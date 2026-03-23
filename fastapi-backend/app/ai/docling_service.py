"""Document conversion service using the Docling library.

Converts PDF, DOCX, and PPTX files to clean Markdown with image extraction.
Docling handles the heavy lifting of document parsing (OCR for scanned PDFs,
table detection, heading hierarchy, list nesting) while this service provides
the async wrapper, image normalization, and metadata extraction layer.

Supported formats:
  - PDF:  Preserves headings (H1-H6 from font sizes), tables (as Markdown
          pipe tables), ordered/unordered lists, OCR for scanned pages.
  - DOCX: Preserves heading styles, tables (merged cells handled gracefully),
          bullet/numbered/nested lists, bold/italic/strikethrough/code spans,
          hyperlinks.
  - PPTX: Each slide becomes ``## Slide N: {title}``, body text as
          paragraphs/lists, speaker notes as blockquotes, tables as pipe tables.

Image extraction:
  - Raster images extracted from all formats.
  - BMP/TIFF/WMF/EMF normalized to PNG; PNG/JPEG preserved.
  - Captions/alt text captured where available.
  - Position ordering maintained.

Error handling:
  - Unsupported file_type       -> ``ImportError``
  - Password-protected PDF      -> ``ImportError``
  - Corrupted / unreadable file -> ``ImportError`` with original details
  - Non-fatal issues            -> appended to ``warnings`` list

All Docling calls are CPU-bound and executed via ``asyncio.to_thread()``
so they do not block the async event loop.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import PictureItem

logger = logging.getLogger(__name__)

# Supported file_type values mapped to Docling InputFormat.
_SUPPORTED_TYPES: dict[str, InputFormat] = {
    "pdf": InputFormat.PDF,
    "docx": InputFormat.DOCX,
    "pptx": InputFormat.PPTX,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DoclingImage:
    """A single image extracted from a document by the Docling pipeline.

    This is the Docling-layer representation. The worker converts these to
    ``image_understanding_service.ExtractedImage`` before passing to the
    image understanding pipeline (see ``worker.py:process_document_import``).

    Attributes:
        image_bytes: Raw image data (PNG or JPEG encoded).
        image_format: Target format string, e.g. ``"png"`` or ``"jpg"``.
        page_number: 1-based source page number, or ``None`` if unavailable.
        caption: Caption or alt-text from the document, if present.
        position: 0-based ordering index within the document.
    """

    image_bytes: bytes
    image_format: str  # "png", "jpg"
    page_number: int | None  # Source page (1-based)
    caption: str | None  # Caption / alt-text from document
    position: int  # Order in document (0-based)


# Backwards-compatible alias for existing imports
ExtractedImage = DoclingImage


@dataclass
class ProcessResult:
    """Full processing output for a single document.

    Attributes:
        markdown: The entire document converted to clean Markdown.
        images: Extracted embedded images (may be empty).
        metadata: Dict with ``page_count``, ``word_count``, ``title_from_doc``.
        warnings: Non-fatal issues encountered during processing.
    """

    markdown: str
    images: list[DoclingImage]
    metadata: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DoclingService:
    """Document conversion service backed by Docling.

    Provides async methods for converting documents to Markdown and extracting
    embedded images.  All CPU-intensive Docling work is offloaded to the
    default thread-pool executor via ``asyncio.to_thread()``.

    Usage::

        service = DoclingService()
        result = await service.process_file("/tmp/report.pdf", "pdf")
        print(result.markdown)
        print(len(result.images))
    """

    def __init__(self) -> None:
        # Configure PDF pipeline to generate picture images so we can extract
        # them later.  Other formats use default options.
        pdf_pipeline_options = PdfPipelineOptions(
            generate_picture_images=True,
        )
        self.converter = DocumentConverter(
            allowed_formats=list(_SUPPORTED_TYPES.values()),
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pdf_pipeline_options,
                ),
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def convert_to_markdown(self, file_path: str) -> str:
        """Convert a document file to clean Markdown.

        Supports PDF, DOCX, and PPTX.  The conversion is performed in a
        background thread so it does not block the event loop.

        Args:
            file_path: Absolute or relative path to the source file.

        Returns:
            Clean Markdown string representing the full document.

        Raises:
            ImportError: If the file is password-protected, corrupted, or
                otherwise unconvertible.
        """
        conv_result = await asyncio.to_thread(self._convert_sync, file_path)
        return conv_result.document.export_to_markdown()

    async def extract_images(self, file_path: str) -> list[ExtractedImage]:
        """Extract embedded images from a document.

        Raster images are extracted in their original format when possible
        (PNG, JPEG).  BMP, TIFF, WMF, and EMF images are normalized to PNG.

        Args:
            file_path: Path to the source document.

        Returns:
            List of :class:`ExtractedImage` instances ordered by position in
            the document.  Returns an empty list if the document contains no
            images.

        Raises:
            ImportError: If the file cannot be opened or converted.
        """
        conv_result = await asyncio.to_thread(self._convert_sync, file_path)
        return self._extract_images_from_result(conv_result)

    async def process_file(
        self,
        file_path: str,
        file_type: str,
        *,
        progress_callback: Callable[[int], Any] | None = None,
    ) -> ProcessResult:
        """Full processing pipeline: validate, convert, extract, metadata.

        Steps:
          1. Validate ``file_type`` is one of ``pdf``, ``docx``, ``pptx``.
          2. Convert the document to Markdown via Docling.
          3. Extract embedded images.
          4. Collect document metadata (page count, word count, title).

        Args:
            file_path: Absolute path to the source file.
            file_type: Lowercase extension without dot (``"pdf"``, ``"docx"``,
                ``"pptx"``).
            progress_callback: Optional callable receiving an integer
                percentage (0-100) as conversion progresses.  Useful for
                files > 50 MB.

        Returns:
            A :class:`ProcessResult` containing Markdown, images, metadata,
            and any non-fatal warnings.

        Raises:
            ImportError: If ``file_type`` is unsupported, the file is
                password-protected, or the file is corrupted.
        """
        file_type_lower = file_type.lower().strip().lstrip(".")
        if file_type_lower not in _SUPPORTED_TYPES:
            raise ImportError(f"Unsupported file type: {file_type}")

        warnings: list[str] = []

        if progress_callback is not None:
            progress_callback(5)

        # --- Conversion ---------------------------------------------------
        try:
            conv_result = await asyncio.to_thread(
                self._convert_sync,
                file_path,
            )
        except ImportError:
            raise
        except Exception as exc:
            raise ImportError(f"Failed to convert file: {exc}") from exc

        if progress_callback is not None:
            progress_callback(30)

        # Check conversion status for partial success / warnings
        if conv_result.status == ConversionStatus.PARTIAL_SUCCESS:
            warnings.append("Document was only partially converted; some content may be missing.")
        elif conv_result.status == ConversionStatus.FAILURE:
            error_msgs = [e.error_message for e in (conv_result.errors or [])]
            detail = "; ".join(error_msgs) if error_msgs else "unknown error"
            raise ImportError(f"Document conversion failed: {detail}")

        # Collect conversion-level warnings from Docling error items
        for err_item in conv_result.errors or []:
            warnings.append(f"[{err_item.component_type}] {err_item.error_message}")

        # --- Markdown export -----------------------------------------------
        try:
            markdown = conv_result.document.export_to_markdown()
        except Exception as exc:
            logger.warning("Markdown export failed, falling back: %s", exc)
            markdown = ""
            warnings.append(f"Markdown export failed: {exc}")

        if progress_callback is not None:
            progress_callback(50)

        # --- Image extraction ----------------------------------------------
        try:
            images = self._extract_images_from_result(conv_result)
        except Exception as exc:
            logger.warning("Image extraction failed: %s", exc)
            images = []
            warnings.append(f"Image extraction failed: {exc}")

        if progress_callback is not None:
            progress_callback(70)

        # --- Metadata extraction -------------------------------------------
        metadata = self._extract_metadata(conv_result, markdown)

        if progress_callback is not None:
            progress_callback(100)

        return ProcessResult(
            markdown=markdown,
            images=images,
            metadata=metadata,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _convert_sync(self, file_path: str) -> Any:
        """Synchronous Docling conversion (runs inside ``to_thread``).

        Validates that the file exists and delegates to
        ``DocumentConverter.convert()``.  Catches and re-raises common
        failure modes with friendly messages.

        Args:
            file_path: Path to the document file.

        Returns:
            A Docling ``ConversionResult``.

        Raises:
            ImportError: On password-protected PDFs, corrupted files, or
                any other conversion failure.
        """
        path = Path(file_path)
        if not path.is_file():
            raise ImportError(f"File not found: {file_path}")

        try:
            result = self.converter.convert(str(path), raises_on_error=False)
        except Exception as exc:
            exc_str = str(exc).lower()
            if "password" in exc_str or "encrypted" in exc_str:
                raise ImportError("Password-protected PDF files are not supported") from exc
            raise ImportError(f"Failed to convert document: {exc}") from exc

        # Detect password-protection from Docling error items
        if result.status == ConversionStatus.FAILURE:
            error_msgs = " ".join(e.error_message for e in (result.errors or [])).lower()
            if "password" in error_msgs or "encrypted" in error_msgs:
                raise ImportError("Password-protected PDF files are not supported")

        return result

    def _extract_images_from_result(
        self,
        conv_result: Any,
    ) -> list[ExtractedImage]:
        """Walk the converted document and extract raster images.

        Iterates over all ``PictureItem`` nodes in the ``DoclingDocument``,
        renders each to a PIL Image via ``get_image()``, normalizes exotic
        formats (BMP/TIFF/WMF/EMF) to PNG, and preserves native PNG/JPEG.

        Args:
            conv_result: A Docling ``ConversionResult``.

        Returns:
            Ordered list of :class:`ExtractedImage`.
        """
        images: list[ExtractedImage] = []
        doc = conv_result.document
        position = 0

        for element, _level in doc.iterate_items():
            if not isinstance(element, PictureItem):
                continue

            try:
                pil_image = element.get_image(doc)
            except Exception as exc:
                logger.debug("Could not extract image at position %d: %s", position, exc)
                position += 1
                continue

            if pil_image is None:
                position += 1
                continue

            # Determine output format and page number
            image_format, image_bytes = self._encode_pil_image(pil_image)
            page_number = self._get_picture_page(element)
            caption = self._get_picture_caption(element)

            images.append(
                ExtractedImage(
                    image_bytes=image_bytes,
                    image_format=image_format,
                    page_number=page_number,
                    caption=caption,
                    position=position,
                )
            )
            position += 1

        return images

    @staticmethod
    def _encode_pil_image(pil_image: Any) -> tuple[str, bytes]:
        """Encode a PIL Image to bytes, choosing PNG or JPEG.

        - If the original format is JPEG, re-encode as JPEG.
        - For everything else (BMP, TIFF, WMF, EMF, or unknown), encode as
          PNG to guarantee lossless quality and broad compatibility.

        Args:
            pil_image: A ``PIL.Image.Image`` instance.

        Returns:
            Tuple of (format_string, raw_bytes).
        """
        buf = io.BytesIO()
        original_format = (getattr(pil_image, "format", None) or "").upper()

        if original_format == "JPEG":
            # Preserve JPEG encoding
            pil_image.save(buf, format="JPEG", quality=95)
            return "jpg", buf.getvalue()

        # Default to PNG (handles BMP, TIFF, WMF, EMF, and unknown)
        # Ensure we have an RGB/RGBA mode for PNG compatibility
        if pil_image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            pil_image = pil_image.convert("RGBA")
        pil_image.save(buf, format="PNG")
        return "png", buf.getvalue()

    @staticmethod
    def _get_picture_page(element: Any) -> int | None:
        """Extract the 1-based page number from a PictureItem.

        Docling stores provenance information on document items.  This
        helper attempts several attribute paths to find the page number.

        Args:
            element: A ``PictureItem`` from Docling.

        Returns:
            1-based page number, or ``None`` if unavailable.
        """
        try:
            # PictureItem stores provenance with page references
            prov_list = getattr(element, "prov", None)
            if prov_list:
                for prov in prov_list:
                    page_no = getattr(prov, "page_no", None)
                    if page_no is not None:
                        return int(page_no)
        except Exception:
            pass
        return None

    @staticmethod
    def _get_picture_caption(element: Any) -> str | None:
        """Extract caption text from a PictureItem.

        Checks ``captions``, ``caption_text()``, and ``annotations`` for
        any textual description attached to the picture.

        Args:
            element: A ``PictureItem`` from Docling.

        Returns:
            Caption string, or ``None`` if not available.
        """
        # Try caption_text() method first (docling-core >=2.x)
        try:
            captions = getattr(element, "captions", None)
            if captions:
                texts = []
                for cap in captions:
                    cap_text = getattr(cap, "text", None)
                    if cap_text and str(cap_text).strip():
                        texts.append(str(cap_text).strip())
                if texts:
                    return " ".join(texts)
        except Exception:
            pass

        # Fallback to annotations
        try:
            annotations = getattr(element, "annotations", None)
            if annotations:
                for ann in annotations:
                    label = getattr(ann, "label", None) or getattr(ann, "predicted_class", None)
                    if label and str(label).strip():
                        return str(label).strip()
        except Exception:
            pass

        return None

    @staticmethod
    def _extract_metadata(
        conv_result: Any,
        markdown: str,
    ) -> dict[str, Any]:
        """Extract document metadata from the conversion result.

        Collects:
          - ``page_count``: Number of pages (from Docling pages dict).
          - ``word_count``: Approximate word count from the Markdown output.
          - ``title_from_doc``: Document title extracted from metadata or
            the first heading in the Markdown.

        Args:
            conv_result: A Docling ``ConversionResult``.
            markdown: The exported Markdown string.

        Returns:
            Dict with ``page_count``, ``word_count``, ``title_from_doc``.
        """
        doc = conv_result.document

        # --- Page count ----------------------------------------------------
        page_count = 0
        try:
            pages = getattr(doc, "pages", None)
            if pages is not None:
                page_count = len(pages)
        except Exception:
            pass

        # --- Word count (from markdown) ------------------------------------
        word_count = len(markdown.split()) if markdown else 0

        # --- Title ---------------------------------------------------------
        title_from_doc = _extract_title(doc, markdown)

        return {
            "page_count": page_count,
            "word_count": word_count,
            "title_from_doc": title_from_doc,
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _extract_title(doc: Any, markdown: str) -> str | None:
    """Best-effort title extraction from a DoclingDocument.

    Priority:
      1. ``doc.name`` if it looks like a real title (not a UUID/hash).
      2. First ``#`` heading in the exported Markdown.
      3. ``None`` if nothing useful found.

    Args:
        doc: A Docling ``DoclingDocument``.
        markdown: Exported Markdown text.

    Returns:
        Title string or ``None``.
    """
    # Try doc.name — Docling sometimes sets this to the PDF title metadata
    try:
        name = getattr(doc, "name", None)
        if name and isinstance(name, str):
            name = name.strip()
            # Skip names that look like hashes or temp file names
            if len(name) > 2 and not name.startswith("tmp") and not _looks_like_hash(name):
                return name
    except Exception:
        pass

    # Fall back to the first heading in Markdown
    if markdown:
        match = re.search(r"^#{1,6}\s+(.+)$", markdown, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            if title:
                return title

    return None


def _looks_like_hash(text: str) -> bool:
    """Return True if *text* looks like a hex hash or UUID."""
    cleaned = text.replace("-", "").replace("_", "")
    if len(cleaned) >= 16 and all(c in "0123456789abcdefABCDEF" for c in cleaned):
        return True
    return False
