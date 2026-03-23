"""Tests for DoclingService document conversion.

Mocks the Docling DocumentConverter since it may not be installed in the test
environment.  Verifies Markdown output structure, image extraction, metadata
collection, and error handling for all supported file types.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Mock Docling modules BEFORE importing the service so top-level imports in
# docling_service.py resolve against our mocks rather than the real library.
# ---------------------------------------------------------------------------

# Create mock module hierarchy for docling imports
_mock_InputFormat = MagicMock()
_mock_InputFormat.PDF = "pdf"
_mock_InputFormat.DOCX = "docx"
_mock_InputFormat.PPTX = "pptx"

_mock_ConversionStatus = MagicMock()
_mock_ConversionStatus.SUCCESS = "SUCCESS"
_mock_ConversionStatus.PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
_mock_ConversionStatus.FAILURE = "FAILURE"

_mock_PictureItem = type("PictureItem", (), {})

_mock_base_models = MagicMock()
_mock_base_models.ConversionStatus = _mock_ConversionStatus
_mock_base_models.InputFormat = _mock_InputFormat

_mock_pipeline_options = MagicMock()
_mock_document_converter_mod = MagicMock()
_mock_docling_core_types = MagicMock()
_mock_docling_core_types.PictureItem = _mock_PictureItem

import sys

sys.modules.setdefault("docling", MagicMock())
sys.modules.setdefault("docling.datamodel", MagicMock())
sys.modules.setdefault("docling.datamodel.base_models", _mock_base_models)
sys.modules.setdefault("docling.datamodel.pipeline_options", _mock_pipeline_options)
sys.modules.setdefault("docling.document_converter", _mock_document_converter_mod)
sys.modules.setdefault("docling_core", MagicMock())
sys.modules.setdefault("docling_core.types", MagicMock())
sys.modules.setdefault("docling_core.types.doc", _mock_docling_core_types)

# Now import the service under test
from app.ai.docling_service import DoclingService, ExtractedImage, ProcessResult


# ---------------------------------------------------------------------------
# Helpers to build mock ConversionResult objects
# ---------------------------------------------------------------------------


def _make_mock_document(
    markdown: str = "# Title\n\nHello world",
    pages: dict | None = None,
    name: str | None = None,
    items: list[tuple[Any, int]] | None = None,
) -> MagicMock:
    """Build a mock DoclingDocument."""
    doc = MagicMock()
    doc.export_to_markdown.return_value = markdown
    doc.pages = pages if pages is not None else {1: MagicMock(), 2: MagicMock()}
    doc.name = name

    if items is None:
        items = []
    doc.iterate_items.return_value = iter(items)

    return doc


def _make_conv_result(
    *,
    status: str = "SUCCESS",
    document: MagicMock | None = None,
    errors: list | None = None,
) -> MagicMock:
    """Build a mock Docling ConversionResult."""
    result = MagicMock()
    result.status = status
    result.document = document or _make_mock_document()
    result.errors = errors
    return result


def _make_picture_item(
    pil_image: Any | None = None,
    page_no: int | None = 1,
    caption_text: str | None = None,
) -> MagicMock:
    """Build a mock PictureItem for image extraction tests."""
    element = MagicMock()
    # Make isinstance(element, PictureItem) return True
    element.__class__ = _mock_PictureItem

    if pil_image is not None:
        element.get_image.return_value = pil_image
    else:
        element.get_image.return_value = None

    # Provenance for page number
    if page_no is not None:
        prov = MagicMock()
        prov.page_no = page_no
        element.prov = [prov]
    else:
        element.prov = []

    # Caption
    if caption_text is not None:
        cap = MagicMock()
        cap.text = caption_text
        element.captions = [cap]
    else:
        element.captions = []

    element.annotations = []
    return element


def _make_pil_image(
    fmt: str = "PNG",
    mode: str = "RGB",
    size: tuple[int, int] = (100, 100),
) -> MagicMock:
    """Build a mock PIL Image."""
    img = MagicMock()
    img.format = fmt
    img.mode = mode
    img.size = size
    img.save = MagicMock(side_effect=lambda buf, **kw: buf.write(b"\x89PNG_FAKE_DATA"))
    if mode not in ("RGB", "RGBA", "L", "LA", "P"):
        converted = MagicMock()
        converted.format = fmt
        converted.mode = "RGBA"
        converted.save = MagicMock(side_effect=lambda buf, **kw: buf.write(b"\x89PNG_FAKE_DATA"))
        img.convert.return_value = converted
    return img


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDoclingService:
    """Tests for DoclingService document conversion."""

    # -----------------------------------------------------------------------
    # 1. test_convert_pdf_to_markdown
    # -----------------------------------------------------------------------

    async def test_convert_pdf_to_markdown(self) -> None:
        """Mock DocumentConverter, verify headings/paragraphs/lists in output."""
        expected_md = (
            "# Quarterly Report\n\nThis is the introduction paragraph.\n\n- Item one\n- Item two\n- Item three\n"
        )
        mock_doc = _make_mock_document(markdown=expected_md)
        conv_result = _make_conv_result(document=mock_doc)

        service = DoclingService.__new__(DoclingService)
        service.converter = MagicMock()
        service.converter.convert.return_value = conv_result

        with patch.object(service, "_convert_sync", return_value=conv_result):
            result = await service.convert_to_markdown("/tmp/report.pdf")

        assert "# Quarterly Report" in result
        assert "This is the introduction paragraph." in result
        assert "- Item one" in result
        assert "- Item two" in result
        assert "- Item three" in result

    # -----------------------------------------------------------------------
    # 2. test_convert_pdf_tables_to_markdown
    # -----------------------------------------------------------------------

    async def test_convert_pdf_tables_to_markdown(self) -> None:
        """Verify tables rendered as Markdown pipe tables."""
        table_md = (
            "# Report\n\n| Name | Score | Grade |\n|------|-------|-------|\n| Alice | 95 | A |\n| Bob | 87 | B |\n"
        )
        mock_doc = _make_mock_document(markdown=table_md)
        conv_result = _make_conv_result(document=mock_doc)

        service = DoclingService.__new__(DoclingService)
        service.converter = MagicMock()

        with patch.object(service, "_convert_sync", return_value=conv_result):
            result = await service.convert_to_markdown("/tmp/tables.pdf")

        assert "| Name | Score | Grade |" in result
        assert "|------|-------|-------|" in result
        assert "| Alice | 95 | A |" in result

    # -----------------------------------------------------------------------
    # 3. test_convert_docx_to_markdown
    # -----------------------------------------------------------------------

    async def test_convert_docx_to_markdown(self) -> None:
        """Verify DOCX headings, bold/italic, lists."""
        docx_md = (
            "# Main Heading\n\n"
            "## Sub Heading\n\n"
            "This has **bold** and *italic* text.\n\n"
            "1. First item\n"
            "2. Second item\n"
        )
        mock_doc = _make_mock_document(markdown=docx_md)
        conv_result = _make_conv_result(document=mock_doc)

        service = DoclingService.__new__(DoclingService)
        service.converter = MagicMock()

        with patch.object(service, "_convert_sync", return_value=conv_result):
            result = await service.convert_to_markdown("/tmp/doc.docx")

        assert "# Main Heading" in result
        assert "## Sub Heading" in result
        assert "**bold**" in result
        assert "*italic*" in result
        assert "1. First item" in result

    # -----------------------------------------------------------------------
    # 4. test_convert_pptx_to_markdown
    # -----------------------------------------------------------------------

    async def test_convert_pptx_to_markdown(self) -> None:
        """Verify slides as sections with titles."""
        pptx_md = (
            "## Slide 1: Introduction\n\n"
            "Welcome to the presentation.\n\n"
            "## Slide 2: Main Points\n\n"
            "- Point A\n"
            "- Point B\n"
        )
        mock_doc = _make_mock_document(markdown=pptx_md)
        conv_result = _make_conv_result(document=mock_doc)

        service = DoclingService.__new__(DoclingService)
        service.converter = MagicMock()

        with patch.object(service, "_convert_sync", return_value=conv_result):
            result = await service.convert_to_markdown("/tmp/slides.pptx")

        assert "## Slide 1: Introduction" in result
        assert "## Slide 2: Main Points" in result
        assert "Welcome to the presentation." in result
        assert "- Point A" in result

    # -----------------------------------------------------------------------
    # 5. test_extract_images_from_pdf
    # -----------------------------------------------------------------------

    async def test_extract_images_from_pdf(self) -> None:
        """Verify images extracted with format, page_number, position."""
        pil_img_1 = _make_pil_image(fmt="PNG")
        pil_img_2 = _make_pil_image(fmt="JPEG")

        pic_1 = _make_picture_item(pil_image=pil_img_1, page_no=1, caption_text="Figure 1")
        pic_2 = _make_picture_item(pil_image=pil_img_2, page_no=3, caption_text="Chart")

        items = [(pic_1, 0), (pic_2, 0)]
        mock_doc = _make_mock_document(items=items)
        conv_result = _make_conv_result(document=mock_doc)

        service = DoclingService.__new__(DoclingService)
        service.converter = MagicMock()

        with patch.object(service, "_convert_sync", return_value=conv_result):
            images = await service.extract_images("/tmp/report.pdf")

        assert len(images) == 2

        assert images[0].page_number == 1
        assert images[0].caption == "Figure 1"
        assert images[0].position == 0
        assert images[0].image_format in ("png", "jpg")
        assert isinstance(images[0].image_bytes, bytes)
        assert len(images[0].image_bytes) > 0

        assert images[1].page_number == 3
        assert images[1].caption == "Chart"
        assert images[1].position == 1

    # -----------------------------------------------------------------------
    # 6. test_process_file_returns_complete_result
    # -----------------------------------------------------------------------

    async def test_process_file_returns_complete_result(self) -> None:
        """Verify ProcessResult has all fields populated."""
        markdown = "# Report\n\nParagraph one.\n\nParagraph two."
        pil_img = _make_pil_image()
        pic = _make_picture_item(pil_image=pil_img, page_no=2, caption_text="Diagram")
        items = [(pic, 0)]

        mock_doc = _make_mock_document(
            markdown=markdown,
            pages={1: MagicMock(), 2: MagicMock(), 3: MagicMock()},
            name="Report 2026",
            items=items,
        )
        conv_result = _make_conv_result(
            status=_mock_ConversionStatus.SUCCESS,
            document=mock_doc,
        )

        service = DoclingService.__new__(DoclingService)
        service.converter = MagicMock()

        progress_values: list[int] = []

        with patch.object(service, "_convert_sync", return_value=conv_result):
            result = await service.process_file(
                "/tmp/report.pdf",
                "pdf",
                progress_callback=lambda p: progress_values.append(p),
            )

        assert isinstance(result, ProcessResult)
        assert "# Report" in result.markdown
        assert len(result.images) == 1
        assert result.images[0].caption == "Diagram"
        assert result.metadata["page_count"] == 3
        assert result.metadata["word_count"] > 0
        assert result.metadata["title_from_doc"] == "Report 2026"
        assert isinstance(result.warnings, list)
        # Progress callback was invoked with ascending values
        assert 5 in progress_values
        assert 100 in progress_values
        assert progress_values == sorted(progress_values)

    # -----------------------------------------------------------------------
    # 7. test_corrupted_file_raises_import_error
    # -----------------------------------------------------------------------

    async def test_corrupted_file_raises_import_error(self) -> None:
        """Pass invalid path, verify ImportError."""
        service = DoclingService.__new__(DoclingService)
        service.converter = MagicMock()

        # _convert_sync checks Path.is_file() and raises ImportError
        # We directly test _convert_sync to verify error handling
        with pytest.raises(ImportError, match="File not found"):
            service._convert_sync("/tmp/nonexistent_file_abc123.pdf")

    # -----------------------------------------------------------------------
    # 8. test_unsupported_type_raises_error
    # -----------------------------------------------------------------------

    async def test_unsupported_type_raises_error(self) -> None:
        """Pass type='txt', verify ImportError."""
        service = DoclingService.__new__(DoclingService)
        service.converter = MagicMock()

        with pytest.raises(ImportError, match="Unsupported file type"):
            await service.process_file("/tmp/notes.txt", "txt")

    # -----------------------------------------------------------------------
    # 9. test_password_protected_pdf_raises_error
    # -----------------------------------------------------------------------

    async def test_password_protected_pdf_raises_error(self) -> None:
        """Mock password detection, verify ImportError."""
        service = DoclingService.__new__(DoclingService)
        service.converter = MagicMock()

        # Simulate Docling raising an exception with "password" in message
        service.converter.convert.side_effect = Exception("Cannot open encrypted/password-protected PDF")

        with pytest.raises(ImportError, match="Password-protected PDF"):
            service._convert_sync.__wrapped__ if hasattr(service._convert_sync, "__wrapped__") else None
            # Directly call _convert_sync with a "file" that exists (mock it)
            with patch("app.ai.docling_service.Path") as mock_path:
                mock_path.return_value.is_file.return_value = True
                mock_path.return_value.__str__ = lambda self: "/tmp/locked.pdf"
                service._convert_sync("/tmp/locked.pdf")

    # -----------------------------------------------------------------------
    # 10. test_zero_images_returns_empty_list
    # -----------------------------------------------------------------------

    async def test_zero_images_returns_empty_list(self) -> None:
        """Document with no images returns []."""
        mock_doc = _make_mock_document(
            markdown="# Just Text\n\nNo images here.",
            items=[],  # No PictureItems
        )
        conv_result = _make_conv_result(document=mock_doc)

        service = DoclingService.__new__(DoclingService)
        service.converter = MagicMock()

        with patch.object(service, "_convert_sync", return_value=conv_result):
            images = await service.extract_images("/tmp/text_only.pdf")

        assert images == []


# ---------------------------------------------------------------------------
# Standalone tests for module-level helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for module-level helper functions."""

    def test_looks_like_hash_detects_hex(self) -> None:
        """Hash detection recognizes 32-char hex strings."""
        from app.ai.docling_service import _looks_like_hash

        assert _looks_like_hash("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4") is True
        assert _looks_like_hash("My Report Title") is False

    def test_extract_title_from_heading(self) -> None:
        """Title extraction falls back to first heading in Markdown."""
        from app.ai.docling_service import _extract_title

        doc = MagicMock()
        doc.name = None

        title = _extract_title(doc, "# My Report\n\nContent here.")
        assert title == "My Report"

    def test_extract_title_from_doc_name(self) -> None:
        """Title extraction uses doc.name when it looks like a real title."""
        from app.ai.docling_service import _extract_title

        doc = MagicMock()
        doc.name = "Quarterly Revenue Report"

        title = _extract_title(doc, "# Heading\n\nBody.")
        assert title == "Quarterly Revenue Report"

    def test_extract_title_skips_hash_name(self) -> None:
        """Title extraction skips doc.name that looks like a hash."""
        from app.ai.docling_service import _extract_title

        doc = MagicMock()
        doc.name = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"

        title = _extract_title(doc, "# Real Title\n\nBody.")
        assert title == "Real Title"
