"""File content extraction orchestrator.

Routes file extraction to the appropriate service based on file extension:
- .pdf, .docx, .pptx -> DoclingService
- .xlsx, .xls, .xlsm, .xlsb, .csv, .tsv -> SpreadsheetExtractor
- .vsdx -> VisioExtractor

Provides a unified ExtractionResult interface regardless of the underlying
extractor. All extraction is run via asyncio.to_thread() to avoid blocking
the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# File extension routing
_DOCLING_EXTENSIONS = {".pdf", ".docx", ".pptx"}
_SPREADSHEET_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".xlsb", ".csv", ".tsv"}
_VISIO_EXTENSIONS = {".vsdx"}

# All supported extensions
SUPPORTED_EXTENSIONS = _DOCLING_EXTENSIONS | _SPREADSHEET_EXTENSIONS | _VISIO_EXTENSIONS

# Size guards per category (bytes)
MAX_DOCLING_SIZE = 200 * 1024 * 1024  # 200 MB
MAX_SPREADSHEET_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_VISIO_SIZE = 50 * 1024 * 1024  # 50 MB


@dataclass
class ExtractionResult:
    """Unified result from any file extraction service."""

    markdown: str
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None


class FileExtractionService:
    """Orchestrates file content extraction by routing to the right extractor.

    All extraction methods are async-safe (run in thread pool) and return
    an ExtractionResult regardless of success or failure.
    """

    async def extract(
        self,
        file_path: str | Path,
        extension: str,
        file_size: int = 0,
    ) -> ExtractionResult:
        """Extract content from a file.

        Args:
            file_path: Path to the file on disk.
            extension: File extension including the dot (e.g., ".pdf").
            file_size: File size in bytes for guard checks.

        Returns:
            ExtractionResult with markdown content or error details.
        """
        ext = extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"

        if ext not in SUPPORTED_EXTENSIONS:
            return ExtractionResult(
                markdown="",
                success=False,
                error=f"Unsupported file extension: {ext}",
            )

        # Size guards
        if ext in _DOCLING_EXTENSIONS and file_size > MAX_DOCLING_SIZE:
            return ExtractionResult(
                markdown="",
                success=False,
                error=f"File too large for extraction ({file_size} bytes, max {MAX_DOCLING_SIZE})",
            )
        if ext in _SPREADSHEET_EXTENSIONS and file_size > MAX_SPREADSHEET_SIZE:
            return ExtractionResult(
                markdown="",
                success=False,
                error=f"File too large for extraction ({file_size} bytes, max {MAX_SPREADSHEET_SIZE})",
            )
        if ext in _VISIO_EXTENSIONS and file_size > MAX_VISIO_SIZE:
            return ExtractionResult(
                markdown="",
                success=False,
                error=f"File too large for extraction ({file_size} bytes, max {MAX_VISIO_SIZE})",
            )

        try:
            if ext in _DOCLING_EXTENSIONS:
                return await self._extract_docling(file_path, ext)
            elif ext in _SPREADSHEET_EXTENSIONS:
                return await self._extract_spreadsheet(file_path, ext)
            elif ext in _VISIO_EXTENSIONS:
                return await self._extract_visio(file_path)
            else:
                return ExtractionResult(
                    markdown="",
                    success=False,
                    error=f"No extractor for extension: {ext}",
                )
        except (ImportError, ValueError) as exc:
            return ExtractionResult(
                markdown="",
                success=False,
                error=str(exc),
            )
        except Exception as exc:
            logger.error(
                "File extraction failed for %s: %s: %s",
                file_path, type(exc).__name__, exc,
            )
            return ExtractionResult(
                markdown="",
                success=False,
                error=f"Extraction failed: {type(exc).__name__}: {exc}",
            )

    async def _extract_docling(
        self, file_path: str | Path, ext: str
    ) -> ExtractionResult:
        """Extract content using DoclingService."""
        from .docling_service import DoclingService

        svc = DoclingService()
        file_type = ext.lstrip(".")

        result = await svc.process_file(
            file_path=str(file_path),
            file_type=file_type,
        )

        return ExtractionResult(
            markdown=result.markdown,
            metadata={
                "page_count": result.metadata.get("page_count"),
                "image_count": len(result.images) if result.images else 0,
                "warnings": result.warnings,
            },
            warnings=result.warnings,
            success=True,
        )

    async def _extract_spreadsheet(
        self, file_path: str | Path, ext: str
    ) -> ExtractionResult:
        """Extract content using SpreadsheetExtractor."""
        from .spreadsheet_extractor import SpreadsheetExtractor

        extractor = SpreadsheetExtractor()

        if ext in {".csv", ".tsv"}:
            result = await asyncio.to_thread(
                extractor.extract_csv, file_path
            )
        else:
            result = await asyncio.to_thread(
                extractor.extract_excel, file_path
            )

        return ExtractionResult(
            markdown=result.markdown,
            metadata={
                "sheet_count": result.sheet_count,
                "total_rows": result.total_rows,
            },
            warnings=result.warnings,
            success=True,
        )

    async def _extract_visio(
        self, file_path: str | Path
    ) -> ExtractionResult:
        """Extract content using VisioExtractor."""
        from .visio_extractor import VisioExtractor

        extractor = VisioExtractor()
        result = await asyncio.to_thread(extractor.extract, file_path)

        return ExtractionResult(
            markdown=result.markdown,
            metadata={
                "page_count": result.page_count,
                "shape_count": result.shape_count,
                "connection_count": result.connection_count,
            },
            warnings=result.warnings,
            success=True,
        )
