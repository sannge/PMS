"""Spreadsheet content extraction service.

Extracts text content from Excel (XLSX/XLS/XLSM/XLSB) and CSV/TSV files
into Markdown format for indexing and embedding.

Excel files use python-calamine for fast reading. CSV/TSV files use the
stdlib csv module with chardet for encoding detection.

Output format:
- <=10 columns: Markdown pipe table
- >10 columns: Markdown key-value format (one row = one KV block)

Guards:
- Max 50 sheets per workbook
- Max 500K rows per sheet
- Max 10K characters per cell
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from zipfile import BadZipFile

logger = logging.getLogger(__name__)

# Guards
MAX_SHEETS = 50
MAX_ROWS_PER_SHEET = 500_000
MAX_CELL_CHARS = 10_000


@dataclass
class SpreadsheetResult:
    """Result of spreadsheet extraction."""

    markdown: str
    sheet_count: int = 0
    total_rows: int = 0
    warnings: list[str] = field(default_factory=list)


# MED-6: Formula-injection prefixes that could be dangerous in downstream tools
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _format_cell(value: Any) -> str:
    """Format a cell value to a clean string representation.

    - datetime -> YYYY-MM-DD HH:MM:SS
    - bool -> Yes/No
    - float with .0 -> int
    - float -> g-format for precision (MED-16)
    - None -> empty string
    - Truncate to MAX_CELL_CHARS
    - Sanitize formula-like values (MED-6)
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        # MED-16: Use g-format for better float precision
        return f"{value:.10g}"
    text = str(value)
    if len(text) > MAX_CELL_CHARS:
        text = text[:MAX_CELL_CHARS] + "..."
    # Replace pipe characters in cell values to avoid breaking Markdown tables
    text = text.replace("|", "\\|")
    # Collapse newlines within cells
    text = text.replace("\n", " ").replace("\r", "")
    text = text.strip()
    # MED-6: Prepend single quote to formula-like cell values
    if text and text[0] in _FORMULA_PREFIXES:
        text = f"'{text}"
    return text


def _rows_to_markdown_table(
    headers: list[str], rows: list[list[str]]
) -> str:
    """Convert rows to a Markdown pipe table."""
    if not headers:
        return ""

    lines: list[str] = []
    # Header row
    lines.append("| " + " | ".join(headers) + " |")
    # Separator row
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    # Data rows
    for row in rows:
        # Pad row to match header length
        padded = row + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(padded[:len(headers)]) + " |")

    return "\n".join(lines) + "\n"


def _rows_to_markdown_kv(
    headers: list[str], rows: list[list[str]]
) -> str:
    """Convert rows to Markdown key-value format (for wide tables)."""
    blocks: list[str] = []
    for row_idx, row in enumerate(rows, 1):
        lines = [f"**Row {row_idx}**"]
        for col_idx, header in enumerate(headers):
            value = row[col_idx] if col_idx < len(row) else ""
            if value:
                lines.append(f"- **{header}**: {value}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


class SpreadsheetExtractor:
    """Extracts text content from spreadsheet files.

    Supports:
    - XLSX, XLS, XLSM, XLSB via python-calamine
    - CSV, TSV via stdlib csv + chardet
    """

    def extract_excel(self, file_path: str | Path) -> SpreadsheetResult:
        """Extract content from an Excel file using python-calamine.

        Args:
            file_path: Path to the Excel file.

        Returns:
            SpreadsheetResult with Markdown content.

        Raises:
            ImportError: If python-calamine is not installed.
            ValueError: If the file is corrupt, password-protected, or invalid.
        """
        try:
            from python_calamine import CalamineWorkbook
        except ImportError:
            raise ImportError(
                "python-calamine is required for Excel extraction. "
                "Install with: uv add python-calamine"
            )

        warnings: list[str] = []

        try:
            wb = CalamineWorkbook.from_path(str(file_path))
        except BadZipFile:
            raise ValueError("File is not a valid Excel file (bad ZIP format)")
        except Exception as exc:
            # Try openpyxl fallback for password-protected files
            err_str = str(exc).lower()
            if "password" in err_str or "encrypted" in err_str:
                raise ValueError("Password-protected Excel files are not supported")
            raise ValueError(f"Failed to open Excel file: {exc}")

        sheet_names = wb.sheet_names
        if not sheet_names:
            return SpreadsheetResult(markdown="*Empty workbook*\n", warnings=warnings)

        if len(sheet_names) > MAX_SHEETS:
            warnings.append(
                f"Workbook has {len(sheet_names)} sheets; only the first {MAX_SHEETS} are processed."
            )
            sheet_names = sheet_names[:MAX_SHEETS]

        sections: list[str] = []
        total_rows = 0

        for sheet_name in sheet_names:
            try:
                data = wb.get_sheet_by_name(sheet_name).to_python()
            except Exception as exc:
                warnings.append(f"Skipped sheet '{sheet_name}': {exc}")
                continue

            if not data:
                continue

            # Cap rows
            if len(data) > MAX_ROWS_PER_SHEET:
                warnings.append(
                    f"Sheet '{sheet_name}' has {len(data)} rows; "
                    f"capped at {MAX_ROWS_PER_SHEET}."
                )
                data = data[:MAX_ROWS_PER_SHEET]

            total_rows += len(data)

            # First row is headers
            raw_headers = data[0] if data else []
            headers = [_format_cell(h) or f"Col{i+1}" for i, h in enumerate(raw_headers)]
            rows = [[_format_cell(c) for c in row] for row in data[1:]]

            # Build section
            section_title = f"## {sheet_name}\n\n"
            if len(headers) <= 10:
                section_body = _rows_to_markdown_table(headers, rows)
            else:
                section_body = _rows_to_markdown_kv(headers, rows)

            sections.append(section_title + section_body)

        markdown = "\n\n".join(sections) if sections else "*Empty workbook*\n"

        return SpreadsheetResult(
            markdown=markdown,
            sheet_count=len(sheet_names),
            total_rows=total_rows,
            warnings=warnings,
        )

    def extract_csv(
        self,
        file_path: str | Path,
        delimiter: str | None = None,
    ) -> SpreadsheetResult:
        """Extract content from a CSV or TSV file.

        Uses chardet for encoding detection when the file is not valid UTF-8.

        Args:
            file_path: Path to the CSV/TSV file.
            delimiter: Explicit delimiter. If None, auto-detected from extension.

        Returns:
            SpreadsheetResult with Markdown content.

        Raises:
            ValueError: If the file cannot be read.
        """
        path = Path(file_path)
        warnings: list[str] = []

        # Detect delimiter from extension
        if delimiter is None:
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","

        # HIGH-12: Read only first 32KB for encoding detection, then stream
        with open(path, "rb") as f:
            sample = f.read(32 * 1024)
            if not sample:
                return SpreadsheetResult(markdown="*Empty file*\n", warnings=warnings)

            # Detect encoding from sample
            encoding = "utf-8"
            try:
                sample.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    import chardet
                    detected = chardet.detect(sample)
                    encoding = detected.get("encoding", "latin-1") or "latin-1"
                    warnings.append(f"File encoding detected as {encoding} (not UTF-8)")
                except ImportError:
                    encoding = "latin-1"
                    warnings.append("chardet not available; fell back to latin-1 encoding")

        # Stream-read the file with detected encoding
        all_rows: list[list[str]] = []
        with open(path, "r", encoding=encoding, errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            for row in reader:
                if len(all_rows) >= MAX_ROWS_PER_SHEET + 1:
                    warnings.append(
                        f"CSV file has more than {MAX_ROWS_PER_SHEET} rows; truncated."
                    )
                    break
                all_rows.append([_format_cell(c) for c in row])

        if not all_rows:
            return SpreadsheetResult(markdown="*Empty file*\n", warnings=warnings)

        # MED-17: Detect if first row is a header using csv.Sniffer
        has_header = True
        try:
            # Re-read a sample for header detection
            sample_text = "\n".join(
                delimiter.join(row) for row in all_rows[:20]
            )
            has_header = csv.Sniffer().has_header(sample_text)
        except csv.Error:
            pass  # Default to assuming first row is header

        if has_header:
            headers = all_rows[0] if all_rows else []
            headers = [h or f"Col{i+1}" for i, h in enumerate(headers)]
            data_rows = all_rows[1:]
        else:
            # Generate column headers: Column_1, Column_2, ...
            col_count = len(all_rows[0]) if all_rows else 0
            headers = [f"Column_{i+1}" for i in range(col_count)]
            data_rows = all_rows
            warnings.append("No header row detected; generated column names.")

        if len(headers) <= 10:
            markdown = _rows_to_markdown_table(headers, data_rows)
        else:
            markdown = _rows_to_markdown_kv(headers, data_rows)

        return SpreadsheetResult(
            markdown=markdown,
            sheet_count=1,
            total_rows=len(data_rows),
            warnings=warnings,
        )
