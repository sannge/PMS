"""TipTap JSON to Markdown and plain text converter.

Converts ProseMirror JSON (TipTap's internal format) to Markdown for AI
consumption and plain text for full-text search indexing. Handles all node
types from the knowledge base editor (editor-extensions.ts).

Node types handled:
  Block: doc, paragraph, heading (1-6), bulletList, orderedList, listItem,
         taskList, taskItem, codeBlock, blockquote, table, tableRow,
         tableCell, tableHeader, horizontalRule, drawio
  Inline: text, hardBreak
  Marks: bold, italic, underline, strike, code, link
  Skipped (presentation-only): textStyle, highlight, indent, textAlign

Design decisions:
  - indent and textAlign attrs are presentation-only; skipped in Markdown
  - underline renders as <u>text</u> (no Markdown equivalent)
  - textStyle and highlight marks are skipped (presentation-only)
  - codeBlock with 'plaintext' or empty/null language renders bare ``` fences
  - drawio nodes: XML parsed to extract shape labels + arrow connections
  - Unknown node types render their children recursively (graceful degradation)
"""

import re
import xml.etree.ElementTree as ET
from typing import Any


# -- Markdown Conversion -------------------------------------------------------

_MARK_WRAPPERS: dict[str, str] = {
    "bold": "**",
    "italic": "_",
    "strike": "~~",
    "code": "`",
}


def tiptap_json_to_markdown(doc: dict[str, Any] | None) -> str:
    """Convert TipTap JSON document to Markdown string.

    Args:
        doc: TipTap JSON document dict with type="doc" at root,
             or a canvas document with format="canvas".

    Returns:
        Markdown string. Empty string for invalid/empty input.
    """
    if not doc:
        return ""
    if doc.get("format") == "canvas":
        return _canvas_to_markdown(doc)
    if doc.get("type") != "doc":
        return ""
    return _md_nodes(doc.get("content", []))


def _canvas_to_markdown(canvas: dict[str, Any]) -> str:
    """Extract markdown from all canvas containers, ordered by array index."""
    containers = canvas.get("containers")
    if not containers or not isinstance(containers, list):
        return ""
    parts: list[str] = []
    for i, container in enumerate(containers, 1):
        if not isinstance(container, dict):
            continue
        content = container.get("content")
        if not isinstance(content, dict) or content.get("type") != "doc":
            continue
        md = _md_nodes(content.get("content", []))
        if md.strip():
            parts.append(f"## Section {i}\n\n{md}")
    return "\n".join(parts)


def _md_nodes(nodes: list[dict[str, Any]], list_indent: int = 0) -> str:
    """Recursively convert a list of ProseMirror nodes to Markdown."""
    parts: list[str] = []
    for node in nodes:
        t = node.get("type", "")

        if t == "paragraph":
            text = _md_inline(node.get("content", []))
            parts.append(text + "\n\n")

        elif t == "heading":
            level = node.get("attrs", {}).get("level", 1)
            parts.append("#" * level + " " + _md_inline(node.get("content", [])) + "\n\n")

        elif t == "bulletList":
            for item in node.get("content", []):
                prefix = "  " * list_indent + "- "
                parts.append(prefix + _md_list_item(item, list_indent))
            parts.append("\n")

        elif t == "orderedList":
            for i, item in enumerate(node.get("content", []), 1):
                prefix = "  " * list_indent + f"{i}. "
                parts.append(prefix + _md_list_item(item, list_indent))
            parts.append("\n")

        elif t == "taskList":
            for item in node.get("content", []):
                checked = item.get("attrs", {}).get("checked", False)
                marker = "[x]" if checked else "[ ]"
                prefix = "  " * list_indent + f"- {marker} "
                parts.append(prefix + _md_list_item(item, list_indent))
            parts.append("\n")

        elif t == "codeBlock":
            lang = node.get("attrs", {}).get("language", "") or ""
            # Skip "plaintext" default language -- render as bare ```
            if lang == "plaintext":
                lang = ""
            code = _extract_text_from_nodes(node.get("content", []))
            parts.append(f"```{lang}\n{code}\n```\n\n")

        elif t == "blockquote":
            inner = _md_nodes(node.get("content", []))
            lines = inner.strip().split("\n")
            parts.append("\n".join("> " + line for line in lines) + "\n\n")

        elif t == "table":
            parts.append(_md_table(node) + "\n\n")

        elif t == "horizontalRule":
            parts.append("---\n\n")

        elif t == "drawio":
            parts.append(_md_drawio(node))

        else:
            # Unknown node -- render children if any (graceful degradation)
            if "content" in node:
                parts.append(_md_nodes(node["content"], list_indent))

    return "".join(parts)


def _md_inline(nodes: list[dict[str, Any]]) -> str:
    """Convert inline nodes (text + marks) to Markdown."""
    parts: list[str] = []
    for node in nodes:
        if node.get("type") == "text":
            text = node.get("text", "")
            for mark in node.get("marks", []):
                mark_type = mark.get("type", "")
                wrapper = _MARK_WRAPPERS.get(mark_type, "")
                if mark_type == "link":
                    href = mark.get("attrs", {}).get("href", "")
                    text = f"[{text}]({href})"
                elif mark_type == "underline":
                    text = f"<u>{text}</u>"
                elif wrapper:
                    text = f"{wrapper}{text}{wrapper}"
                # textStyle, highlight marks are presentation-only; skip
            parts.append(text)
        elif node.get("type") == "hardBreak":
            parts.append("  \n")
    return "".join(parts)


def _md_list_item(item: dict[str, Any], parent_indent: int) -> str:
    """Render a listItem/taskItem node, recursively handling nested lists."""
    content = item.get("content", [])
    parts: list[str] = []
    for i, child in enumerate(content):
        if child.get("type") in ("bulletList", "orderedList", "taskList"):
            # Nested list -- increase indent
            parts.append("\n" + _md_nodes([child], parent_indent + 1))
        elif child.get("type") == "paragraph":
            text = _md_inline(child.get("content", []))
            if i == 0:
                parts.append(text + "\n")
            else:
                # Continuation paragraph in list item
                parts.append("  " * (parent_indent + 1) + text + "\n")
        else:
            parts.append(_md_nodes([child], parent_indent + 1))
    return "".join(parts)


def _md_table(node: dict[str, Any]) -> str:
    """Render a table node to Markdown."""
    rows = node.get("content", [])
    if not rows:
        return ""

    md_rows: list[list[str]] = []
    for row in rows:
        cells = row.get("content", [])
        md_cells: list[str] = []
        for cell in cells:
            cell_content = _md_inline(
                cell.get("content", [{}])[0].get("content", [])
                if cell.get("content") else []
            )
            md_cells.append(cell_content.strip())
        md_rows.append(md_cells)

    if not md_rows:
        return ""

    # Build markdown table
    lines: list[str] = []
    # Header row
    lines.append("| " + " | ".join(md_rows[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in md_rows[0]) + " |")
    # Data rows
    for row in md_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


# -- Plain Text Extraction -----------------------------------------------------


def tiptap_json_to_plain_text(doc: dict[str, Any] | None) -> str:
    """Extract plain text from TipTap JSON document.

    Strips all formatting marks and returns clean text with newlines
    after block-level nodes.

    Args:
        doc: TipTap JSON document dict with type="doc" at root,
             or a canvas document with format="canvas".

    Returns:
        Plain text string. Empty string for invalid/empty input.
    """
    if not doc:
        return ""
    if doc.get("format") == "canvas":
        return _canvas_to_plain_text(doc)
    if doc.get("type") != "doc":
        return ""
    return _extract_text_from_nodes(doc.get("content", [])).strip()


def _canvas_to_plain_text(canvas: dict[str, Any]) -> str:
    """Extract plain text from all canvas containers for full-text search."""
    containers = canvas.get("containers")
    if not containers or not isinstance(containers, list):
        return ""
    parts: list[str] = []
    for container in containers:
        if not isinstance(container, dict):
            continue
        content = container.get("content")
        if not isinstance(content, dict) or content.get("type") != "doc":
            continue
        text = _extract_text_from_nodes(content.get("content", []))
        if text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def _extract_text_from_nodes(nodes: list[dict[str, Any]]) -> str:
    """Recursively extract text from nodes, adding newlines after blocks."""
    parts: list[str] = []
    for node in nodes:
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        elif node.get("type") == "hardBreak":
            parts.append("\n")
        elif node.get("type") == "drawio":
            parts.append(_extract_drawio_text(node.get("attrs", {})))
            parts.append("\n")
        elif "content" in node:
            parts.append(_extract_text_from_nodes(node["content"]))
            # Add newline after block-level nodes
            if node.get("type") in (
                "paragraph", "heading", "listItem", "taskItem",
                "codeBlock", "blockquote",
            ):
                parts.append("\n")
    return "".join(parts)


# -- Draw.io Helpers -----------------------------------------------------------


def _strip_html_tags(text: str) -> str:
    """Strip HTML tags from draw.io label text."""
    clean = re.sub(r"<[^>]+>", " ", text).strip()
    return re.sub(r"\s+", " ", clean)


def _extract_drawio_text(attrs: dict[str, Any]) -> str:
    """Extract plain text from draw.io XML data for Meilisearch indexing."""
    xml_data = attrs.get("data")
    if not xml_data:
        return ""

    try:
        root = ET.fromstring(xml_data)
        texts: list[str] = []
        for cell in root.iter("mxCell"):
            value = cell.get("value", "")
            if value:
                clean = _strip_html_tags(value)
                if clean:
                    texts.append(clean)
        return " ".join(texts)
    except ET.ParseError:
        return ""


def _md_drawio(node: dict[str, Any]) -> str:
    """Convert draw.io node to Markdown with shapes and connections."""
    attrs = node.get("attrs", {})
    xml_data = attrs.get("data")
    if not xml_data:
        return "**[Diagram]** *(empty)*\n\n"

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return "**[Diagram]** *(parse error)*\n\n"

    # Build cell map: id -> label
    cell_map: dict[str, str] = {}
    shapes: list[str] = []
    edges: list[tuple[str, str, str]] = []  # (source_id, edge_label, target_id)

    for cell in root.iter("mxCell"):
        cell_id = cell.get("id", "")
        value = cell.get("value", "")
        clean_value = _strip_html_tags(value) if value else ""

        if cell_id:
            cell_map[cell_id] = clean_value

        if cell.get("vertex") == "1" and clean_value:
            shapes.append(clean_value)
        elif cell.get("edge") == "1":
            source = cell.get("source", "")
            target = cell.get("target", "")
            edge_label = clean_value or "connected_to"
            edges.append((source, edge_label, target))

    parts: list[str] = ["**[Diagram]**\n"]

    if shapes:
        parts.append("Shapes:\n")
        for s in shapes:
            parts.append(f"  - {s}\n")

    if edges:
        parts.append("Connections:\n")
        for src_id, label, tgt_id in edges:
            src_name = cell_map.get(src_id, src_id)
            tgt_name = cell_map.get(tgt_id, tgt_id)
            if src_name and tgt_name:
                parts.append(f"  - {src_name} --[{label}]--> {tgt_name}\n")

    parts.append("\n")
    return "".join(parts)
