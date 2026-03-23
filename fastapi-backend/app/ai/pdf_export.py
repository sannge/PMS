"""PDF export service for AI document export.

Creates PDF files from document content using fpdf2 (pure Python, no system deps).
Files stored in temp directory scoped by user_id with 1-hour TTL cleanup.
"""

from __future__ import annotations

import logging
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from fpdf import FPDF

from .config_service import get_agent_config

logger = logging.getLogger(__name__)

_cfg = get_agent_config()

EXPORT_DIR = Path(tempfile.gettempdir()) / "blair_exports"
EXPORT_TTL_SECONDS = _cfg.get_int("export.pdf_ttl_seconds", 3600)


@dataclass
class PdfExportResult:
    """Result of PDF export."""

    filename: str
    download_url: str
    byte_count: int


def _sanitize_filename(title: str) -> str:
    """Sanitize a title for use as a filename."""
    clean = re.sub(r"[^\w\s\-.]", "", title)
    clean = re.sub(r"\s+", "_", clean.strip())
    return clean[:100] or "document"


def generate_pdf(title: str, content: str) -> bytes:
    """Generate a PDF document from title and markdown/plain text content.

    Args:
        title: Document title (rendered as heading).
        content: Document content in markdown or plain text.

    Returns:
        PDF file contents as bytes.
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Content -- process line by line for basic formatting
    page_width = pdf.w - pdf.l_margin - pdf.r_margin
    lines = content.split("\n")
    for line in lines:
        stripped = line.strip()
        # Ensure cursor is at left margin before each line
        pdf.set_x(pdf.l_margin)

        # Heading detection (markdown)
        if stripped.startswith("### "):
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(page_width, 7, stripped[4:])
            pdf.ln(3)
        elif stripped.startswith("## "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.multi_cell(page_width, 7, stripped[3:])
            pdf.ln(3)
        elif stripped.startswith("# "):
            pdf.set_font("Helvetica", "B", 16)
            pdf.multi_cell(page_width, 8, stripped[2:])
            pdf.ln(4)
        elif stripped.startswith("---"):
            # Horizontal rule
            pdf.ln(3)
            y = pdf.get_y()
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(5)
        elif stripped == "":
            pdf.ln(4)
        else:
            # Strip basic markdown formatting for clean PDF text
            clean = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", stripped)
            clean = re.sub(r"_{1,3}(.+?)_{1,3}", r"\1", clean)
            clean = re.sub(r"~~(.+?)~~", r"\1", clean)
            clean = re.sub(r"`(.+?)`", r"\1", clean)
            clean = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", clean)

            # List items -- replace marker with bullet character
            list_match = re.match(r"^[-*+]\s+(.*)", clean)
            numbered_match = re.match(r"^(\d+\.)\s+(.*)", clean)
            if list_match:
                pdf.set_font("Helvetica", "", 11)
                pdf.multi_cell(page_width, 6, "  - " + list_match.group(1))
            elif numbered_match:
                pdf.set_font("Helvetica", "", 11)
                pdf.multi_cell(page_width, 6, "  " + numbered_match.group(1) + " " + numbered_match.group(2))
            else:
                pdf.set_font("Helvetica", "", 11)
                pdf.multi_cell(page_width, 6, clean)

    return bytes(pdf.output())


def _cleanup_expired_exports(user_dir: Path) -> None:
    """Delete export files older than EXPORT_TTL_SECONDS in the user's directory."""
    try:
        cutoff = time.time() - EXPORT_TTL_SECONDS
        for f in user_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                    logger.debug("Cleaned up expired export: %s", f.name)
                except OSError:
                    pass  # Best-effort cleanup
    except OSError:
        pass  # Directory may not exist yet


async def save_pdf_export(
    pdf_bytes: bytes,
    title: str,
    user_id: UUID,
) -> PdfExportResult:
    """Save PDF bytes to the export directory and return download info.

    Args:
        pdf_bytes: PDF file content.
        title: Document title (used for filename).
        user_id: UUID of the requesting user (for file scoping).

    Returns:
        PdfExportResult with filename and download URL.
    """
    # Ensure export directory exists
    user_dir = EXPORT_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    # Clean up expired exports for this user
    _cleanup_expired_exports(user_dir)

    # Generate unique filename
    safe_title = _sanitize_filename(title)
    unique_id = uuid4().hex[:8]
    filename = f"{safe_title}_{unique_id}.pdf"
    filepath = user_dir / filename

    # Write PDF
    filepath.write_bytes(pdf_bytes)

    download_url = f"/api/ai/export/{filename}"

    logger.info(
        "PDF export created: %s (%d bytes) for user %s",
        filename,
        len(pdf_bytes),
        user_id,
    )

    return PdfExportResult(
        filename=filename,
        download_url=download_url,
        byte_count=len(pdf_bytes),
    )
