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

import math
from dataclasses import dataclass
from typing import Any

import tiktoken


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

    # Token bounds for merge/split logic
    MIN_TOKENS = 500
    MAX_TOKENS = 800

    # Spatial proximity threshold for canvas clustering (pixels)
    CANVAS_PROXIMITY_THRESHOLD = 300.0

    def __init__(self, target_tokens: int = 600, overlap_tokens: int = 100) -> None:
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self._encoder = tiktoken.get_encoding("cl100k_base")

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
                text = self._extract_table_text(node)
                if text.strip():
                    blocks.append(_TextBlock(
                        text=text,
                        heading_context=current_heading,
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
        rows = node.get("content", [])
        parts: list[str] = []
        for row in rows:
            cells = row.get("content", [])
            cell_texts: list[str] = []
            for cell in cells:
                text = self._extract_text_recursive(cell.get("content", []))
                cell_texts.append(text.strip())
            parts.append(" | ".join(cell_texts) + "\n")
        return "".join(parts)

    def _extract_drawio_text(self, node: dict[str, Any]) -> str:
        """Extract text from draw.io diagram nodes."""
        import re
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

        texts: list[str] = []
        for cell in root.iter("mxCell"):
            value = cell.get("value", "")
            if value:
                clean = re.sub(r"<[^>]+>", " ", value).strip()
                clean = re.sub(r"\s+", " ", clean)
                if clean:
                    texts.append(clean)

        return "[Diagram] " + " ".join(texts) + "\n" if texts else ""

    def _merge_and_split(self, blocks: list[_TextBlock]) -> list[ChunkResult]:
        """Merge small blocks under same heading; split blocks exceeding MAX_TOKENS."""
        chunks: list[ChunkResult] = []
        current_text = ""
        current_heading: str | None = blocks[0].heading_context if blocks else None
        current_tokens = 0

        for block in blocks:
            # If heading changed and we have accumulated text, flush
            if block.heading_context != current_heading and current_text.strip():
                chunks.append(ChunkResult(
                    text=current_text.strip(),
                    heading_context=current_heading,
                    token_count=current_tokens,
                    chunk_index=0,
                ))
                current_text = ""
                current_tokens = 0
                current_heading = block.heading_context

            # If adding this block would exceed MAX, flush first
            if current_tokens + block.token_count > self.MAX_TOKENS and current_text.strip():
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
                    chunks.append(ChunkResult(
                        text=current_text.strip(),
                        heading_context=current_heading,
                        token_count=current_tokens,
                        chunk_index=0,
                    ))
                    current_text = ""
                    current_tokens = 0

                split_chunks = self._split_large_text(
                    block.text, block.heading_context
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
        import re
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

    # ---- Canvas Chunking ----

    def _chunk_canvas(
        self, content_json: dict[str, Any], title: str
    ) -> list[ChunkResult]:
        """Canvas document chunking pipeline.

        1. Extract text-bearing elements
        2. Build connectivity graph from connectors
        3. Cluster connected/proximate elements
        4. Generate chunk text per cluster
        5. Split oversized clusters
        6. Assign chunk_index
        """
        if not content_json:
            return []

        elements, connectors = self._extract_canvas_elements(content_json)
        if not elements:
            return []

        clusters = self._cluster_canvas_elements(elements, connectors)
        chunks: list[ChunkResult] = []

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
        """Split an oversized cluster at element boundaries."""
        chunks: list[ChunkResult] = []
        current_elements: list[_CanvasElement] = []
        current_tokens = 0

        for elem in cluster:
            elem_text = f"[{elem.type.replace('_', ' ').title()}] {elem.text}"
            elem_tokens = self.count_tokens(elem_text)

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
