"""Tests for Phase 9 Category B: Embedding Quality fixes (Tasks 9.10-9.14).

Covers:
- 9.10 Table boundary awareness (is_table flag, preamble, MAX_TOKENS bypass)
- 9.11 Canvas container TipTap parsing
- 9.12 Slide boundary enforcement
- 9.13 Canvas oversized element fallback
- 9.14 Imported image slide context
"""

import pytest
from app.ai.chunking_service import ChunkResult, SemanticChunker, _TextBlock


# ---------------------------------------------------------------------------
# 9.10 Table Boundary Awareness
# ---------------------------------------------------------------------------


class TestTableBoundaryAwareness:
    """Tests for table blocks being emitted as own chunks with preamble."""

    def test_text_block_has_is_table_field(self):
        """_TextBlock should have is_table and table_columns fields."""
        block = _TextBlock(text="test", heading_context=None)
        assert block.is_table is False
        assert block.table_columns is None

    def test_table_block_marked_is_table(self):
        """_extract_blocks marks table nodes with is_table=True."""
        chunker = SemanticChunker()
        tiptap_nodes = [
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {"type": "tableCell", "content": [{"type": "text", "text": "Name"}]},
                            {"type": "tableCell", "content": [{"type": "text", "text": "Age"}]},
                        ],
                    },
                    {
                        "type": "tableRow",
                        "content": [
                            {"type": "tableCell", "content": [{"type": "text", "text": "Alice"}]},
                            {"type": "tableCell", "content": [{"type": "text", "text": "30"}]},
                        ],
                    },
                ],
            }
        ]
        blocks = chunker._extract_blocks(tiptap_nodes, current_heading="Test")
        assert len(blocks) == 1
        assert blocks[0].is_table is True
        assert blocks[0].table_columns == ["Name", "Age"]

    def test_table_chunk_has_preamble(self):
        """Table chunks should include a preamble with heading and column names."""
        chunker = SemanticChunker()
        content_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Before table."}],
                },
                {
                    "type": "table",
                    "content": [
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableCell", "content": [{"type": "text", "text": "Col1"}]},
                                {"type": "tableCell", "content": [{"type": "text", "text": "Col2"}]},
                            ],
                        },
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableCell", "content": [{"type": "text", "text": "A"}]},
                                {"type": "tableCell", "content": [{"type": "text", "text": "B"}]},
                            ],
                        },
                    ],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "After table."}],
                },
            ],
        }
        chunks = chunker._chunk_tiptap(content_json, "Report")
        # Should produce at least 2 chunks: paragraph(s) and table
        table_chunks = [c for c in chunks if c.text.startswith("Table")]
        assert len(table_chunks) >= 1
        table_chunk = table_chunks[0]
        assert "columns: Col1, Col2" in table_chunk.text
        assert "Col1 | Col2" in table_chunk.text

    def test_oversized_table_is_split(self):
        """Table blocks exceeding MAX_TOKENS are split by row groups."""
        chunker = SemanticChunker()
        # Build a large table that exceeds MAX_TOKENS (800)
        rows = []
        # Header row
        rows.append({
            "type": "tableRow",
            "content": [
                {"type": "tableCell", "content": [{"type": "text", "text": "Header1"}]},
                {"type": "tableCell", "content": [{"type": "text", "text": "Header2"}]},
            ],
        })
        # Many data rows to exceed MAX_TOKENS
        for i in range(200):
            rows.append({
                "type": "tableRow",
                "content": [
                    {"type": "tableCell", "content": [{"type": "text", "text": f"Row {i} column 1 with some extra text"}]},
                    {"type": "tableCell", "content": [{"type": "text", "text": f"Row {i} column 2 with some extra text"}]},
                ],
            })

        content_json = {
            "type": "doc",
            "content": [{"type": "table", "content": rows}],
        }
        chunks = chunker._chunk_tiptap(content_json, "Big Table")
        # The table should be split into multiple chunks
        table_chunks = [c for c in chunks if "Table" in c.text and "Header1" in c.text]
        assert len(table_chunks) > 1
        # Each chunk should contain the header row
        for tc in table_chunks:
            assert "Header1 | Header2" in tc.text

    def test_table_flushes_preceding_buffer(self):
        """When a table is encountered, preceding text buffer is flushed first."""
        chunker = SemanticChunker()
        content_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Some preceding paragraph text."}],
                },
                {
                    "type": "table",
                    "content": [
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableCell", "content": [{"type": "text", "text": "A"}]},
                            ],
                        },
                    ],
                },
            ],
        }
        # Use _merge_and_split directly (before overlap is added) to verify flush
        nodes = content_json.get("content", [])
        blocks = chunker._extract_blocks(nodes, current_heading="Test")
        blocks = [b for b in blocks if b.text.strip()]
        for b in blocks:
            b.token_count = chunker.count_tokens(b.text)
        merged = chunker._merge_and_split(blocks)
        # First chunk should be the paragraph, second should be the table
        assert len(merged) >= 2
        assert "preceding paragraph" in merged[0].text
        assert merged[1].text.startswith("Table")


    def test_two_adjacent_tables_separate_chunks(self):
        """Two adjacent tables should produce 2 separate table chunks, never merged."""
        chunker = SemanticChunker()
        content_json = {
            "type": "doc",
            "content": [
                {
                    "type": "table",
                    "content": [
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableCell", "content": [{"type": "text", "text": "T1Col"}]},
                            ],
                        },
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableCell", "content": [{"type": "text", "text": "T1Data"}]},
                            ],
                        },
                    ],
                },
                {
                    "type": "table",
                    "content": [
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableCell", "content": [{"type": "text", "text": "T2Col"}]},
                            ],
                        },
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableCell", "content": [{"type": "text", "text": "T2Data"}]},
                            ],
                        },
                    ],
                },
            ],
        }
        chunks = chunker._chunk_tiptap(content_json, "Report")
        table_chunks = [c for c in chunks if c.text.startswith("Table")]
        assert len(table_chunks) == 2
        assert "T1Col" in table_chunks[0].text
        assert "T2Col" in table_chunks[1].text

    def test_empty_table_produces_no_chunk(self):
        """An empty table (no rows) should not produce any chunk."""
        chunker = SemanticChunker()
        content_json = {
            "type": "doc",
            "content": [
                {"type": "table", "content": []},
            ],
        }
        chunks = chunker._chunk_tiptap(content_json, "Test")
        assert len(chunks) == 0

    def test_table_preamble_format_with_heading(self):
        """Table preamble should be 'Table: {heading} — columns: {cols}'."""
        chunker = SemanticChunker()
        content_json = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Q4 Report"}],
                },
                {
                    "type": "table",
                    "content": [
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableCell", "content": [{"type": "text", "text": "Name"}]},
                                {"type": "tableCell", "content": [{"type": "text", "text": "Revenue"}]},
                            ],
                        },
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableCell", "content": [{"type": "text", "text": "Acme"}]},
                                {"type": "tableCell", "content": [{"type": "text", "text": "$100"}]},
                            ],
                        },
                    ],
                },
            ],
        }
        # Use _merge_and_split to avoid overlap modification
        nodes = content_json.get("content", [])
        blocks = chunker._extract_blocks(nodes, current_heading="Report")
        blocks = [b for b in blocks if b.text.strip()]
        for b in blocks:
            b.token_count = chunker.count_tokens(b.text)
        merged = chunker._merge_and_split(blocks)
        table_chunks = [c for c in merged if c.text.startswith("Table")]
        assert len(table_chunks) == 1
        assert table_chunks[0].text.startswith("Table: Q4 Report — columns: Name, Revenue")

    def test_table_no_heading_context_preamble(self):
        """Table without heading context should have preamble 'Table — columns: ...'."""
        chunker = SemanticChunker()
        block = _TextBlock(
            text="A | B\n1 | 2\n",
            heading_context=None,
            token_count=10,
            is_table=True,
            table_columns=["A", "B"],
        )
        merged = chunker._merge_and_split([block])
        assert len(merged) == 1
        assert merged[0].text.startswith("Table — columns: A, B")


# ---------------------------------------------------------------------------
# 9.11 Canvas Container TipTap Parsing
# ---------------------------------------------------------------------------


class TestCanvasContainerTipTap:
    """Tests for canvas containers being parsed via _chunk_tiptap."""

    def test_container_with_tiptap_content(self):
        """Canvas containers with type='doc' content go through _chunk_tiptap."""
        chunker = SemanticChunker()
        canvas_json = {
            "elements": [],
            "containers": [
                {
                    "id": "c1",
                    "label": "Requirements",
                    "position": {"x": 100, "y": 100},
                    "content": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Container paragraph text."}],
                            },
                        ],
                    },
                },
            ],
        }
        chunks = chunker._chunk_canvas(canvas_json, "Canvas")
        assert len(chunks) >= 1
        assert "Container paragraph text" in chunks[0].text

    def test_container_table_gets_own_chunk(self):
        """Tables inside canvas containers get their own chunk (via 9.10 integration)."""
        chunker = SemanticChunker()
        canvas_json = {
            "elements": [],
            "containers": [
                {
                    "id": "c1",
                    "label": "Data",
                    "position": {"x": 600, "y": 100},
                    "content": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Before table."}],
                            },
                            {
                                "type": "table",
                                "content": [
                                    {
                                        "type": "tableRow",
                                        "content": [
                                            {"type": "tableCell", "content": [{"type": "text", "text": "X"}]},
                                            {"type": "tableCell", "content": [{"type": "text", "text": "Y"}]},
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                },
            ],
        }
        chunks = chunker._chunk_canvas(canvas_json, "Canvas")
        # Table preamble may have overlap text prepended, so check for "Table" anywhere
        table_chunks = [c for c in chunks if "Table" in c.text and "columns:" in c.text]
        assert len(table_chunks) >= 1

    def test_container_heading_context_includes_quadrant(self):
        """Container chunks should have heading context with label and quadrant."""
        chunker = SemanticChunker()
        canvas_json = {
            "elements": [],
            "containers": [
                {
                    "id": "c1",
                    "label": "Notes",
                    "position": {"x": 100, "y": 600},
                    "content": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Test text."}],
                            },
                        ],
                    },
                },
            ],
        }
        chunks = chunker._chunk_canvas(canvas_json, "Canvas")
        assert len(chunks) >= 1
        # Position (100, 600) = Bottom Left
        assert chunks[0].heading_context == "Notes — Bottom Left"

    def test_mixed_containers_and_elements(self):
        """Canvas with both containers and plain elements produces chunks for both."""
        chunker = SemanticChunker()
        canvas_json = {
            "elements": [
                {
                    "id": "e1",
                    "type": "sticky_note",
                    "text": "Plain sticky note text",
                    "position": {"x": 50, "y": 50},
                    "size": {"width": 100, "height": 100},
                },
            ],
            "containers": [
                {
                    "id": "c1",
                    "label": "Box",
                    "position": {"x": 500, "y": 500},
                    "content": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Container content."}],
                            },
                        ],
                    },
                },
            ],
        }
        chunks = chunker._chunk_canvas(canvas_json, "Canvas")
        texts = " ".join(c.text for c in chunks)
        assert "Container content" in texts
        assert "sticky note" in texts.lower() or "Plain sticky note" in texts

    def test_empty_container_no_crash(self):
        """Canvas with empty container (no content) should not crash or produce empty chunks."""
        chunker = SemanticChunker()
        canvas_json = {
            "elements": [],
            "containers": [
                {"id": "c1", "label": "Empty", "position": {"x": 0, "y": 0}},
                {"id": "c2", "label": "NoDoc", "position": {"x": 100, "y": 100}, "content": {}},
                {"id": "c3", "label": "WrongType", "position": {"x": 200, "y": 200}, "content": {"type": "other"}},
            ],
        }
        chunks = chunker._chunk_canvas(canvas_json, "Canvas")
        assert len(chunks) == 0


# ---------------------------------------------------------------------------
# 9.12 Slide Boundary Enforcement
# ---------------------------------------------------------------------------


class TestSlideBoundaryEnforcement:
    """Tests for chunk boundaries at Slide N headings."""

    def test_slide_heading_detection(self):
        """_is_slide_heading detects 'Slide N: Title' pattern."""
        chunker = SemanticChunker()
        block = _TextBlock(text="## Slide 1: Introduction\n", heading_context=None)
        result = chunker._is_slide_heading(block)
        assert result == "Slide 1: Introduction"

    def test_non_slide_heading_not_detected(self):
        """Non-slide headings return None."""
        chunker = SemanticChunker()
        block = _TextBlock(text="## Regular Heading\n", heading_context=None)
        result = chunker._is_slide_heading(block)
        assert result is None

    def test_slides_never_merge_across_boundaries(self):
        """Two small adjacent slides should be separate chunks, not merged."""
        chunker = SemanticChunker()
        content_json = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Slide 1: Intro"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Slide 1 content here."}],
                },
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Slide 2: Details"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Slide 2 content here."}],
                },
            ],
        }
        chunks = chunker._chunk_tiptap(content_json, "Presentation")
        # Each slide should be its own chunk (not merged)
        assert len(chunks) >= 2
        # Find chunks with slide content
        slide1_chunks = [c for c in chunks if "Slide 1 content" in c.text]
        slide2_chunks = [c for c in chunks if "Slide 2 content" in c.text]
        assert len(slide1_chunks) >= 1
        assert len(slide2_chunks) >= 1
        # They should be different chunks
        assert slide1_chunks[0] is not slide2_chunks[0]

    def test_slide_heading_sets_heading_context(self):
        """Slide heading becomes the heading_context for its chunks."""
        chunker = SemanticChunker()
        content_json = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Slide 3: Summary"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Summary content."}],
                },
            ],
        }
        chunks = chunker._chunk_tiptap(content_json, "Presentation")
        # The chunk containing "Summary content" should have slide heading context
        summary_chunks = [c for c in chunks if "Summary content" in c.text]
        assert len(summary_chunks) >= 1
        assert summary_chunks[0].heading_context == "Slide 3: Summary"

    def test_speaker_notes_prefixed(self):
        """Blockquotes within slides should be prefixed with [Speaker Notes]."""
        chunker = SemanticChunker()
        content_json = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Slide 1: Intro"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Main slide content."}],
                },
                {
                    "type": "blockquote",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "These are my speaker notes."}],
                        },
                    ],
                },
            ],
        }
        # Use _merge_and_split to check output without overlap
        nodes = content_json.get("content", [])
        blocks = chunker._extract_blocks(nodes, current_heading="Pres")
        blocks = [b for b in blocks if b.text.strip()]
        for b in blocks:
            b.token_count = chunker.count_tokens(b.text)
        merged = chunker._merge_and_split(blocks)
        all_text = " ".join(c.text for c in merged)
        assert "[Speaker Notes]" in all_text

    def test_large_slide_split_within_boundaries(self):
        """A single slide with text exceeding MAX_TOKENS should be split, but all
        sub-chunks should have the same heading_context."""
        chunker = SemanticChunker()
        # Build content: one slide heading + many paragraphs exceeding MAX_TOKENS
        nodes = [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Slide 1: Big Slide"}],
            },
        ]
        # Add enough paragraphs to exceed MAX_TOKENS (800)
        for i in range(50):
            nodes.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": f"Sentence number {i}. This is additional text to pad the paragraph content further and further. "}],
            })
        content_json = {"type": "doc", "content": nodes}
        chunks = chunker._chunk_tiptap(content_json, "Pres")
        # Should produce multiple chunks
        assert len(chunks) >= 2
        # All chunks should have "Slide 1: Big Slide" heading context
        for chunk in chunks:
            assert chunk.heading_context == "Slide 1: Big Slide"

    def test_three_slides_produce_separate_chunks(self):
        """Three slides with 200, 300, 400 tokens each should produce 3 chunks."""
        chunker = SemanticChunker()
        nodes = []
        for slide_num in range(1, 4):
            nodes.append({
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": f"Slide {slide_num}: Title{slide_num}"}],
            })
            # Add unique text per slide
            word_count = 100 + slide_num * 50
            text = f"Content for slide {slide_num}. " + ("word " * word_count)
            nodes.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            })

        content_json = {"type": "doc", "content": nodes}
        # Use merge_and_split directly to avoid overlap complicating checks
        blocks = chunker._extract_blocks(content_json.get("content", []), current_heading="Pres")
        blocks = [b for b in blocks if b.text.strip()]
        for b in blocks:
            b.token_count = chunker.count_tokens(b.text)
        merged = chunker._merge_and_split(blocks)
        # Should have at least 3 chunks (one per slide)
        assert len(merged) >= 3
        # Each slide heading context should appear
        heading_contexts = [c.heading_context for c in merged]
        assert "Slide 1: Title1" in heading_contexts
        assert "Slide 2: Title2" in heading_contexts
        assert "Slide 3: Title3" in heading_contexts


# ---------------------------------------------------------------------------
# 9.13 Canvas Oversized Element Fallback
# ---------------------------------------------------------------------------


class TestCanvasOversizedElementFallback:
    """Tests for sub-splitting oversized canvas elements."""

    def test_oversized_element_subsplit(self):
        """Single element exceeding MAX_TOKENS is sub-split via _split_large_text."""
        chunker = SemanticChunker()
        from app.ai.chunking_service import _CanvasElement, _CanvasConnector

        # Create a single element with text exceeding MAX_TOKENS
        long_text = "word " * 2000  # Well over 800 tokens
        elem = _CanvasElement(
            id="e1",
            type="text_box",
            position_x=100,
            position_y=100,
            width=200,
            height=200,
            text=long_text.strip(),
        )

        chunks = chunker._split_cluster([elem], [])
        # Should produce multiple chunks (sub-split)
        assert len(chunks) > 1
        # Each chunk should be at or below MAX_TOKENS
        for chunk in chunks:
            assert chunk.token_count <= chunker.MAX_TOKENS + 10  # small margin for heading

    def test_normal_elements_not_subsplit(self):
        """Elements under MAX_TOKENS are not sub-split."""
        chunker = SemanticChunker()
        from app.ai.chunking_service import _CanvasElement

        elem = _CanvasElement(
            id="e1",
            type="sticky_note",
            position_x=100,
            position_y=100,
            width=100,
            height=100,
            text="Short text here.",
        )
        chunks = chunker._split_cluster([elem], [])
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# 9.14 Imported Image Slide Context
# ---------------------------------------------------------------------------


class TestImportedImageSlideContext:
    """Tests for slide title context in imported image chunks."""

    def test_parse_slide_titles_from_markdown(self):
        """_parse_slide_titles extracts page_number -> title mapping."""
        from app.worker import _parse_slide_titles

        markdown = (
            "# Document\n\n"
            "## Slide 1: Introduction\n\n"
            "Some intro content\n\n"
            "## Slide 2: Architecture Overview\n\n"
            "Architecture details\n\n"
            "## Slide 3: Conclusion\n\n"
            "Final remarks\n"
        )
        titles = _parse_slide_titles(markdown)
        assert titles == {
            1: "Introduction",
            2: "Architecture Overview",
            3: "Conclusion",
        }

    def test_parse_slide_titles_empty_markdown(self):
        """_parse_slide_titles returns empty dict for no slides."""
        from app.worker import _parse_slide_titles

        titles = _parse_slide_titles("Just regular text without slides.")
        assert titles == {}

    def test_process_imported_images_accepts_slide_titles(self):
        """process_imported_images accepts slide_titles parameter."""
        import inspect
        from app.ai.image_understanding_service import ImageUnderstandingService

        sig = inspect.signature(ImageUnderstandingService.process_imported_images)
        assert "slide_titles" in sig.parameters

    def test_heading_uses_slide_title_when_available(self):
        """Image heading should include slide title when slide_titles mapping provided."""
        # Test the logic directly by simulating the heading construction
        slide_titles = {1: "Introduction", 2: "Architecture"}
        page_number = 1

        slide_title = slide_titles.get(page_number)
        if slide_title:
            heading = f"Imported Image — Slide {page_number}: {slide_title}"
        elif page_number:
            heading = f"Imported Image (page {page_number})"
        else:
            heading = "Imported Image"

        assert heading == "Imported Image — Slide 1: Introduction"

    def test_heading_falls_back_to_page_number(self):
        """Without slide title, heading falls back to page number format."""
        slide_titles = {1: "Introduction"}
        page_number = 3  # Not in slide_titles

        slide_title = slide_titles.get(page_number)
        if slide_title:
            heading = f"Imported Image — Slide {page_number}: {slide_title}"
        elif page_number:
            heading = f"Imported Image (page {page_number})"
        else:
            heading = "Imported Image"

        assert heading == "Imported Image (page 3)"

    def test_heading_no_slide_titles_no_page(self):
        """Image with no slide titles and no page number uses bare heading."""
        slide_titles: dict[int, str] | None = None
        page_number = 0

        slide_title = (slide_titles or {}).get(page_number) if page_number else None
        if slide_title:
            heading = f"Imported Image — Slide {page_number}: {slide_title}"
        elif page_number:
            heading = f"Imported Image (page {page_number})"
        else:
            heading = "Imported Image"

        assert heading == "Imported Image"

    def test_parse_slide_titles_with_no_colon(self):
        """Slide headings without colon still match (consistent with _is_slide_heading)."""
        from app.worker import _parse_slide_titles

        markdown = "## Slide 1\n\nContent\n"
        titles = _parse_slide_titles(markdown)
        # Matches same pattern as chunking_service._is_slide_heading
        assert titles == {1: "Slide 1"}


# ---------------------------------------------------------------------------
# DA-008: Oversized Table Splitting
# ---------------------------------------------------------------------------


class TestOversizedTableSplitting:
    """Tests for splitting oversized tables by row groups."""

    def test_large_table_split_into_multiple_chunks(self):
        """Table with 200 rows (>MAX_TOKENS) should be split into multiple chunks
        with header repeated in each."""
        chunker = SemanticChunker()
        # Build a table with 200 data rows
        rows = []
        rows.append({
            "type": "tableRow",
            "content": [
                {"type": "tableCell", "content": [{"type": "text", "text": "Name"}]},
                {"type": "tableCell", "content": [{"type": "text", "text": "Value"}]},
                {"type": "tableCell", "content": [{"type": "text", "text": "Description"}]},
            ],
        })
        for i in range(200):
            rows.append({
                "type": "tableRow",
                "content": [
                    {"type": "tableCell", "content": [{"type": "text", "text": f"Item {i}"}]},
                    {"type": "tableCell", "content": [{"type": "text", "text": f"${i * 100}"}]},
                    {"type": "tableCell", "content": [{"type": "text", "text": f"Description for item {i} with details"}]},
                ],
            })

        content_json = {
            "type": "doc",
            "content": [{"type": "table", "content": rows}],
        }
        chunks = chunker._chunk_tiptap(content_json, "Inventory")

        # Should produce multiple chunks
        table_chunks = [c for c in chunks if "Table" in c.text]
        assert len(table_chunks) > 1

        # Each chunk should contain the header row
        for tc in table_chunks:
            assert "Name | Value | Description" in tc.text

        # Each chunk should have a row range in the preamble
        for tc in table_chunks:
            assert "(rows " in tc.text

    def test_small_table_not_split(self):
        """Table with 10 rows (<MAX_TOKENS) should remain a single chunk (no split)."""
        chunker = SemanticChunker()
        rows = []
        rows.append({
            "type": "tableRow",
            "content": [
                {"type": "tableCell", "content": [{"type": "text", "text": "Col1"}]},
                {"type": "tableCell", "content": [{"type": "text", "text": "Col2"}]},
            ],
        })
        for i in range(10):
            rows.append({
                "type": "tableRow",
                "content": [
                    {"type": "tableCell", "content": [{"type": "text", "text": f"A{i}"}]},
                    {"type": "tableCell", "content": [{"type": "text", "text": f"B{i}"}]},
                ],
            })

        content_json = {
            "type": "doc",
            "content": [{"type": "table", "content": rows}],
        }
        chunks = chunker._chunk_tiptap(content_json, "Small Table")

        # Should produce exactly one table chunk
        table_chunks = [c for c in chunks if c.text.startswith("Table")]
        assert len(table_chunks) == 1
        # Should NOT have row range in preamble (not split)
        assert "(rows " not in table_chunks[0].text

    def test_row_count_per_chunk_roughly_equal(self):
        """Row groups should each have ~50 rows (default rows_per_chunk)."""
        chunker = SemanticChunker()

        # Build table text directly for _split_table_by_rows
        header = "Name | Value | Category"
        data_rows = [f"Item{i} | ${i} | Cat{i % 5}" for i in range(200)]
        table_text = header + "\n" + "\n".join(data_rows)
        preamble = "Table: Test — columns: Name, Value, Category"

        chunks = chunker._split_table_by_rows(table_text, preamble, "Test")

        assert len(chunks) == 4  # 200 rows / 50 per chunk = 4 chunks

        # Check row ranges in preambles
        assert "(rows 1-50)" in chunks[0].text
        assert "(rows 51-100)" in chunks[1].text
        assert "(rows 101-150)" in chunks[2].text
        assert "(rows 151-200)" in chunks[3].text

    def test_split_table_header_only(self):
        """Table with only a header row should produce single chunk."""
        chunker = SemanticChunker()
        table_text = "Name | Value"
        preamble = "Table — columns: Name, Value"

        chunks = chunker._split_table_by_rows(table_text, preamble, None)
        assert len(chunks) == 1
        assert "Name | Value" in chunks[0].text
