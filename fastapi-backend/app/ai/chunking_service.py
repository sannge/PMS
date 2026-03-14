"""Semantic document chunking for vector embeddings.

Chunks document content into embedding-ready segments. Supports two document
types: regular TipTap documents (rich text) and CANVAS documents (freeform
spatial canvases with elements, connectors, and spatial clustering).

TipTap Strategy:
  - Walk TipTap JSON tree (reuses pattern from content_converter.py)
  - Split at heading boundaries (h1, h2, h3)
  - Target: 500-800 tokens per chunk
  - Overlap: ~100 tokens between adjacent chunks for context continuity
  - Each chunk keeps heading_context (ancestor headings) for retrieval quality
  - Handles: paragraphs, lists, code blocks, tables, blockquotes, drawio
  - Strips: image nodes (handled by image understanding in Phase 6)

Canvas Strategy:
  - Parse canvas JSON elements array
  - Extract text from each element (sticky notes, text boxes, etc.)
  - Build connectivity graph from connectors
  - Cluster connected/proximate elements using union-find
  - Each cluster becomes one chunk
  - heading_context = element type + position label
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

import tiktoken

# Module-level singleton encoder — tiktoken caches the encoding data
# internally, but reusing the same object avoids per-instance overhead.
_tiktoken_encoder = tiktoken.get_encoding("cl100k_base")


@dataclass
class ChunkResult:
    """A single chunk ready for embedding."""

    text: str
    heading_context: str | None
    token_count: int
    chunk_index: int


@dataclass
class _TextBlock:
    """Intermediate representation of a text segment with heading context."""

    text: str
    heading_context: str | None
    token_count: int = 0
    is_table: bool = False
    table_columns: list[str] | None = None


@dataclass
class _CanvasElement:
    """Parsed canvas element with text content."""

    id: str
    type: str
    position_x: float
    position_y: float
    width: float
    height: float
    text: str
    color: str | None = None


@dataclass
class _CanvasConnector:
    """Parsed connector between canvas elements."""

    id: str
    source_id: str
    target_id: str
    label: str


class SemanticChunker:
    """Chunks document content into embedding-ready segments.

    Args:
        target_tokens: Target chunk size in tokens (default 600).
        overlap_tokens: Token overlap between adjacent chunks (default 100).
    """

    # Token bounds for merge/split logic — read from config at class init
    from .config_service import get_agent_config as _get_cfg
    _chunker_cfg = _get_cfg()
    MIN_TOKENS = _chunker_cfg.get_int("embedding.min_chunk_tokens", 500)
    MAX_TOKENS = _chunker_cfg.get_int("embedding.max_chunk_tokens", 800)

    # Spatial proximity threshold for canvas clustering (pixels)
    CANVAS_PROXIMITY_THRESHOLD = _chunker_cfg.get_float(
        "embedding.canvas_proximity_threshold", 300.0
    )
    del _chunker_cfg, _get_cfg  # cleanup class namespace

    def __init__(self, target_tokens: int = 600, overlap_tokens: int = 100) -> None:
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self._encoder = _tiktoken_encoder

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken cl100k_base encoding."""
        if not text:
            return 0
        return len(self._encoder.encode(text))

    def chunk_document(
        self,
        content_json: dict[str, Any],
        title: str,
        document_type: str = "document",
    ) -> list[ChunkResult]:
        """Main entry point. Routes to appropriate chunking strategy.

        Args:
            content_json: TipTap JSON (document) or Canvas JSON (canvas).
            title: Document title for heading context.
            document_type: "document" for TipTap, "canvas" for spatial canvas.

        Returns:
            Ordered list of chunks with sequential chunk_index values.
        """
        if document_type == "canvas":
            return self._chunk_canvas(content_json, title)
        return self._chunk_tiptap(content_json, title)

    # ---- TipTap Chunking ----

    def _chunk_tiptap(
        self, content_json: dict[str, Any], title: str
    ) -> list[ChunkResult]:
        """TipTap document chunking pipeline.

        1. Parse TipTap JSON content tree
        2. Extract text blocks with heading context
        3. Merge small blocks, split large blocks
        4. Add overlap between adjacent chunks
        5. Assign sequential chunk_index
        """
        if not content_json:
            return []

        nodes = content_json.get("content", [])
        if not nodes:
            return []

        blocks = self._extract_blocks(nodes, current_heading=title)
        if not blocks:
            return []

        # Filter out blocks with no meaningful text
        blocks = [b for b in blocks if b.text.strip()]
        if not blocks:
            return []

        # Count tokens for each block
        for block in blocks:
            block.token_count = self.count_tokens(block.text)

        merged = self._merge_and_split(blocks)
        if not merged:
            return []

        with_overlap = self._add_overlap(merged)

        # Assign sequential chunk_index
        for i, chunk in enumerate(with_overlap):
            chunk.chunk_index = i

        return with_overlap

    def _extract_blocks(
        self,
        nodes: list[dict[str, Any]],
        current_heading: str | None = None,
    ) -> list[_TextBlock]:
        """Walk TipTap nodes recursively, extract text blocks with heading hierarchy."""
        blocks: list[_TextBlock] = []

        for node in nodes:
            node_type = node.get("type", "")

            if node_type == "heading":
                level = node.get("attrs", {}).get("level", 1)
                heading_text = self._inline_text(node.get("content", []))
                if heading_text.strip():
                    current_heading = heading_text.strip()
                    # Start a new block at heading boundary
                    blocks.append(_TextBlock(
                        text=f"{'#' * level} {heading_text}\n",
                        heading_context=current_heading,
                    ))

            elif node_type == "paragraph":
                text = self._inline_text(node.get("content", []))
                if text.strip():
                    blocks.append(_TextBlock(
                        text=text + "\n",
                        heading_context=current_heading,
                    ))

            elif node_type in ("bulletList", "orderedList", "taskList"):
                text = self._extract_list_text(node)
                if text.strip():
                    blocks.append(_TextBlock(
                        text=text,
                        heading_context=current_heading,
                    ))

            elif node_type == "codeBlock":
                code = self._extract_text_recursive(node.get("content", []))
                lang = node.get("attrs", {}).get("language", "") or ""
                text = f"```{lang}\n{code}\n```\n"
                if code.strip():
                    blocks.append(_TextBlock(
                        text=text,
                        heading_context=current_heading,
                    ))

            elif node_type == "blockquote":
                inner_blocks = self._extract_blocks(
                    node.get("content", []),
                    current_heading=current_heading,
                )
                for b in inner_blocks:
                    b.text = "> " + b.text.replace("\n", "\n> ").removesuffix("> ") + "\n"
                blocks.extend(inner_blocks)

            elif node_type == "table":
                text, header_cells = self._extract_table_text_with_headers(node)
                if text.strip():
                    blocks.append(_TextBlock(
                        text=text,
                        heading_context=current_heading,
                        is_table=True,
                        table_columns=header_cells,
                    ))

            elif node_type == "horizontalRule":
                continue  # Skip presentation-only elements

            elif node_type == "image":
                continue  # Skip images (handled by image understanding)

            elif node_type == "drawio":
                text = self._extract_drawio_text(node)
                if text.strip():
                    blocks.append(_TextBlock(
                        text=text,
                        heading_context=current_heading,
                    ))

            else:
                # Unknown node type -- recurse into children (graceful degradation)
                if "content" in node:
                    child_blocks = self._extract_blocks(
                        node["content"],
                        current_heading=current_heading,
                    )
                    blocks.extend(child_blocks)

        return blocks

    def _inline_text(self, nodes: list[dict[str, Any]]) -> str:
        """Extract inline text from text/hardBreak nodes."""
        parts: list[str] = []
        for node in nodes:
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            elif node.get("type") == "hardBreak":
                parts.append("\n")
        return "".join(parts)

    def _extract_text_recursive(self, nodes: list[dict[str, Any]]) -> str:
        """Recursively extract all text from nodes."""
        parts: list[str] = []
        for node in nodes:
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            elif node.get("type") == "hardBreak":
                parts.append("\n")
            elif node.get("type") == "image":
                continue  # Skip images
            elif "content" in node:
                parts.append(self._extract_text_recursive(node["content"]))
                if node.get("type") in (
                    "paragraph", "heading", "listItem", "taskItem",
                    "codeBlock", "blockquote",
                ):
                    parts.append("\n")
        return "".join(parts)

    def _extract_list_text(self, node: dict[str, Any]) -> str:
        """Extract text from list nodes (bullet, ordered, task)."""
        items = node.get("content", [])
        parts: list[str] = []
        for i, item in enumerate(items):
            prefix = "- "
            if node.get("type") == "orderedList":
                prefix = f"{i + 1}. "
            elif node.get("type") == "taskList":
                checked = item.get("attrs", {}).get("checked", False)
                prefix = "[x] " if checked else "[ ] "

            text = self._extract_text_recursive(item.get("content", []))
            parts.append(prefix + text.strip() + "\n")
        return "".join(parts)

    def _extract_table_text(self, node: dict[str, Any]) -> str:
        """Extract text from table nodes."""
        text, _ = self._extract_table_text_with_headers(node)
        return text

    def _extract_table_text_with_headers(
        self, node: dict[str, Any]
    ) -> tuple[str, list[str]]:
        """Extract text from table nodes and return header row cells separately.

        Returns:
            Tuple of (full_table_text, header_cell_texts).
            header_cell_texts is the list of cell texts from the first row.
        """
        rows = node.get("content", [])
        parts: list[str] = []
        header_cells: list[str] = []
        for row_idx, row in enumerate(rows):
            cells = row.get("content", [])
            cell_texts: list[str] = []
            for cell in cells:
                text = self._extract_text_recursive(cell.get("content", []))
                cell_texts.append(text.strip())
            if row_idx == 0:
                header_cells = cell_texts
            parts.append(" | ".join(cell_texts) + "\n")
        return "".join(parts), header_cells

    def _extract_drawio_text(self, node: dict[str, Any]) -> str:
        """Extract structured graph information from draw.io diagram nodes.

        Parses the full draw.io XML graph structure (vertices, edges, and
        containment hierarchy) to produce a rich textual representation.
        Falls back to plain label extraction if no edges or containment are found.
        """
        import defusedxml.ElementTree as ET

        attrs = node.get("attrs", {})
        xml_data = attrs.get("data")
        if not xml_data:
            return ""

        try:
            root = ET.fromstring(xml_data)
        except (ET.ParseError, Exception):
            # Catches both malformed XML (ParseError) and defusedxml security
            # rejections (DTDForbidden, EntitiesForbidden, ExternalReferenceForbidden)
            return ""

        def clean_html(text: str) -> str:
            """Strip HTML tags and normalize whitespace."""
            cleaned = re.sub(r"<[^>]+>", " ", text).strip()
            return re.sub(r"\s+", " ", cleaned)

        # Pass 1 -- Vertices: collect mxCell[vertex="1"]
        vertices: dict[str, dict[str, str]] = {}
        for cell in root.iter("mxCell"):
            if cell.get("vertex") == "1":
                cell_id = cell.get("id", "")
                value = cell.get("value", "")
                label = clean_html(value) if value else ""
                parent_id = cell.get("parent", "")
                if cell_id:
                    vertices[cell_id] = {"label": label, "parent": parent_id}

        # Pass 2 -- Edges: collect mxCell[edge="1"]
        edges: list[tuple[str, str, str]] = []
        for cell in root.iter("mxCell"):
            if cell.get("edge") == "1":
                source = cell.get("source", "")
                target = cell.get("target", "")
                if source and target and source in vertices and target in vertices:
                    value = cell.get("value", "")
                    edge_label = clean_html(value) if value else ""
                    edges.append((source, target, edge_label))

        # Pass 3 -- Containment: build parent->children map
        # Only include parents that are actual vertices (not root "0" or layer "1")
        children_map: dict[str, list[str]] = {}
        for cell_id, info in vertices.items():
            parent_id = info["parent"]
            if parent_id and parent_id in vertices:
                children_map.setdefault(parent_id, []).append(cell_id)

        # If no structured graph data found, fall back to simple label list
        if not edges and not children_map:
            labels = [info["label"] for info in vertices.values() if info["label"]]
            if labels:
                return "[Diagram] " + " ".join(labels) + "\n"
            # Final fallback: extract value from any mxCell (handles XML without
            # vertex/edge attributes, e.g. simplified draw.io exports)
            all_labels: list[str] = []
            for cell in root.iter("mxCell"):
                value = cell.get("value", "")
                if value:
                    clean = clean_html(value)
                    if clean:
                        all_labels.append(clean)
            return "[Diagram] " + " ".join(all_labels) + "\n" if all_labels else ""

        # Build structured output
        parts: list[str] = ["[Diagram]"]

        # Components line: all vertices with labels
        labeled = [info["label"] for info in vertices.values() if info["label"]]
        if labeled:
            parts.append("Components: " + ", ".join(labeled))

        # Relationships section
        if edges:
            parts.append("Relationships:")
            for source_id, target_id, edge_label in edges:
                src_label = vertices[source_id]["label"] or source_id
                tgt_label = vertices[target_id]["label"] or target_id
                if edge_label:
                    parts.append(f"- {src_label} -> {edge_label} -> {tgt_label}")
                else:
                    parts.append(f"- {src_label} -> {tgt_label}")

        # Structure section (containment)
        if children_map:
            parts.append("Structure:")
            for parent_id, child_ids in children_map.items():
                parent_label = vertices[parent_id]["label"] or parent_id
                child_labels = [
                    vertices[cid]["label"] or cid for cid in child_ids
                ]
                parts.append(f"- {parent_label} contains: {', '.join(child_labels)}")

        return "\n".join(parts) + "\n"

    @staticmethod
    def _is_slide_heading(block: _TextBlock) -> str | None:
        """Check if a block is a slide heading from Docling import.

        Returns the slide heading text (e.g. "Slide 1: Introduction") if
        the block text matches the ``## Slide N`` pattern, else None.
        """
        text = block.text.strip()
        m = re.match(r'^#{1,3}\s+(Slide\s+\d+.*)', text)
        if m:
            return m.group(1).strip()
        return None

    def _merge_and_split(
        self, blocks: list[_TextBlock], rows_per_chunk: int = 50
    ) -> list[ChunkResult]:
        """Merge small blocks under same heading; split blocks exceeding MAX_TOKENS.

        Special handling:
        - Table blocks (is_table=True): flush buffer, emit table as its own
          chunk with a preamble, bypass MAX_TOKENS.
        - Slide headings ("Slide N: ..."): flush buffer, enforce chunk boundary
          at slide breaks. Never merge content across slide boundaries.

        Args:
            blocks: List of _TextBlock to merge/split.
            rows_per_chunk: Target rows per table chunk (MED-2).
        """
        chunks: list[ChunkResult] = []
        current_text = ""
        current_heading: str | None = blocks[0].heading_context if blocks else None
        current_tokens = 0

        for block in blocks:
            # --- Table blocks: flush buffer, emit as own chunk, bypass MAX_TOKENS ---
            if block.is_table:
                # Flush accumulated text buffer
                if current_text.strip():
                    chunks.append(ChunkResult(
                        text=current_text.strip(),
                        heading_context=current_heading,
                        token_count=current_tokens,
                        chunk_index=0,
                    ))
                    current_text = ""
                    current_tokens = 0

                # Build preamble: "Table: {heading} — columns: col1, col2, ..."
                preamble_parts: list[str] = []
                preamble_parts.append("Table")
                if block.heading_context:
                    preamble_parts.append(f": {block.heading_context}")
                if block.table_columns:
                    cols = ", ".join(c for c in block.table_columns if c)
                    if cols:
                        preamble_parts.append(f" — columns: {cols}")
                preamble = "".join(preamble_parts)

                table_text = f"{preamble}\n{block.text.strip()}"
                table_tokens = self.count_tokens(table_text)

                if table_tokens > self.MAX_TOKENS:
                    # Split oversized table by row groups (MED-2: thread rows_per_chunk)
                    table_chunks = self._split_table_by_rows(
                        block.text.strip(), preamble, block.heading_context,
                        rows_per_chunk=rows_per_chunk,
                    )
                    chunks.extend(table_chunks)
                else:
                    chunks.append(ChunkResult(
                        text=table_text,
                        heading_context=block.heading_context,
                        token_count=table_tokens,
                        chunk_index=0,
                    ))
                current_heading = block.heading_context
                continue

            # --- Slide headings: enforce chunk boundary at slide breaks ---
            slide_title = self._is_slide_heading(block)
            if slide_title is not None:
                # Flush accumulated text buffer
                if current_text.strip():
                    chunks.append(ChunkResult(
                        text=current_text.strip(),
                        heading_context=current_heading,
                        token_count=current_tokens,
                        chunk_index=0,
                    ))
                    current_text = ""
                    current_tokens = 0
                # Use slide title as heading context for this and subsequent blocks
                current_heading = slide_title
                current_text = block.text
                current_tokens = block.token_count
                continue

            # --- 9.12: Speaker notes — blockquotes within slides ---
            if (
                current_heading
                and re.match(r"^Slide\s+\d+", current_heading)
                and block.text.lstrip().startswith(">")
            ):
                # Strip blockquote markers and prefix with [Speaker Notes]
                lines = block.text.split("\n")
                cleaned = []
                for line in lines:
                    cleaned.append(re.sub(r"^>\s?", "", line))
                speaker_text = "[Speaker Notes] " + "\n".join(cleaned).strip() + "\n"
                block = _TextBlock(
                    text=speaker_text,
                    heading_context=block.heading_context,
                    token_count=self.count_tokens(speaker_text),
                )

            # If heading changed and we have accumulated text, flush —
            # BUT if the buffer is tiny (e.g. just a heading line like
            # "# Introduction\n" with no body text), carry it forward
            # into the next chunk instead of emitting a near-empty chunk.
            if block.heading_context != current_heading and current_text.strip():
                if current_tokens > 50:
                    chunks.append(ChunkResult(
                        text=current_text.strip(),
                        heading_context=current_heading,
                        token_count=current_tokens,
                        chunk_index=0,
                    ))
                    current_text = ""
                    current_tokens = 0
                current_heading = block.heading_context

            # If adding this block would exceed MAX, flush first —
            # BUT if the buffer is tiny (≤50 tokens, e.g. just a title or
            # heading line), keep it so it merges with the next content
            # instead of being emitted as a near-empty chunk.
            if current_tokens + block.token_count > self.MAX_TOKENS and current_text.strip():
                if current_tokens > 50:
                    chunks.append(ChunkResult(
                        text=current_text.strip(),
                        heading_context=current_heading,
                        token_count=current_tokens,
                        chunk_index=0,
                    ))
                    current_text = ""
                    current_tokens = 0

            # If single block exceeds MAX, split at sentence boundaries
            if block.token_count > self.MAX_TOKENS:
                if current_text.strip():
                    if current_tokens > 50:
                        # Buffer is large enough — emit as its own chunk
                        chunks.append(ChunkResult(
                            text=current_text.strip(),
                            heading_context=current_heading,
                            token_count=current_tokens,
                            chunk_index=0,
                        ))
                        text_to_split = block.text
                    else:
                        # Buffer is tiny (e.g. just a title) — prepend it
                        # to the block text so it stays with the content
                        text_to_split = current_text + block.text
                else:
                    text_to_split = block.text
                current_text = ""
                current_tokens = 0

                split_chunks = self._split_large_text(
                    text_to_split, block.heading_context
                )
                chunks.extend(split_chunks)
                current_heading = block.heading_context
            else:
                current_text += block.text
                current_tokens += block.token_count
                current_heading = block.heading_context

        # Flush remaining
        if current_text.strip():
            chunks.append(ChunkResult(
                text=current_text.strip(),
                heading_context=current_heading,
                token_count=current_tokens,
                chunk_index=0,
            ))

        return chunks

    def _split_table_by_rows(
        self,
        table_text: str,
        preamble: str,
        heading_context: str | None,
        rows_per_chunk: int = 50,
    ) -> list[ChunkResult]:
        """Split an oversized table into chunks of row groups.

        Parses the table text into header + data rows, then groups data rows
        into chunks of ``rows_per_chunk``, repeating the header at the top of
        each chunk with a preamble indicating the row range.

        Args:
            table_text: Raw table text (pipe-delimited rows separated by newlines).
            preamble: Base preamble (e.g. "Table: Heading — columns: A, B").
            heading_context: Heading context for each chunk.
            rows_per_chunk: Target number of data rows per chunk (default 50).

        Returns:
            List of ChunkResult, one per row group.
        """
        lines = [ln for ln in table_text.split("\n") if ln.strip()]
        if not lines:
            return []

        # First line with "|" is the header row
        header_line = lines[0]
        data_lines = lines[1:]

        if not data_lines:
            # Table with only a header — emit as single chunk
            full_text = f"{preamble}\n{header_line}"
            return [ChunkResult(
                text=full_text,
                heading_context=heading_context,
                token_count=self.count_tokens(full_text),
                chunk_index=0,
            )]

        chunks: list[ChunkResult] = []
        total_rows = len(data_lines)

        for start in range(0, total_rows, rows_per_chunk):
            end = min(start + rows_per_chunk, total_rows)
            group = data_lines[start:end]

            chunk_preamble = f"{preamble} (rows {start + 1}-{end})"
            chunk_text = f"{chunk_preamble}\n{header_line}\n" + "\n".join(group)
            chunks.append(ChunkResult(
                text=chunk_text,
                heading_context=heading_context,
                token_count=self.count_tokens(chunk_text),
                chunk_index=0,
            ))

        logger.info(
            "Oversized table split: %d rows -> %d chunks of ~%d rows (heading: %s)",
            total_rows,
            len(chunks),
            rows_per_chunk,
            heading_context,
        )

        return chunks

    def _split_large_text(
        self, text: str, heading_context: str | None
    ) -> list[ChunkResult]:
        """Split text exceeding MAX_TOKENS at sentence boundaries.

        If a single sentence exceeds MAX_TOKENS (e.g., a long code block
        with no newlines, a giant URL, or CJK text without periods), it is
        hard-split at token boundaries as a fallback.
        """
        sentences = self._split_into_sentences(text)
        chunks: list[ChunkResult] = []
        current_text = ""
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = self.count_tokens(sentence)

            # Fallback: hard-split sentences that exceed MAX_TOKENS
            if sentence_tokens > self.MAX_TOKENS:
                # Flush any accumulated text first
                if current_text.strip():
                    chunks.append(ChunkResult(
                        text=current_text.strip(),
                        heading_context=heading_context,
                        token_count=current_tokens,
                        chunk_index=0,
                    ))
                    current_text = ""
                    current_tokens = 0

                # Hard-split at token boundaries
                tokens = self._encoder.encode(sentence)
                for start in range(0, len(tokens), self.MAX_TOKENS):
                    sub_tokens = tokens[start:start + self.MAX_TOKENS]
                    sub_text = self._encoder.decode(sub_tokens)
                    if sub_text.strip():
                        chunks.append(ChunkResult(
                            text=sub_text.strip(),
                            heading_context=heading_context,
                            token_count=len(sub_tokens),
                            chunk_index=0,
                        ))
                continue

            if current_tokens + sentence_tokens > self.MAX_TOKENS and current_text.strip():
                chunks.append(ChunkResult(
                    text=current_text.strip(),
                    heading_context=heading_context,
                    token_count=current_tokens,
                    chunk_index=0,
                ))
                current_text = ""
                current_tokens = 0

            current_text += sentence
            current_tokens += sentence_tokens

        if current_text.strip():
            chunks.append(ChunkResult(
                text=current_text.strip(),
                heading_context=heading_context,
                token_count=current_tokens,
                chunk_index=0,
            ))

        return chunks

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences at period/newline boundaries."""
        # Split at sentence-ending punctuation followed by space, or at newlines
        parts = re.split(r'(?<=[.!?])\s+|\n+', text)
        # Re-add spacing
        result: list[str] = []
        for part in parts:
            if part.strip():
                result.append(part.strip() + " ")
        return result

    def _add_overlap(self, chunks: list[ChunkResult]) -> list[ChunkResult]:
        """Add overlap tokens from end of chunk N to start of chunk N+1."""
        if len(chunks) <= 1:
            return chunks

        result: list[ChunkResult] = [chunks[0]]

        for i in range(1, len(chunks)):
            prev_text = chunks[i - 1].text
            # Get last ~overlap_tokens worth of text from previous chunk
            prev_tokens = self._encoder.encode(prev_text)
            if len(prev_tokens) > self.overlap_tokens:
                overlap_tokens = prev_tokens[-self.overlap_tokens:]
                overlap_text = self._encoder.decode(overlap_tokens)
            else:
                overlap_text = prev_text

            # Prepend overlap to current chunk
            new_text = overlap_text.strip() + " " + chunks[i].text
            new_token_count = self.count_tokens(new_text)

            result.append(ChunkResult(
                text=new_text,
                heading_context=chunks[i].heading_context,
                token_count=new_token_count,
                chunk_index=0,
            ))

        return result

    # ---- Markdown Chunking (for file extraction output) ----

    def chunk_markdown(
        self,
        markdown: str,
        title: str,
        rows_per_chunk: int = 50,
    ) -> list[ChunkResult]:
        """Chunk raw Markdown text into embedding-ready segments.

        Designed for file extraction output (spreadsheets, Visio, PDF/DOCX).
        Splits at heading boundaries, detects pipe tables and splits them
        via _split_table_by_rows, merges small sections, splits large ones.

        Args:
            markdown: Raw Markdown text from extraction.
            title: File title for heading context.
            rows_per_chunk: Dynamic rows_per_chunk for table splitting.

        Returns:
            Ordered list of ChunkResult with sequential chunk_index.
        """
        if not markdown or not markdown.strip():
            return []

        blocks = self._extract_markdown_blocks(markdown, title)
        if not blocks:
            return []

        # Count tokens
        for block in blocks:
            block.token_count = self.count_tokens(block.text)

        # MED-2: Thread rows_per_chunk to _merge_and_split -> _split_table_by_rows
        merged = self._merge_and_split(blocks, rows_per_chunk=rows_per_chunk)
        if not merged:
            return []

        with_overlap = self._add_overlap(merged)

        for i, chunk in enumerate(with_overlap):
            chunk.chunk_index = i

        return with_overlap

    def _extract_markdown_blocks(
        self,
        markdown: str,
        title: str,
    ) -> list[_TextBlock]:
        """Parse raw Markdown into TextBlocks split at heading boundaries.

        Detects pipe tables and marks them with is_table=True so that
        _merge_and_split can use table-specific splitting logic.
        """
        lines = markdown.split("\n")
        blocks: list[_TextBlock] = []
        current_heading = title
        buffer_lines: list[str] = []
        in_table = False
        table_lines: list[str] = []
        table_headers: list[str] = []

        def flush_buffer() -> None:
            nonlocal buffer_lines
            text = "\n".join(buffer_lines).strip()
            if text:
                blocks.append(_TextBlock(
                    text=text + "\n",
                    heading_context=current_heading,
                ))
            buffer_lines = []

        def flush_table() -> None:
            nonlocal table_lines, table_headers, in_table
            text = "\n".join(table_lines).strip()
            if text:
                blocks.append(_TextBlock(
                    text=text + "\n",
                    heading_context=current_heading,
                    is_table=True,
                    table_columns=table_headers if table_headers else None,
                ))
            table_lines = []
            table_headers = []
            in_table = False

        for line in lines:
            stripped = line.strip()

            # Detect heading
            if re.match(r'^#{1,6}\s+', stripped):
                # Flush any accumulated content
                if in_table:
                    flush_table()
                flush_buffer()
                # Extract heading text
                heading_match = re.match(r'^#{1,6}\s+(.*)', stripped)
                if heading_match:
                    current_heading = heading_match.group(1).strip()
                buffer_lines.append(line)
                continue

            # Detect pipe table rows
            is_pipe_row = stripped.startswith("|") and stripped.endswith("|")
            is_separator = bool(re.match(r'^\|[\s\-:|]+\|$', stripped))

            if is_pipe_row:
                if not in_table:
                    # Entering a table: flush text buffer
                    flush_buffer()
                    in_table = True
                    # First pipe row is the header
                    header_text = stripped.strip("|")
                    table_headers = [h.strip() for h in header_text.split("|")]
                if not is_separator:
                    table_lines.append(line)
                continue

            # If we were in a table and hit a non-table line, flush table
            if in_table:
                flush_table()

            buffer_lines.append(line)

        # Flush remaining
        if in_table:
            flush_table()
        flush_buffer()

        return blocks

    # ---- Canvas Chunking ----

    def _chunk_canvas(
        self, content_json: dict[str, Any], title: str
    ) -> list[ChunkResult]:
        """Canvas document chunking pipeline.

        1. Detect containers with TipTap content — route through _chunk_tiptap
        2. Extract text-bearing elements (non-container)
        3. Build connectivity graph from connectors
        4. Cluster connected/proximate elements
        5. Generate chunk text per cluster
        6. Split oversized clusters
        7. Assign chunk_index
        """
        if not content_json:
            return []

        chunks: list[ChunkResult] = []

        # --- Phase 1: Process containers with TipTap content ---
        containers = content_json.get("containers", [])
        container_ids: set[str] = set()
        for container in containers:
            if not isinstance(container, dict):
                continue
            container_id = container.get("id", "")
            if container_id:
                container_ids.add(container_id)
            content = container.get("content")
            if isinstance(content, dict) and content.get("type") == "doc":
                # Build heading context from container label and position
                label = container.get("label", "") or "Container"
                position = container.get("position", {})
                px = float(position.get("x", 0))
                py = float(position.get("y", 0))
                if px < 500 and py < 500:
                    quadrant = "Top Left"
                elif px >= 500 and py < 500:
                    quadrant = "Top Right"
                elif px < 500 and py >= 500:
                    quadrant = "Bottom Left"
                else:
                    quadrant = "Bottom Right"
                container_heading = f"{label} — {quadrant}"
                # Run full TipTap chunking on container content
                container_chunks = self._chunk_tiptap(content, container_heading)
                chunks.extend(container_chunks)

        # --- Phase 2: Process non-container elements ---
        elements, connectors = self._extract_canvas_elements(content_json)
        if not elements:
            # Still have container chunks — assign indexes and return
            for i, chunk in enumerate(chunks):
                chunk.chunk_index = i
            return chunks

        clusters = self._cluster_canvas_elements(elements, connectors)

        for cluster in clusters:
            chunk_text = self._build_cluster_text(cluster, connectors)
            if not chunk_text.strip():
                continue

            token_count = self.count_tokens(chunk_text)

            if token_count > self.MAX_TOKENS:
                # Split oversized cluster at element boundaries
                split_chunks = self._split_cluster(cluster, connectors)
                chunks.extend(split_chunks)
            else:
                # Determine heading context from primary element
                primary = cluster[0]
                heading = self._canvas_heading_context(primary)
                chunks.append(ChunkResult(
                    text=chunk_text.strip(),
                    heading_context=heading,
                    token_count=token_count,
                    chunk_index=0,
                ))

        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i

        return chunks

    def _extract_canvas_elements(
        self, canvas_json: dict[str, Any]
    ) -> tuple[list[_CanvasElement], list[_CanvasConnector]]:
        """Extract text-bearing elements and connectors from canvas JSON."""
        raw_elements = canvas_json.get("elements", [])
        elements: list[_CanvasElement] = []
        connectors: list[_CanvasConnector] = []

        for elem in raw_elements:
            if not isinstance(elem, dict):
                continue

            elem_type = elem.get("type", "")
            elem_id = elem.get("id", "")

            if elem_type == "connector":
                connectors.append(_CanvasConnector(
                    id=elem_id,
                    source_id=elem.get("source", ""),
                    target_id=elem.get("target", ""),
                    label=elem.get("label", "") or "",
                ))
                continue

            # Skip elements with no text content
            text = elem.get("text", "")
            if not text or not text.strip():
                continue

            position = elem.get("position", {})
            size = elem.get("size", {})
            elements.append(_CanvasElement(
                id=elem_id,
                type=elem_type,
                position_x=float(position.get("x", 0)),
                position_y=float(position.get("y", 0)),
                width=float(size.get("width", 0)),
                height=float(size.get("height", 0)),
                text=text.strip(),
                color=elem.get("color"),
            ))

        return elements, connectors

    def _cluster_canvas_elements(
        self,
        elements: list[_CanvasElement],
        connectors: list[_CanvasConnector],
    ) -> list[list[_CanvasElement]]:
        """Group elements by connectivity (connectors) and spatial proximity.

        Uses union-find (disjoint set) algorithm.
        """
        if not elements:
            return []

        # Cap: skip O(n^2) clustering for very large canvases
        from .config_service import get_agent_config
        _MAX_CLUSTER_ELEMENTS = get_agent_config().get_int("embedding.max_cluster_elements", 500)
        if len(elements) > _MAX_CLUSTER_ELEMENTS:
            logger.info(
                "Canvas has %d elements (> %d), skipping spatial clustering",
                len(elements),
                _MAX_CLUSTER_ELEMENTS,
            )
            return [elements]

        # Build element index
        elem_map: dict[str, int] = {}
        for i, elem in enumerate(elements):
            elem_map[elem.id] = i

        # Union-Find
        parent: list[int] = list(range(len(elements)))
        rank: list[int] = [0] * len(elements)

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # path compression
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if rank[ra] < rank[rb]:
                ra, rb = rb, ra
            parent[rb] = ra
            if rank[ra] == rank[rb]:
                rank[ra] += 1

        # Union by explicit connectors
        for conn in connectors:
            if conn.source_id in elem_map and conn.target_id in elem_map:
                union(elem_map[conn.source_id], elem_map[conn.target_id])

        # Union by spatial proximity
        for i in range(len(elements)):
            for j in range(i + 1, len(elements)):
                dist = self._element_distance(elements[i], elements[j])
                if dist < self.CANVAS_PROXIMITY_THRESHOLD:
                    union(i, j)

        # Group by root
        groups: dict[int, list[_CanvasElement]] = {}
        for i, elem in enumerate(elements):
            root = find(i)
            groups.setdefault(root, []).append(elem)

        return list(groups.values())

    def _element_distance(self, a: _CanvasElement, b: _CanvasElement) -> float:
        """Euclidean distance between center points of two elements."""
        ax = a.position_x + a.width / 2
        ay = a.position_y + a.height / 2
        bx = b.position_x + b.width / 2
        by = b.position_y + b.height / 2
        return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)

    def _build_cluster_text(
        self,
        cluster: list[_CanvasElement],
        connectors: list[_CanvasConnector],
    ) -> str:
        """Generate chunk text for a cluster of canvas elements."""
        elem_map = {elem.id: elem for elem in cluster}
        cluster_ids = set(elem_map.keys())
        parts: list[str] = []

        # Add element text
        for elem in cluster:
            label = elem.type.replace("_", " ").title()
            parts.append(f"[{label}] {elem.text}")

        # Add connector relationships within the cluster
        for conn in connectors:
            if conn.source_id in cluster_ids and conn.target_id in cluster_ids:
                src = elem_map.get(conn.source_id)
                tgt = elem_map.get(conn.target_id)
                if src and tgt:
                    src_label = src.type.replace("_", " ").title()
                    tgt_label = tgt.type.replace("_", " ").title()
                    connector_label = conn.label or "connected to"
                    parts.append(
                        f"[{src_label}] {src.text} -> [{connector_label}] -> "
                        f"[{tgt_label}] {tgt.text}"
                    )

        return "\n".join(parts)

    def _canvas_heading_context(self, elem: _CanvasElement) -> str:
        """Generate heading context from element type and position."""
        label = elem.type.replace("_", " ").title()

        # Determine quadrant
        if elem.position_x < 500 and elem.position_y < 500:
            position = "Top Left"
        elif elem.position_x >= 500 and elem.position_y < 500:
            position = "Top Right"
        elif elem.position_x < 500 and elem.position_y >= 500:
            position = "Bottom Left"
        else:
            position = "Bottom Right"

        return f"{label} - {position}"

    def _split_cluster(
        self,
        cluster: list[_CanvasElement],
        connectors: list[_CanvasConnector],
    ) -> list[ChunkResult]:
        """Split an oversized cluster at element boundaries.

        If a single element exceeds MAX_TOKENS, fall back to
        _split_large_text for that element's text.
        """
        chunks: list[ChunkResult] = []
        current_elements: list[_CanvasElement] = []
        current_tokens = 0

        for elem in cluster:
            elem_text = f"[{elem.type.replace('_', ' ').title()}] {elem.text}"
            elem_tokens = self.count_tokens(elem_text)

            # Single element exceeds MAX_TOKENS — sub-split via _split_large_text
            if elem_tokens > self.MAX_TOKENS:
                # Flush accumulated elements first
                if current_elements:
                    text = self._build_cluster_text(current_elements, connectors)
                    heading = self._canvas_heading_context(current_elements[0])
                    chunks.append(ChunkResult(
                        text=text.strip(),
                        heading_context=heading,
                        token_count=self.count_tokens(text),
                        chunk_index=0,
                    ))
                    current_elements = []
                    current_tokens = 0

                heading = self._canvas_heading_context(elem)
                sub_chunks = self._split_large_text(elem_text, heading)
                logger.info(
                    "Oversized canvas element sub-split: type=%s, "
                    "tokens=%d, sub_chunks=%d",
                    elem.type,
                    elem_tokens,
                    len(sub_chunks),
                )
                chunks.extend(sub_chunks)
                continue

            if current_tokens + elem_tokens > self.MAX_TOKENS and current_elements:
                text = self._build_cluster_text(current_elements, connectors)
                heading = self._canvas_heading_context(current_elements[0])
                chunks.append(ChunkResult(
                    text=text.strip(),
                    heading_context=heading,
                    token_count=self.count_tokens(text),
                    chunk_index=0,
                ))
                current_elements = []
                current_tokens = 0

            current_elements.append(elem)
            current_tokens += elem_tokens

        if current_elements:
            text = self._build_cluster_text(current_elements, connectors)
            heading = self._canvas_heading_context(current_elements[0])
            chunks.append(ChunkResult(
                text=text.strip(),
                heading_context=heading,
                token_count=self.count_tokens(text),
                chunk_index=0,
            ))

        return chunks
