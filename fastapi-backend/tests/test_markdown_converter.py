"""Tests for markdown_to_tiptap_json converter in worker.py."""

from app.worker import markdown_to_tiptap_json


class TestMarkdownToTiptapJson:
    """Tests for the markdown to TipTap JSON converter."""

    def test_empty_markdown_returns_empty_paragraph(self):
        """Empty markdown should return doc with at least one empty paragraph."""
        result = markdown_to_tiptap_json("")
        assert result["type"] == "doc"
        assert len(result["content"]) >= 1

    def test_heading_levels(self):
        """Test H1 through H6 heading conversion."""
        for level in range(1, 7):
            md = f"{'#' * level} Heading {level}"
            result = markdown_to_tiptap_json(md)
            heading = result["content"][0]
            assert heading["type"] == "heading"
            assert heading["attrs"]["level"] == level

    def test_paragraph(self):
        """Plain text becomes a paragraph."""
        result = markdown_to_tiptap_json("Hello world")
        para = result["content"][0]
        assert para["type"] == "paragraph"
        assert para["content"][0]["text"] == "Hello world"

    def test_bold_text(self):
        """**bold** becomes text with bold mark."""
        result = markdown_to_tiptap_json("This is **bold** text")
        para = result["content"][0]
        texts = para["content"]
        bold_nodes = [t for t in texts if any(m.get("type") == "bold" for m in t.get("marks", []))]
        assert len(bold_nodes) >= 1
        assert bold_nodes[0]["text"] == "bold"

    def test_italic_text(self):
        """*italic* becomes text with italic mark."""
        result = markdown_to_tiptap_json("This is *italic* text")
        para = result["content"][0]
        texts = para["content"]
        italic_nodes = [t for t in texts if any(m.get("type") == "italic" for m in t.get("marks", []))]
        assert len(italic_nodes) >= 1

    def test_code_span(self):
        """`code` becomes text with code mark."""
        result = markdown_to_tiptap_json("Use `print()` function")
        para = result["content"][0]
        texts = para["content"]
        code_nodes = [t for t in texts if any(m.get("type") == "code" for m in t.get("marks", []))]
        assert len(code_nodes) >= 1

    def test_link(self):
        """[text](url) becomes text with link mark."""
        result = markdown_to_tiptap_json("Visit [Google](https://google.com) now")
        para = result["content"][0]
        texts = para["content"]
        link_nodes = [t for t in texts if any(m.get("type") == "link" for m in t.get("marks", []))]
        assert len(link_nodes) >= 1
        link_mark = link_nodes[0]["marks"][0]
        assert link_mark["attrs"]["href"] == "https://google.com"

    def test_bullet_list(self):
        """Bullet list items."""
        md = "- Item 1\n- Item 2\n- Item 3"
        result = markdown_to_tiptap_json(md)
        bullet = result["content"][0]
        assert bullet["type"] == "bulletList"
        assert len(bullet["content"]) == 3

    def test_ordered_list(self):
        """Numbered list items."""
        md = "1. First\n2. Second\n3. Third"
        result = markdown_to_tiptap_json(md)
        ordered = result["content"][0]
        assert ordered["type"] == "orderedList"
        assert len(ordered["content"]) == 3

    def test_code_block(self):
        """Fenced code block."""
        md = "```python\nprint('hello')\n```"
        result = markdown_to_tiptap_json(md)
        code = result["content"][0]
        assert code["type"] == "codeBlock"

    def test_blockquote(self):
        """> prefix becomes blockquote."""
        md = "> This is a quote"
        result = markdown_to_tiptap_json(md)
        bq = result["content"][0]
        assert bq["type"] == "blockquote"

    def test_horizontal_rule(self):
        """--- becomes horizontalRule."""
        md = "Before\n\n---\n\nAfter"
        result = markdown_to_tiptap_json(md)
        types = [n["type"] for n in result["content"]]
        assert "horizontalRule" in types

    def test_table(self):
        """Pipe table becomes TipTap table."""
        md = "| Col1 | Col2 |\n| --- | --- |\n| A | B |\n| C | D |"
        result = markdown_to_tiptap_json(md)
        table = result["content"][0]
        assert table["type"] == "table"
        assert len(table["content"]) >= 2  # header + data rows

    def test_mixed_content(self):
        """Multiple block types in sequence."""
        md = "# Title\n\nParagraph text.\n\n- List item\n\n> Quote"
        result = markdown_to_tiptap_json(md)
        types = [n["type"] for n in result["content"]]
        assert "heading" in types
        assert "paragraph" in types
        assert "bulletList" in types
        assert "blockquote" in types

    def test_unsafe_link_rendered_as_plain_text(self):
        """javascript: links are sanitized to plain text, not stored as links."""
        result = markdown_to_tiptap_json("[click me](javascript:alert(1))")
        para = result["content"][0]
        texts = para["content"]
        link_nodes = [t for t in texts if any(m.get("type") == "link" for m in t.get("marks", []))]
        assert len(link_nodes) == 0
        text_nodes = [t for t in texts if t.get("type") == "text"]
        assert any("click me" in t.get("text", "") for t in text_nodes)

    def test_data_uri_link_rendered_as_plain_text(self):
        """data: URI links are sanitized to plain text."""
        result = markdown_to_tiptap_json("[xss](data:text/html,<script>alert(1)</script>)")
        para = result["content"][0]
        texts = para["content"]
        link_nodes = [t for t in texts if any(m.get("type") == "link" for m in t.get("marks", []))]
        assert len(link_nodes) == 0
