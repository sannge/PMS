"""Source reference types for Blair AI agent tool results.

When agent tools return information derived from documents, they attach
structured source references so the frontend can render citations with
links back to the original content. This module defines the shared
data structures for those references.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Source accumulator (ContextVar)
#
# LangGraph tool functions return plain strings, so structured sources
# cannot be passed through ToolMessage.additional_kwargs. Instead, tool
# functions push sources into this ContextVar, and the SSE stream handler
# in ai_chat.py reads them after the run completes.
#
# Usage:
#   - ai_chat.py: call reset_source_accumulator() before streaming,
#     then read get_accumulated_sources() after streaming.
#   - tools_read.py: call push_sources(refs) inside tool functions.
# ---------------------------------------------------------------------------

_source_accumulator: ContextVar[list[dict] | None] = ContextVar(
    "_source_accumulator", default=None
)


def reset_source_accumulator() -> None:
    """Initialize (or reset) the per-request source accumulator."""
    _source_accumulator.set([])


def push_sources(sources: list["SourceReference"]) -> None:
    """Append serialized sources from a tool function."""
    acc = _source_accumulator.get(None)
    if acc is not None:
        acc.extend(s.to_dict() for s in sources)


def get_accumulated_sources() -> list[dict]:
    """Return all accumulated sources for the current request."""
    return _source_accumulator.get(None) or []


@dataclass
class SourceReference:
    """A single source reference pointing to a document chunk.

    Represents a piece of evidence the agent used to formulate its
    response. The frontend renders these as clickable citations that
    navigate to the source document.

    Attributes:
        document_id: UUID of the source document.
        document_title: Human-readable title of the document.
        document_type: Either ``"document"`` (rich text) or ``"canvas"``.
        heading_context: Nearest heading above the chunk, if available.
            Helps users locate the relevant section within the document.
        chunk_text: The actual text content of the chunk that matched.
        chunk_index: Position of the chunk within the document (0-based).
        score: Relevance score from the retrieval system (0.0 to 1.0).
            Higher is more relevant.
        source_type: How this source was found. One of:
            - ``"semantic"``: Vector similarity search
            - ``"keyword"``: Full-text keyword match (Meilisearch)
            - ``"fuzzy"``: Trigram fuzzy match (pg_trgm)
            - ``"sql"``: Retrieved via SQL query tool
        entity_name: Optional entity name for graph/SQL-derived sources
            (e.g., project name, task key). Provides additional context
            for non-document sources.
        application_id: UUID of the application the source document belongs to.
            Used by the frontend for navigation to the correct knowledge tree.
    """

    document_id: str
    document_title: str
    document_type: str  # "document" or "canvas"
    heading_context: str | None
    chunk_text: str
    chunk_index: int
    score: float
    source_type: str  # "semantic", "keyword", "fuzzy", "sql"
    entity_name: str | None = None
    application_id: str | None = None

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary for JSON responses.

        Returns:
            Dict with all fields, suitable for JSON serialization.
        """
        return {
            "document_id": self.document_id,
            "document_title": self.document_title,
            "document_type": self.document_type,
            "heading_context": self.heading_context,
            "chunk_text": self.chunk_text,
            "chunk_index": self.chunk_index,
            "score": self.score,
            "source_type": self.source_type,
            "entity_name": self.entity_name,
            "application_id": self.application_id,
        }


@dataclass
class ToolResultWithSources:
    """A tool result that includes both text for the LLM and structured sources.

    Agent tools return this when they retrieve information from documents
    or the database. The ``text`` field is what the LLM sees in its
    context to formulate a response. The ``sources`` field is passed
    through to the frontend for rendering citations.

    Attributes:
        text: Formatted text response for the LLM. Should be concise
            and contain the key information the LLM needs to answer
            the user's question.
        sources: List of structured source references for the frontend.
            These are rendered as clickable citation links in the UI.
    """

    text: str
    sources: list[SourceReference] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary for JSON responses.

        Returns:
            Dict with ``text`` and ``sources`` (list of dicts).
        """
        return {
            "text": self.text,
            "sources": [s.to_dict() for s in self.sources],
        }

    @property
    def has_sources(self) -> bool:
        """Check if this result includes any source references.

        Returns:
            True if there is at least one source reference.
        """
        return len(self.sources) > 0

    def format_for_llm(self) -> str:
        """Format the result text with inline source markers for the LLM.

        Appends a numbered list of sources at the end of the text so
        the LLM can reference them in its response (e.g., ``[1]``).

        Returns:
            The text with appended source list, or just the text if
            there are no sources.
        """
        if not self.sources:
            return self.text

        source_list = []
        for i, src in enumerate(self.sources, 1):
            label = src.document_title
            if src.heading_context:
                label += f" > {src.heading_context}"
            if src.entity_name:
                label += f" ({src.entity_name})"
            source_list.append(f"[{i}] {label}")

        return self.text + "\n\nSources:\n" + "\n".join(source_list)
