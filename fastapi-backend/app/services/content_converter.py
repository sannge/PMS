"""TipTap JSON to Markdown and plain text converter.

Converts ProseMirror JSON (TipTap's internal format) to Markdown for AI
consumption and plain text for full-text search indexing. Handles all node
types from the knowledge base editor (editor-extensions.ts).

Node types handled:
  Block: doc, paragraph, heading (1-6), bulletList, orderedList, listItem,
         taskList, taskItem, codeBlock, blockquote, table, tableRow,
         tableCell, tableHeader, horizontalRule
  Inline: text, hardBreak
  Marks: bold, italic, underline, strike, code, link
  Skipped (presentation-only): textStyle, highlight, indent, textAlign

Design decisions:
  - indent and textAlign attrs are presentation-only; skipped in Markdown
  - underline renders as <u>text</u> (no Markdown equivalent)
  - textStyle and highlight marks are skipped (presentation-only)
  - codeBlock with 'plaintext' or empty/null language renders bare ``` fences
  - Unknown node types render their children recursively (graceful degradation)
"""

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
        doc: TipTap JSON document dict with type="doc" at root.

    Returns:
        Markdown string. Empty string for invalid/empty input.
    """
    if not doc or doc.get("type") != "doc":
        return ""
    return _md_nodes(doc.get("content", []))


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
        doc: TipTap JSON document dict with type="doc" at root.

    Returns:
        Plain text string. Empty string for invalid/empty input.
    """
    if not doc or doc.get("type") != "doc":
        return ""
    return _extract_text_from_nodes(doc.get("content", [])).strip()


def _extract_text_from_nodes(nodes: list[dict[str, Any]]) -> str:
    """Recursively extract text from nodes, adding newlines after blocks."""
    parts: list[str] = []
    for node in nodes:
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        elif node.get("type") == "hardBreak":
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
