"""Draw.io knowledge graph triple extraction.

Parses draw.io XML from TipTap document JSON to extract subject-predicate-object
triples from diagram connections. Used for knowledge graph construction.

Draw.io XML format:
  - vertex="1" = shape node
  - edge="1" = connection with source/target cell IDs
  - value attr = label text (may contain HTML)
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass
class GraphTriple:
    """A subject-predicate-object triple extracted from a draw.io diagram."""

    subject: str
    predicate: str
    object: str
    document_id: UUID
    edge_id: str


def _strip_html_tags(text: str) -> str:
    """Strip HTML tags from draw.io label text."""
    clean = re.sub(r"<[^>]+>", " ", text).strip()
    return re.sub(r"\s+", " ", clean)


def extract_graph_triples(
    content_json: dict[str, Any] | None,
    document_id: UUID,
) -> list[GraphTriple]:
    """Extract knowledge graph triples from draw.io nodes in TipTap JSON.

    Walks the TipTap JSON document tree, finds drawio nodes, parses their
    XML data, and extracts triples from edges with explicit source/target.

    Supports both regular documents (type="doc") and canvas documents
    (format="canvas") which contain multiple TipTap docs in containers.

    Args:
        content_json: TipTap JSON document (type="doc" root),
                      or a canvas document (format="canvas").
        document_id: UUID of the document containing the diagrams.

    Returns:
        List of GraphTriple instances.
    """
    if not content_json:
        return []

    triples: list[GraphTriple] = []

    if content_json.get("format") == "canvas":
        containers = content_json.get("containers")
        if isinstance(containers, list):
            for container in containers:
                if not isinstance(container, dict):
                    continue
                content = container.get("content")
                if isinstance(content, dict) and content.get("type") == "doc":
                    _walk_nodes(content.get("content", []), document_id, triples)
    elif content_json.get("type") == "doc":
        _walk_nodes(content_json.get("content", []), document_id, triples)

    return triples


def _walk_nodes(
    nodes: list[dict[str, Any]],
    document_id: UUID,
    triples: list[GraphTriple],
) -> None:
    """Recursively walk TipTap nodes to find drawio nodes."""
    for node in nodes:
        if node.get("type") == "drawio":
            _extract_from_drawio(node.get("attrs", {}), document_id, triples)
        elif "content" in node:
            _walk_nodes(node["content"], document_id, triples)


def _extract_from_drawio(
    attrs: dict[str, Any],
    document_id: UUID,
    triples: list[GraphTriple],
) -> None:
    """Parse draw.io XML and extract triples from edges."""
    xml_data = attrs.get("data")
    if not xml_data:
        return

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return

    # Build cell map: id -> cleaned label
    cell_map: dict[str, str] = {}
    for cell in root.iter("mxCell"):
        cell_id = cell.get("id", "")
        value = cell.get("value", "")
        if cell_id and value:
            cell_map[cell_id] = _strip_html_tags(value)

    # Extract triples from edges
    for cell in root.iter("mxCell"):
        if cell.get("edge") != "1":
            continue

        source_id = cell.get("source", "")
        target_id = cell.get("target", "")

        if not source_id or not target_id:
            continue

        subject = cell_map.get(source_id, "")
        obj = cell_map.get(target_id, "")

        if not subject or not obj:
            continue

        edge_label = cell.get("value", "")
        predicate = _strip_html_tags(edge_label) if edge_label else "connected_to"

        triples.append(
            GraphTriple(
                subject=subject,
                predicate=predicate,
                object=obj,
                document_id=document_id,
                edge_id=cell.get("id", ""),
            )
        )
