"""Visio (.vsdx) content extraction service.

Extracts text content from Visio diagrams into Markdown format
using the vsdx library. Captures shape text and connections per page.

Output format:
  ## Page: {page_name}
  ### Shapes
  - **{shape_id}**: {shape_text}
  ### Connections
  - {source_text} --> {target_text}

Error handling:
- BadZipFile -> ValueError (corrupt file)
- XMLSyntaxError -> ValueError (corrupt file)
- Empty files -> ValueError
- ImportError only for missing vsdx library
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import BadZipFile

logger = logging.getLogger(__name__)

# HIGH-9: Maximum total uncompressed size for VSDX (ZIP) files (500 MB)
MAX_UNCOMPRESSED_SIZE = 500 * 1024 * 1024

# MED-18: Maximum number of shapes to process per file
MAX_SHAPES = 10_000

# HIGH-9: Maximum recursion depth for grouped shapes
MAX_SHAPE_RECURSION_DEPTH = 10


@dataclass
class VisioResult:
    """Result of Visio extraction."""

    markdown: str
    page_count: int = 0
    shape_count: int = 0
    connection_count: int = 0
    warnings: list[str] = field(default_factory=list)


class VisioExtractor:
    """Extracts text content from Visio (.vsdx) files.

    Uses the vsdx library to parse the OOXML structure and extract
    shape text and connection topology from each page.
    """

    def extract(self, file_path: str | Path) -> VisioResult:
        """Extract content from a Visio file.

        Args:
            file_path: Path to the .vsdx file.

        Returns:
            VisioResult with Markdown content.

        Raises:
            ImportError: If the vsdx library is not installed.
            ValueError: If the file is corrupt, empty, or invalid.
        """
        try:
            import vsdx as vsdx_lib
        except ImportError:
            raise ImportError(
                "vsdx is required for Visio extraction. "
                "Install with: uv add vsdx"
            )

        warnings: list[str] = []
        path = Path(file_path)

        if not path.exists():
            raise ValueError(f"File not found: {file_path}")

        if path.stat().st_size == 0:
            raise ValueError("Empty Visio file")

        # HIGH-9: Zip bomb protection — scan member sizes before opening
        try:
            with zipfile.ZipFile(str(path), 'r') as zf:
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                if total_uncompressed > MAX_UNCOMPRESSED_SIZE:
                    raise ValueError(
                        f"Visio file uncompressed size ({total_uncompressed} bytes) "
                        f"exceeds limit ({MAX_UNCOMPRESSED_SIZE} bytes)"
                    )
        except zipfile.BadZipFile:
            raise ValueError("File is not a valid Visio file (bad ZIP format)")
        except ValueError:
            raise  # Re-raise our own ValueError
        except Exception as exc:
            raise ValueError(f"Failed to inspect Visio ZIP structure: {exc}")

        try:
            doc = vsdx_lib.VisioFile(str(path))
        except BadZipFile:
            raise ValueError("File is not a valid Visio file (bad ZIP format)")
        except Exception as exc:
            err_str = str(exc).lower()
            if "xml" in err_str:
                raise ValueError(f"Invalid Visio XML structure: {exc}")
            raise ValueError(f"Failed to open Visio file: {exc}")

        pages = doc.pages
        if not pages:
            return VisioResult(
                markdown="*Empty Visio document*\n",
                warnings=warnings,
            )

        sections: list[str] = []
        total_shapes = 0
        total_connections = 0

        for page in pages:
            page_name = getattr(page, "name", None) or f"Page {len(sections) + 1}"
            section_lines: list[str] = [f"## Page: {page_name}\n"]

            # Extract shapes
            shapes_lines: list[str] = []
            shape_text_map: dict[str, str] = {}  # shape_id -> text

            try:
                flat_shapes = self._get_all_shapes(page)
            except Exception as exc:
                warnings.append(f"Error reading shapes on page '{page_name}': {exc}")
                flat_shapes = []

            # MED-18: Cap total shapes to prevent excessive processing
            if len(flat_shapes) > MAX_SHAPES:
                warnings.append(
                    f"Page '{page_name}' has {len(flat_shapes)} shapes; "
                    f"truncated to {MAX_SHAPES}."
                )
                flat_shapes = flat_shapes[:MAX_SHAPES]

            for shape in flat_shapes:
                shape_id = getattr(shape, "ID", None) or str(id(shape))
                text = ""
                try:
                    text = shape.text.strip() if shape.text else ""
                except Exception:
                    pass

                if text:
                    total_shapes += 1
                    shape_text_map[str(shape_id)] = text
                    # Escape pipe characters in text
                    safe_text = text.replace("\n", " ").replace("|", "\\|")
                    shapes_lines.append(f"- **{shape_id}**: {safe_text}")

            if shapes_lines:
                section_lines.append("### Shapes\n")
                section_lines.extend(shapes_lines)
                section_lines.append("")

            # Extract connections
            conn_lines: list[str] = []
            try:
                connects = self._get_connects(page)
            except Exception as exc:
                warnings.append(f"Error reading connections on page '{page_name}': {exc}")
                connects = []

            for from_id, to_id in connects:
                from_text = shape_text_map.get(str(from_id), f"Shape {from_id}")
                to_text = shape_text_map.get(str(to_id), f"Shape {to_id}")
                from_safe = from_text.replace("\n", " ")
                to_safe = to_text.replace("\n", " ")
                conn_lines.append(f"- {from_safe} --> {to_safe}")
                total_connections += 1

            if conn_lines:
                section_lines.append("### Connections\n")
                section_lines.extend(conn_lines)
                section_lines.append("")

            if shapes_lines or conn_lines:
                sections.append("\n".join(section_lines))

        markdown = "\n\n".join(sections) if sections else "*Empty Visio document*\n"

        return VisioResult(
            markdown=markdown,
            page_count=len(pages),
            shape_count=total_shapes,
            connection_count=total_connections,
            warnings=warnings,
        )

    def _get_all_shapes(self, page, _depth: int = 0) -> list:
        """Recursively get all shapes from a page, including sub-shapes.

        HIGH-9: Recursion depth limit to prevent stack overflow from
        deeply nested grouped shapes.
        """
        if _depth > MAX_SHAPE_RECURSION_DEPTH:
            return []

        shapes = []
        try:
            for shape in page.child_shapes:
                shapes.append(shape)
                # Recurse into grouped shapes with depth tracking
                try:
                    sub_shapes = shape.sub_shapes()
                    if sub_shapes:
                        for sub in sub_shapes:
                            shapes.append(sub)
                            # Check sub-shapes of sub-shapes (groups within groups)
                            try:
                                nested = sub.sub_shapes()
                                if nested and _depth + 1 < MAX_SHAPE_RECURSION_DEPTH:
                                    shapes.extend(nested)
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass
        return shapes

    def _get_connects(self, page) -> list[tuple[str, str]]:
        """Extract connection pairs from a page.

        Returns list of (from_shape_id, to_shape_id) tuples.
        """
        connections: list[tuple[str, str]] = []
        try:
            connects = page.connects
            if not connects:
                return connections

            # Group by connector shape: each connector has two connects
            # (from_sheet -> connector, connector -> to_sheet)
            connector_map: dict[str, list[str]] = {}
            for connect in connects:
                from_sheet = getattr(connect, "from_id", None) or getattr(connect, "from_sheet", None)
                to_sheet = getattr(connect, "to_id", None) or getattr(connect, "to_sheet", None)
                if from_sheet and to_sheet:
                    key = str(from_sheet)
                    if key not in connector_map:
                        connector_map[key] = []
                    connector_map[key].append(str(to_sheet))

            # Simple heuristic: pairs of connected shapes
            seen: set[tuple[str, str]] = set()
            for from_id, to_ids in connector_map.items():
                for to_id in to_ids:
                    pair = (from_id, to_id)
                    if pair not in seen:
                        seen.add(pair)
                        connections.append(pair)

        except Exception:
            pass

        return connections
