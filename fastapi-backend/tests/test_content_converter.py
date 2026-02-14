"""Comprehensive test suite for TipTap JSON to Markdown and plain text converter.

Tests cover all node types from the knowledge base editor (editor-extensions.ts):
- Block: doc, paragraph, heading (1-6), bulletList, orderedList, listItem,
  taskList, taskItem, codeBlock, blockquote, table, horizontalRule
- Inline: text, hardBreak
- Marks: bold, italic, underline, strike, code, link, textStyle, highlight
"""

import pytest

from app.services.content_converter import (
    tiptap_json_to_markdown,
    tiptap_json_to_plain_text,
)


# ---------------------------------------------------------------------------
# Helper: wrap content in a doc node
# ---------------------------------------------------------------------------

def doc(*content: dict) -> dict:
    return {"type": "doc", "content": list(content)}


def paragraph(*content: dict) -> dict:
    return {"type": "paragraph", "content": list(content)}


def heading(level: int, *content: dict) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": list(content)}


def text(t: str, marks: list | None = None) -> dict:
    node: dict = {"type": "text", "text": t}
    if marks:
        node["marks"] = marks
    return node


def bold() -> dict:
    return {"type": "bold"}


def italic() -> dict:
    return {"type": "italic"}


def strike() -> dict:
    return {"type": "strike"}


def code_mark() -> dict:
    return {"type": "code"}


def underline() -> dict:
    return {"type": "underline"}


def link(href: str) -> dict:
    return {"type": "link", "attrs": {"href": href}}


def text_style(**attrs: str) -> dict:
    return {"type": "textStyle", "attrs": attrs}


def highlight(color: str) -> dict:
    return {"type": "highlight", "attrs": {"color": color}}


def bullet_list(*items: dict) -> dict:
    return {"type": "bulletList", "content": list(items)}


def ordered_list(*items: dict) -> dict:
    return {"type": "orderedList", "content": list(items)}


def list_item(*content: dict) -> dict:
    return {"type": "listItem", "content": list(content)}


def task_list(*items: dict) -> dict:
    return {"type": "taskList", "content": list(items)}


def task_item(checked: bool, *content: dict) -> dict:
    return {"type": "taskItem", "attrs": {"checked": checked}, "content": list(content)}


def code_block(code_text: str, language: str | None = None) -> dict:
    attrs: dict = {}
    if language is not None:
        attrs["language"] = language
    return {
        "type": "codeBlock",
        "attrs": attrs,
        "content": [text(code_text)],
    }


def blockquote(*content: dict) -> dict:
    return {"type": "blockquote", "content": list(content)}


def table(*rows: dict) -> dict:
    return {"type": "table", "content": list(rows)}


def table_row(*cells: dict) -> dict:
    return {"type": "tableRow", "content": list(cells)}


def table_header(*content: dict) -> dict:
    return {"type": "tableHeader", "content": list(content)}


def table_cell(*content: dict) -> dict:
    return {"type": "tableCell", "content": list(content)}


def hard_break() -> dict:
    return {"type": "hardBreak"}


def horizontal_rule() -> dict:
    return {"type": "horizontalRule"}


# ===========================================================================
# Markdown Tests
# ===========================================================================

class TestMarkdownEmpty:
    def test_empty_doc(self):
        assert tiptap_json_to_markdown(doc()) == ""

    def test_none_input(self):
        assert tiptap_json_to_markdown(None) == ""

    def test_empty_dict(self):
        assert tiptap_json_to_markdown({}) == ""

    def test_wrong_type(self):
        assert tiptap_json_to_markdown({"type": "notadoc"}) == ""


class TestMarkdownParagraph:
    def test_single_paragraph(self):
        result = tiptap_json_to_markdown(doc(paragraph(text("Hello world"))))
        assert result == "Hello world\n\n"

    def test_multiple_paragraphs(self):
        result = tiptap_json_to_markdown(doc(
            paragraph(text("First")),
            paragraph(text("Second")),
        ))
        assert result == "First\n\n" + "Second\n\n"

    def test_empty_paragraph(self):
        result = tiptap_json_to_markdown(doc({"type": "paragraph"}))
        assert result == "\n\n"


class TestMarkdownHeadings:
    def test_heading_level_1(self):
        result = tiptap_json_to_markdown(doc(heading(1, text("My Heading"))))
        assert result == "# My Heading\n\n"

    def test_heading_level_2(self):
        result = tiptap_json_to_markdown(doc(heading(2, text("My Heading"))))
        assert result == "## My Heading\n\n"

    def test_heading_level_3(self):
        result = tiptap_json_to_markdown(doc(heading(3, text("My Heading"))))
        assert result == "### My Heading\n\n"

    def test_heading_level_6(self):
        result = tiptap_json_to_markdown(doc(heading(6, text("My Heading"))))
        assert result == "###### My Heading\n\n"


class TestMarkdownMarks:
    def test_bold(self):
        result = tiptap_json_to_markdown(doc(paragraph(text("bold", [bold()]))))
        assert result == "**bold**\n\n"

    def test_italic(self):
        result = tiptap_json_to_markdown(doc(paragraph(text("italic", [italic()]))))
        assert result == "_italic_\n\n"

    def test_strike(self):
        result = tiptap_json_to_markdown(doc(paragraph(text("struck", [strike()]))))
        assert result == "~~struck~~\n\n"

    def test_inline_code(self):
        result = tiptap_json_to_markdown(doc(paragraph(text("code", [code_mark()]))))
        assert result == "`code`\n\n"

    def test_underline(self):
        result = tiptap_json_to_markdown(doc(paragraph(text("underlined", [underline()]))))
        assert result == "<u>underlined</u>\n\n"

    def test_link(self):
        result = tiptap_json_to_markdown(doc(paragraph(text("click", [link("https://example.com")]))))
        assert result == "[click](https://example.com)\n\n"

    def test_text_style_skipped(self):
        result = tiptap_json_to_markdown(doc(paragraph(text("styled", [text_style(fontSize="1.5rem")]))))
        assert result == "styled\n\n"

    def test_highlight_skipped(self):
        result = tiptap_json_to_markdown(doc(paragraph(text("highlighted", [highlight("#fef9c3")]))))
        assert result == "highlighted\n\n"

    def test_bold_and_italic(self):
        result = tiptap_json_to_markdown(doc(paragraph(
            text("bold", [bold()]),
            text(" "),
            text("italic", [italic()]),
        )))
        assert result == "**bold** _italic_\n\n"

    def test_combined_bold_italic_link(self):
        result = tiptap_json_to_markdown(doc(paragraph(
            text("click me", [bold(), italic(), link("https://ex.com")]),
        )))
        # Marks applied in order: bold wraps text, italic wraps bold, link wraps all
        assert result == "[_**click me**_](https://ex.com)\n\n"


class TestMarkdownBulletList:
    def test_simple_bullet_list(self):
        result = tiptap_json_to_markdown(doc(bullet_list(
            list_item(paragraph(text("one"))),
            list_item(paragraph(text("two"))),
        )))
        assert "- one\n" in result
        assert "- two\n" in result

    def test_nested_bullet_list(self):
        result = tiptap_json_to_markdown(doc(bullet_list(
            list_item(
                paragraph(text("parent")),
                bullet_list(
                    list_item(paragraph(text("child"))),
                ),
            ),
        )))
        assert "- parent\n" in result
        assert "  - child\n" in result

    def test_deeply_nested_list(self):
        result = tiptap_json_to_markdown(doc(bullet_list(
            list_item(
                paragraph(text("level 0")),
                bullet_list(
                    list_item(
                        paragraph(text("level 1")),
                        bullet_list(
                            list_item(paragraph(text("level 2"))),
                        ),
                    ),
                ),
            ),
        )))
        assert "- level 0\n" in result
        assert "  - level 1\n" in result
        assert "    - level 2\n" in result


class TestMarkdownOrderedList:
    def test_simple_ordered_list(self):
        result = tiptap_json_to_markdown(doc(ordered_list(
            list_item(paragraph(text("first"))),
            list_item(paragraph(text("second"))),
        )))
        assert "1. first\n" in result
        assert "2. second\n" in result


class TestMarkdownTaskList:
    def test_task_item_checked(self):
        result = tiptap_json_to_markdown(doc(task_list(
            task_item(True, paragraph(text("done"))),
        )))
        assert "- [x] done\n" in result

    def test_task_item_unchecked(self):
        result = tiptap_json_to_markdown(doc(task_list(
            task_item(False, paragraph(text("pending"))),
        )))
        assert "- [ ] pending\n" in result

    def test_mixed_task_list(self):
        result = tiptap_json_to_markdown(doc(task_list(
            task_item(True, paragraph(text("done"))),
            task_item(False, paragraph(text("pending"))),
        )))
        assert "- [x] done\n" in result
        assert "- [ ] pending\n" in result


class TestMarkdownCodeBlock:
    def test_code_block_with_language(self):
        result = tiptap_json_to_markdown(doc(code_block("print('hi')", "python")))
        assert result == "```python\nprint('hi')\n```\n\n"

    def test_code_block_plaintext_language(self):
        """Code blocks with 'plaintext' language should render bare fences."""
        result = tiptap_json_to_markdown(doc(code_block("some code", "plaintext")))
        assert result == "```\nsome code\n```\n\n"

    def test_code_block_no_language(self):
        """Code blocks with no language attr should render bare fences."""
        result = tiptap_json_to_markdown(doc(code_block("some code")))
        assert result == "```\nsome code\n```\n\n"

    def test_code_block_empty_language(self):
        """Code blocks with empty string language should render bare fences."""
        result = tiptap_json_to_markdown(doc(code_block("some code", "")))
        assert result == "```\nsome code\n```\n\n"


class TestMarkdownBlockquote:
    def test_simple_blockquote(self):
        result = tiptap_json_to_markdown(doc(blockquote(paragraph(text("quoted text")))))
        assert "> quoted text" in result

    def test_multiline_blockquote(self):
        result = tiptap_json_to_markdown(doc(blockquote(
            paragraph(text("line one")),
            paragraph(text("line two")),
        )))
        lines = [l for l in result.strip().split("\n") if l.strip()]
        assert all(l.startswith(">") for l in lines)


class TestMarkdownTable:
    def test_simple_table(self):
        result = tiptap_json_to_markdown(doc(table(
            table_row(
                table_header(paragraph(text("H1"))),
                table_header(paragraph(text("H2"))),
            ),
            table_row(
                table_cell(paragraph(text("A"))),
                table_cell(paragraph(text("B"))),
            ),
        )))
        assert "| H1 | H2 |" in result
        assert "| --- | --- |" in result
        assert "| A | B |" in result


class TestMarkdownHorizontalRule:
    def test_horizontal_rule(self):
        result = tiptap_json_to_markdown(doc(horizontal_rule()))
        assert result == "---\n\n"


class TestMarkdownHardBreak:
    def test_hard_break(self):
        result = tiptap_json_to_markdown(doc(paragraph(
            text("before"),
            hard_break(),
            text("after"),
        )))
        assert "before  \nafter" in result


class TestMarkdownUnknownNode:
    def test_unknown_node_renders_children(self):
        """Unknown node types should render their children without crashing."""
        result = tiptap_json_to_markdown(doc(
            {"type": "customWidget", "content": [paragraph(text("inner"))]}
        ))
        assert "inner" in result

    def test_unknown_node_no_content(self):
        """Unknown node with no content should not crash."""
        result = tiptap_json_to_markdown(doc({"type": "unknownEmpty"}))
        assert result == ""


# ===========================================================================
# Plain Text Tests
# ===========================================================================

class TestPlainTextBasic:
    def test_empty_doc(self):
        assert tiptap_json_to_plain_text(doc()) == ""

    def test_none_input(self):
        assert tiptap_json_to_plain_text(None) == ""

    def test_paragraph(self):
        result = tiptap_json_to_plain_text(doc(paragraph(text("Hello world"))))
        assert result == "Hello world"

    def test_heading(self):
        result = tiptap_json_to_plain_text(doc(heading(1, text("My Heading"))))
        assert result == "My Heading"


class TestPlainTextMarksStripped:
    def test_bold_stripped(self):
        result = tiptap_json_to_plain_text(doc(paragraph(text("bold", [bold()]))))
        assert result == "bold"
        assert "**" not in result

    def test_all_marks_stripped(self):
        result = tiptap_json_to_plain_text(doc(paragraph(
            text("b", [bold()]),
            text("i", [italic()]),
            text("s", [strike()]),
            text("c", [code_mark()]),
            text("u", [underline()]),
            text("l", [link("http://x.com")]),
        )))
        assert result == "biscul"


class TestPlainTextBlocks:
    def test_code_block_text_preserved(self):
        result = tiptap_json_to_plain_text(doc(code_block("print('hi')", "python")))
        assert "print('hi')" in result
        assert "```" not in result

    def test_multiple_paragraphs(self):
        result = tiptap_json_to_plain_text(doc(
            paragraph(text("First")),
            paragraph(text("Second")),
        ))
        assert "First" in result
        assert "Second" in result
        assert "\n" in result

    def test_hard_break(self):
        result = tiptap_json_to_plain_text(doc(paragraph(
            text("before"),
            hard_break(),
            text("after"),
        )))
        assert "before\nafter" in result

    def test_task_list_text_only(self):
        result = tiptap_json_to_plain_text(doc(task_list(
            task_item(True, paragraph(text("done"))),
            task_item(False, paragraph(text("pending"))),
        )))
        assert "done" in result
        assert "pending" in result
        assert "[" not in result
