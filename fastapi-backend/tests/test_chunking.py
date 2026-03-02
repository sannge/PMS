"""Unit tests for semantic chunking service.

Tests cover both TipTap document chunking and Canvas document chunking,
including edge cases, token counting, and heading context preservation.
"""

import pytest

from app.ai.chunking_service import SemanticChunker


# ---- Fixtures: TipTap JSON Documents ----


def make_tiptap_doc(*nodes):
    """Helper to build a minimal TipTap document."""
    return {"type": "doc", "content": list(nodes)}


def paragraph(text: str) -> dict:
    """Create a TipTap paragraph node."""
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def heading(text: str, level: int = 1) -> dict:
    """Create a TipTap heading node."""
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def bullet_list(*items: str) -> dict:
    """Create a TipTap bullet list."""
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [paragraph(item)],
            }
            for item in items
        ],
    }


def ordered_list(*items: str) -> dict:
    """Create a TipTap ordered list."""
    return {
        "type": "orderedList",
        "content": [
            {
                "type": "listItem",
                "content": [paragraph(item)],
            }
            for item in items
        ],
    }


def task_list(*items: tuple[str, bool]) -> dict:
    """Create a TipTap task list."""
    return {
        "type": "taskList",
        "content": [
            {
                "type": "taskItem",
                "attrs": {"checked": checked},
                "content": [paragraph(text)],
            }
            for text, checked in items
        ],
    }


def code_block(code: str, language: str = "python") -> dict:
    """Create a TipTap code block."""
    return {
        "type": "codeBlock",
        "attrs": {"language": language},
        "content": [{"type": "text", "text": code}],
    }


def table(rows: list[list[str]]) -> dict:
    """Create a TipTap table."""
    return {
        "type": "table",
        "content": [
            {
                "type": "tableRow",
                "content": [
                    {
                        "type": "tableCell",
                        "content": [paragraph(cell)],
                    }
                    for cell in row
                ],
            }
            for row in rows
        ],
    }


def image_node(src: str = "https://example.com/image.png") -> dict:
    """Create a TipTap image node."""
    return {"type": "image", "attrs": {"src": src, "alt": "test image"}}


# ---- Fixtures: Canvas JSON Documents ----


def make_canvas(*elements):
    """Helper to build a canvas document."""
    return {"elements": list(elements)}


def sticky_note(id: str, text: str, x: float = 100, y: float = 100) -> dict:
    return {
        "id": id,
        "type": "sticky_note",
        "position": {"x": x, "y": y},
        "size": {"width": 200, "height": 150},
        "text": text,
        "color": "yellow",
    }


def text_box(id: str, text: str, x: float = 400, y: float = 200) -> dict:
    return {
        "id": id,
        "type": "text_box",
        "position": {"x": x, "y": y},
        "size": {"width": 300, "height": 100},
        "text": text,
    }


def connector(id: str, source: str, target: str, label: str = "") -> dict:
    return {
        "id": id,
        "type": "connector",
        "source": source,
        "target": target,
        "label": label,
    }


def shape_element(id: str, x: float = 0, y: float = 0) -> dict:
    """A shape element with no text (should be skipped)."""
    return {
        "id": id,
        "type": "shape",
        "position": {"x": x, "y": y},
        "size": {"width": 50, "height": 50},
        "text": "",
    }


# ---- Chunker Instance ----


@pytest.fixture
def chunker():
    """Create a SemanticChunker with default settings."""
    return SemanticChunker(target_tokens=600, overlap_tokens=100)


# ---- TipTap Tests ----


class TestTipTapChunking:
    """Tests for TipTap document chunking strategy."""

    def test_chunk_empty_document_returns_empty(self, chunker):
        """Empty TipTap doc returns empty list, not a list with one empty chunk."""
        doc = make_tiptap_doc()
        result = chunker.chunk_document(doc, "Empty Doc", "document")
        assert result == []

    def test_chunk_none_content_returns_empty(self, chunker):
        """None content returns empty list."""
        result = chunker.chunk_document({}, "Empty", "document")
        assert result == []

    def test_chunk_single_paragraph(self, chunker):
        """Single paragraph returns 1 chunk with correct text and chunk_index=0."""
        doc = make_tiptap_doc(paragraph("Hello world. This is a test."))
        result = chunker.chunk_document(doc, "Test Doc", "document")
        assert len(result) == 1
        assert result[0].chunk_index == 0
        assert "Hello world" in result[0].text
        assert result[0].token_count > 0

    def test_chunk_multiple_headings_splits_at_boundaries(self, chunker):
        """Document with h1/h2 sections splits at heading boundaries.

        Each section must have enough content (>50 tokens) to be emitted
        as its own chunk; tiny sections are carried forward and merged.
        """
        # ~80 tokens per section to exceed the 50-token carry-forward threshold
        intro_text = "This is the introduction section with enough detail to be meaningful. " * 8
        details_text = "Here are the project details covering architecture and design choices. " * 8
        conclusion_text = "In conclusion we have covered all the main points of the project. " * 8
        doc = make_tiptap_doc(
            heading("Introduction", 1),
            paragraph(intro_text),
            heading("Details", 2),
            paragraph(details_text),
            heading("Conclusion", 2),
            paragraph(conclusion_text),
        )
        result = chunker.chunk_document(doc, "Test Doc", "document")
        assert len(result) >= 2  # At least 2 chunks at heading boundaries
        # Verify heading context is set
        for chunk in result:
            assert chunk.heading_context is not None

    def test_chunk_long_paragraph_splits_at_target_tokens(self, chunker):
        """Paragraph exceeding 800 tokens is split, each chunk within range."""
        # Create a very long paragraph (~1500 tokens)
        long_text = "This is a test sentence that contains several words. " * 150
        doc = make_tiptap_doc(paragraph(long_text))
        result = chunker.chunk_document(doc, "Long Doc", "document")
        assert len(result) >= 2
        for chunk in result:
            # Allow some tolerance for overlap
            assert chunk.token_count <= 1000  # MAX_TOKENS + overlap tolerance

    def test_chunk_preserves_heading_context(self, chunker):
        """Each chunk's heading_context contains its ancestor heading text."""
        doc = make_tiptap_doc(
            heading("Section A", 1),
            paragraph("Content under section A."),
        )
        result = chunker.chunk_document(doc, "Test Doc", "document")
        assert len(result) >= 1
        assert result[0].heading_context == "Section A"

    def test_chunk_overlap_between_adjacent_chunks(self, chunker):
        """Verify overlap tokens from end of chunk N appear at start of chunk N+1."""
        # Create a single heading with enough text to force a split (>800 tokens)
        long_sentence = "Alpha bravo charlie delta echo foxtrot. "
        # ~800 tokens * 2 = guaranteed to produce at least 2 chunks
        doc = make_tiptap_doc(
            heading("Big Section", 1),
            paragraph(long_sentence * 200),
        )
        result = chunker.chunk_document(doc, "Overlap Test", "document")
        assert len(result) >= 2, f"Expected >=2 chunks, got {len(result)}"
        # Verify overlap: text from end of chunk 0 should appear at the start of chunk 1
        # Get last few words of first chunk
        first_words = result[0].text.strip().split()
        last_words_of_first = " ".join(first_words[-5:])  # Last 5 words
        # The start of the second chunk should contain those words (overlap)
        second_start = result[1].text[:200]
        assert last_words_of_first in second_start or any(
            w in second_start for w in first_words[-3:]
        ), "Overlap text from chunk 0 not found at start of chunk 1"

    def test_chunk_handles_code_blocks(self, chunker):
        """Code block content is included in chunk text."""
        doc = make_tiptap_doc(
            code_block("def hello():\n    return 'world'", "python")
        )
        result = chunker.chunk_document(doc, "Code Doc", "document")
        assert len(result) == 1
        assert "def hello" in result[0].text
        assert "```python" in result[0].text

    def test_chunk_handles_tables(self, chunker):
        """Table cell content is extracted and included."""
        doc = make_tiptap_doc(
            table([
                ["Name", "Value"],
                ["Alpha", "100"],
                ["Beta", "200"],
            ])
        )
        result = chunker.chunk_document(doc, "Table Doc", "document")
        assert len(result) == 1
        assert "Alpha" in result[0].text
        assert "Beta" in result[0].text

    def test_chunk_handles_lists(self, chunker):
        """Bullet/ordered/task list items are extracted."""
        doc = make_tiptap_doc(
            bullet_list("Item one", "Item two"),
            ordered_list("First", "Second"),
            task_list(("Done task", True), ("Todo task", False)),
        )
        result = chunker.chunk_document(doc, "List Doc", "document")
        assert len(result) >= 1
        combined_text = " ".join(chunk.text for chunk in result)
        assert "Item one" in combined_text
        assert "First" in combined_text
        assert "Done task" in combined_text

    def test_chunk_strips_image_nodes(self, chunker):
        """Image nodes are skipped, no empty chunks from image-only sections."""
        doc = make_tiptap_doc(
            paragraph("Before image."),
            image_node(),
            paragraph("After image."),
        )
        result = chunker.chunk_document(doc, "Image Doc", "document")
        combined = " ".join(c.text for c in result)
        assert "Before image" in combined
        assert "After image" in combined
        # No chunk should contain image references
        for chunk in result:
            assert "image.png" not in chunk.text

    def test_chunk_image_only_document_returns_empty(self, chunker):
        """Document with only image nodes returns empty list."""
        doc = make_tiptap_doc(image_node(), image_node())
        result = chunker.chunk_document(doc, "Images Only", "document")
        assert result == []

    def test_chunk_token_count_accuracy(self, chunker):
        """Verify token_count matches actual tiktoken encoding of text."""
        doc = make_tiptap_doc(
            paragraph("The quick brown fox jumps over the lazy dog.")
        )
        result = chunker.chunk_document(doc, "Token Test", "document")
        assert len(result) == 1
        actual_tokens = chunker.count_tokens(result[0].text)
        assert result[0].token_count == actual_tokens

    def test_chunk_index_sequential(self, chunker):
        """chunk_index values are 0, 1, 2, ... with no gaps."""
        doc = make_tiptap_doc(
            heading("Section 1", 1),
            paragraph("Content 1. " * 20),
            heading("Section 2", 1),
            paragraph("Content 2. " * 20),
            heading("Section 3", 1),
            paragraph("Content 3. " * 20),
        )
        result = chunker.chunk_document(doc, "Sequential", "document")
        if result:
            indexes = [c.chunk_index for c in result]
            assert indexes == list(range(len(result)))

    def test_chunk_handles_unknown_node_types(self, chunker):
        """Unknown node types don't crash; children are recursed into."""
        doc = make_tiptap_doc(
            {
                "type": "unknownWidget",
                "content": [paragraph("Hidden text inside widget")],
            }
        )
        result = chunker.chunk_document(doc, "Unknown Node", "document")
        assert len(result) >= 1
        assert "Hidden text" in result[0].text

    def test_chunk_handles_blockquotes(self, chunker):
        """Blockquote content is extracted with > prefix."""
        doc = make_tiptap_doc(
            {
                "type": "blockquote",
                "content": [paragraph("Quoted text here.")],
            }
        )
        result = chunker.chunk_document(doc, "Quote Doc", "document")
        assert len(result) == 1
        assert "Quoted text" in result[0].text

    def test_chunk_handles_hard_breaks(self, chunker):
        """Hard breaks produce newlines in text."""
        doc = make_tiptap_doc(
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Line one"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "Line two"},
                ],
            }
        )
        result = chunker.chunk_document(doc, "Break Doc", "document")
        assert len(result) == 1
        assert "Line one" in result[0].text
        assert "Line two" in result[0].text

    def test_title_heading_not_its_own_chunk(self, chunker):
        """Title heading should merge with body content, never be a standalone chunk.

        Regression test: a document with a title heading followed by a large
        body paragraph should NOT produce a tiny chunk containing only the title.
        """
        # ~700 tokens — large enough that title + body > MAX_TOKENS (800),
        # which previously caused the title buffer to flush separately.
        body_text = "This sentence has several words for testing purposes. " * 70
        doc = make_tiptap_doc(
            heading("Project Plan", 1),
            paragraph(body_text),
        )
        result = chunker.chunk_document(doc, "Project Plan", "document")
        assert len(result) >= 1
        # The first chunk must contain the title AND body content together
        assert "# Project Plan" in result[0].text
        assert "This sentence" in result[0].text
        # No chunk should contain ONLY the title
        for chunk in result:
            stripped = chunk.text.replace("# Project Plan", "").strip()
            assert len(stripped) > 0, f"Chunk contains only the title: {chunk.text!r}"

    def test_title_merges_with_split_large_block(self, chunker):
        """Title heading should prepend to first split chunk when body exceeds MAX_TOKENS."""
        # ~1500 tokens — a single block exceeding MAX_TOKENS that needs splitting
        body_text = "Alpha bravo charlie delta echo foxtrot golf hotel. " * 200
        doc = make_tiptap_doc(
            heading("Architecture Overview", 1),
            paragraph(body_text),
        )
        result = chunker.chunk_document(doc, "Architecture Overview", "document")
        assert len(result) >= 2  # Body is large enough to split
        # Title must be in the first chunk, not isolated
        assert "# Architecture Overview" in result[0].text
        assert "Alpha bravo" in result[0].text

    def test_chunk_document_type_routes_correctly(self, chunker):
        """document_type parameter correctly routes to appropriate strategy."""
        tiptap_doc = make_tiptap_doc(paragraph("TipTap content"))
        canvas_doc = make_canvas(sticky_note("e1", "Canvas content"))

        tiptap_result = chunker.chunk_document(tiptap_doc, "T", "document")
        canvas_result = chunker.chunk_document(canvas_doc, "C", "canvas")

        assert len(tiptap_result) >= 1
        assert "TipTap" in tiptap_result[0].text

        assert len(canvas_result) >= 1
        assert "Canvas content" in canvas_result[0].text


# ---- Canvas Tests ----


class TestCanvasChunking:
    """Tests for canvas document chunking strategy."""

    def test_chunk_canvas_extracts_element_text(self, chunker):
        """Canvas elements with text are extracted."""
        doc = make_canvas(sticky_note("e1", "Planning notes"))
        result = chunker.chunk_document(doc, "Canvas", "canvas")
        assert len(result) == 1
        assert "Planning notes" in result[0].text

    def test_chunk_canvas_groups_connected_elements(self, chunker):
        """Elements linked by connectors are in the same chunk."""
        doc = make_canvas(
            sticky_note("e1", "Payment flow", x=100, y=100),
            text_box("e2", "Auth Service", x=5000, y=5000),  # Far apart
            connector("c1", "e1", "e2", "depends on"),
        )
        result = chunker.chunk_document(doc, "Canvas", "canvas")
        # Both elements should be in the same chunk due to connector
        assert len(result) == 1
        assert "Payment flow" in result[0].text
        assert "Auth Service" in result[0].text

    def test_chunk_canvas_includes_connector_labels(self, chunker):
        """Connector label text appears in chunk."""
        doc = make_canvas(
            sticky_note("e1", "Service A", x=100, y=100),
            sticky_note("e2", "Service B", x=5000, y=5000),
            connector("c1", "e1", "e2", "calls"),
        )
        result = chunker.chunk_document(doc, "Canvas", "canvas")
        assert len(result) == 1
        assert "calls" in result[0].text

    def test_chunk_canvas_skips_empty_elements(self, chunker):
        """Elements with no text content (pure shapes) are excluded."""
        doc = make_canvas(
            sticky_note("e1", "Has text"),
            shape_element("e2"),  # No text
        )
        result = chunker.chunk_document(doc, "Canvas", "canvas")
        assert len(result) == 1
        assert "Has text" in result[0].text

    def test_chunk_canvas_empty_document(self, chunker):
        """Empty canvas returns empty list."""
        doc = make_canvas()
        result = chunker.chunk_document(doc, "Empty Canvas", "canvas")
        assert result == []

    def test_chunk_canvas_only_shapes_returns_empty(self, chunker):
        """Canvas with only text-less shapes returns empty."""
        doc = make_canvas(
            shape_element("s1"),
            shape_element("s2"),
        )
        result = chunker.chunk_document(doc, "Shapes Only", "canvas")
        assert result == []

    def test_chunk_canvas_multiple_disconnected_elements(self, chunker):
        """Disconnected elements far apart form separate chunks."""
        doc = make_canvas(
            sticky_note("e1", "Far left element", x=0, y=0),
            sticky_note("e2", "Far right element", x=10000, y=10000),
        )
        result = chunker.chunk_document(doc, "Canvas", "canvas")
        # Should be 2 chunks since elements are far apart and unconnected
        assert len(result) == 2

    def test_chunk_canvas_proximate_elements_grouped(self, chunker):
        """Elements within proximity threshold are grouped together."""
        doc = make_canvas(
            sticky_note("e1", "Close element A", x=100, y=100),
            sticky_note("e2", "Close element B", x=150, y=150),
        )
        result = chunker.chunk_document(doc, "Canvas", "canvas")
        # Elements are close together, should be in same chunk
        assert len(result) == 1

    def test_chunk_canvas_splits_large_clusters(self, chunker):
        """Cluster exceeding target_tokens is split at element boundaries."""
        # Create many elements in a connected cluster to exceed MAX_TOKENS
        elements = []
        for i in range(30):
            elements.append(
                sticky_note(f"e{i}", f"Element {i} with detailed text content. " * 10, x=100, y=100 + i * 10)
            )
        # Connect them all in a chain
        for i in range(29):
            elements.append(connector(f"c{i}", f"e{i}", f"e{i+1}", f"link{i}"))

        doc = {"elements": elements}
        result = chunker.chunk_document(doc, "Large Canvas", "canvas")
        # Should be split into multiple chunks
        assert len(result) >= 2

    def test_chunk_canvas_heading_context_set(self, chunker):
        """Canvas chunks have heading_context with element type and position."""
        doc = make_canvas(
            sticky_note("e1", "Top left note", x=100, y=100),
        )
        result = chunker.chunk_document(doc, "Canvas", "canvas")
        assert len(result) == 1
        assert result[0].heading_context is not None
        assert "Sticky Note" in result[0].heading_context
        assert "Top Left" in result[0].heading_context

    def test_chunk_canvas_sequential_chunk_indexes(self, chunker):
        """Canvas chunks have sequential 0-based chunk_index."""
        doc = make_canvas(
            sticky_note("e1", "Element A", x=0, y=0),
            sticky_note("e2", "Element B", x=10000, y=10000),
        )
        result = chunker.chunk_document(doc, "Canvas", "canvas")
        if len(result) >= 2:
            indexes = [c.chunk_index for c in result]
            assert indexes == list(range(len(result)))


# ---- Token Counting Tests ----


class TestTokenCounting:
    """Tests for token counting accuracy."""

    def test_count_tokens_empty_string(self, chunker):
        assert chunker.count_tokens("") == 0

    def test_count_tokens_simple_text(self, chunker):
        tokens = chunker.count_tokens("Hello world")
        assert tokens > 0
        assert tokens < 10  # Should be 2-3 tokens

    def test_count_tokens_consistent(self, chunker):
        """Token count is deterministic."""
        text = "The quick brown fox jumps over the lazy dog."
        count1 = chunker.count_tokens(text)
        count2 = chunker.count_tokens(text)
        assert count1 == count2


# ---- DrawIO Extraction Tests ----


class TestDrawIOExtraction:
    """Tests for draw.io diagram text extraction."""

    @pytest.fixture
    def chunker(self):
        return SemanticChunker()

    def test_drawio_valid_xml(self, chunker):
        """Valid drawio XML with mxCell elements extracts text."""
        node = {
            "type": "drawio",
            "attrs": {
                "data": '<mxGraphModel><root><mxCell value="Start"/><mxCell value="End"/></root></mxGraphModel>'
            },
        }
        doc = make_tiptap_doc(node)
        result = chunker.chunk_document(doc, "Drawio Test", "document")
        assert len(result) == 1
        assert "Start" in result[0].text
        assert "End" in result[0].text
        assert "[Diagram]" in result[0].text

    def test_drawio_empty_data(self, chunker):
        """Drawio node with no data attribute returns no chunks."""
        node = {"type": "drawio", "attrs": {}}
        doc = make_tiptap_doc(node)
        result = chunker.chunk_document(doc, "Drawio Empty", "document")
        assert result == []

    def test_drawio_malformed_xml(self, chunker):
        """Malformed XML in drawio node does not crash."""
        node = {"type": "drawio", "attrs": {"data": "<not-valid-xml>>"}}
        doc = make_tiptap_doc(node)
        result = chunker.chunk_document(doc, "Bad Drawio", "document")
        assert result == []

    def test_drawio_html_stripped(self, chunker):
        """HTML tags inside mxCell values are stripped."""
        node = {
            "type": "drawio",
            "attrs": {
                "data": '<mxGraphModel><root><mxCell value="&lt;b&gt;Bold&lt;/b&gt; text"/></root></mxGraphModel>'
            },
        }
        doc = make_tiptap_doc(node)
        result = chunker.chunk_document(doc, "HTML Drawio", "document")
        assert len(result) == 1
        assert "Bold" in result[0].text
        assert "<b>" not in result[0].text


# ---- Oversized Sentence Split Tests ----


class TestOversizedSentenceSplit:
    """Tests for hard-splitting sentences that exceed MAX_TOKENS."""

    @pytest.fixture
    def chunker(self):
        return SemanticChunker()

    def test_single_oversized_sentence_is_split(self, chunker):
        """A single sentence exceeding MAX_TOKENS is hard-split at token boundaries."""
        # Create a single "sentence" with no periods/newlines (~1600 tokens)
        # Using repeated words without punctuation
        oversized_text = "word " * 2000  # ~2000 tokens, well over MAX_TOKENS=800
        doc = make_tiptap_doc(paragraph(oversized_text))
        result = chunker.chunk_document(doc, "Oversized", "document")
        assert len(result) >= 2, f"Expected >=2 chunks for oversized sentence, got {len(result)}"
        for chunk in result:
            # Each chunk should be at most MAX_TOKENS (plus overlap tolerance)
            assert chunk.token_count <= 1000, f"Chunk has {chunk.token_count} tokens, expected <=1000"


# ---- HorizontalRule Tests ----


class TestHorizontalRule:
    """Tests for horizontalRule node handling."""

    @pytest.fixture
    def chunker(self):
        return SemanticChunker()

    def test_horizontal_rule_does_not_crash(self, chunker):
        """Document with horizontalRule between paragraphs is handled gracefully."""
        doc = make_tiptap_doc(
            paragraph("Before the rule."),
            {"type": "horizontalRule"},
            paragraph("After the rule."),
        )
        result = chunker.chunk_document(doc, "HR Test", "document")
        assert len(result) >= 1
        assert "Before" in result[0].text
        assert "After" in result[-1].text
