# Backend Changes

The backend API surface is **unchanged**. Documents still save via `PUT /api/documents/{id}/content` with `{ content_json, row_version }`. Only the content processing layer needs updates to handle the new canvas JSON format.

## Modified Files

### 1. `content_converter.py` — Text Extraction

Two functions need canvas-aware guards and corresponding helper functions.

#### Markdown Extraction

```python
def tiptap_json_to_markdown(doc: dict[str, Any] | None) -> str:
    if not doc:
        return ""
    if doc.get("format") == "canvas":    # NEW: check before type check
        return _canvas_to_markdown(doc)
    if doc.get("type") != "doc":
        return ""
    return _md_nodes(doc.get("content", []))


def _canvas_to_markdown(canvas: dict[str, Any]) -> str:
    """Extract markdown from all canvas containers, ordered by array index."""
    parts = []
    for i, container in enumerate(canvas.get("containers", []), 1):
        content = container.get("content")
        if content and content.get("type") == "doc":
            md = _md_nodes(content.get("content", []))
            if md.strip():
                parts.append(f"## Section {i}\n\n{md}")
    return "\n".join(parts)
```

Markdown uses `## Section N` headers ordered by array index (not spatial position). This gives structured output for RAG and knowledge graph use cases.

#### Plain Text Extraction

```python
def tiptap_json_to_plain_text(doc: dict[str, Any] | None) -> str:
    if not doc:
        return ""
    if doc.get("format") == "canvas":    # NEW
        return _canvas_to_plain_text(doc)
    if doc.get("type") != "doc":
        return ""
    return _extract_text_from_nodes(doc.get("content", [])).strip()


def _canvas_to_plain_text(canvas: dict[str, Any]) -> str:
    """Extract plain text from all canvas containers for full-text search."""
    parts = []
    for container in canvas.get("containers", []):
        content = container.get("content")
        if content and content.get("type") == "doc":
            text = _extract_text_from_nodes(content.get("content", []))
            if text.strip():
                parts.append(text.strip())
    return "\n\n".join(parts)
```

Plain text uses double newlines (no headers). This is used for Meilisearch full-text indexing where structure is irrelevant.

#### Unchanged

All existing node handlers (`_md_drawio`, `_md_image`, etc.) are unchanged. The canvas helpers delegate to the same `_md_nodes` and `_extract_text_from_nodes` functions.

---

### 2. `document_service.py` — Attachment ID Extraction

The `extract_attachment_ids` function walks the document tree to find image attachment references. It needs to handle the canvas container wrapper.

```python
def extract_attachment_ids(content_json: str) -> Set[str]:
    try:
        content = json.loads(content_json)
    except (json.JSONDecodeError, TypeError):
        return set()

    ids: Set[str] = set()

    def walk(node: dict) -> None:
        if node.get("type") == "image":
            attachment_id = node.get("attrs", {}).get("attachmentId")
            if attachment_id:
                ids.add(attachment_id)
        for child in node.get("content", []):
            if isinstance(child, dict):
                walk(child)

    if isinstance(content, dict):
        if content.get("format") == "canvas":    # NEW: walk canvas containers
            for container in content.get("containers", []):
                container_content = container.get("content")
                if isinstance(container_content, dict):
                    walk(container_content)
        else:
            walk(content)

    return ids
```

The guard checks `format == "canvas"` and iterates through each container's `content`, applying the same recursive `walk` function.

---

## Testing

### Unit Tests for `content_converter.py`

```python
def test_canvas_to_markdown():
    canvas = {
        "format": "canvas",
        "version": 1,
        "viewport": {"scrollX": 0, "scrollY": 0, "zoom": 1},
        "containers": [
            {
                "id": "c1",
                "x": 50, "y": 50,
                "width": 600, "minWidth": 200, "zIndex": 1,
                "content": {
                    "type": "doc",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}]
                }
            },
            {
                "id": "c2",
                "x": 700, "y": 50,
                "width": 600, "minWidth": 200, "zIndex": 2,
                "content": {
                    "type": "doc",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "World"}]}]
                }
            }
        ]
    }
    result = tiptap_json_to_markdown(canvas)
    assert "## Section 1" in result
    assert "Hello" in result
    assert "## Section 2" in result
    assert "World" in result


def test_canvas_to_plain_text():
    canvas = {
        "format": "canvas",
        "version": 1,
        "viewport": {"scrollX": 0, "scrollY": 0, "zoom": 1},
        "containers": [
            {
                "id": "c1",
                "x": 50, "y": 50,
                "width": 600, "minWidth": 200, "zIndex": 1,
                "content": {
                    "type": "doc",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}]
                }
            }
        ]
    }
    result = tiptap_json_to_plain_text(canvas)
    assert result == "Hello"


def test_canvas_empty_containers():
    canvas = {"format": "canvas", "version": 1, "viewport": {"scrollX": 0, "scrollY": 0, "zoom": 1}, "containers": []}
    assert tiptap_json_to_markdown(canvas) == ""
    assert tiptap_json_to_plain_text(canvas) == ""


def test_legacy_doc_unchanged():
    doc = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Legacy"}]}]}
    result = tiptap_json_to_markdown(doc)
    assert "Legacy" in result
    assert "Section" not in result  # No canvas wrapping
```

### Unit Tests for `document_service.py`

```python
def test_extract_attachment_ids_canvas():
    canvas = {
        "format": "canvas",
        "version": 1,
        "viewport": {"scrollX": 0, "scrollY": 0, "zoom": 1},
        "containers": [
            {
                "id": "c1",
                "x": 50, "y": 50,
                "width": 600, "minWidth": 200, "zIndex": 1,
                "content": {
                    "type": "doc",
                    "content": [{
                        "type": "image",
                        "attrs": {"src": "...", "attachmentId": "att-123"}
                    }]
                }
            }
        ]
    }
    ids = extract_attachment_ids(json.dumps(canvas))
    assert ids == {"att-123"}


def test_extract_attachment_ids_legacy():
    doc = {
        "type": "doc",
        "content": [{
            "type": "image",
            "attrs": {"src": "...", "attachmentId": "att-456"}
        }]
    }
    ids = extract_attachment_ids(json.dumps(doc))
    assert ids == {"att-456"}
```

---

## Backward Compatibility

- Legacy documents (no `format` key, `type: "doc"` at top level) are handled by the existing code paths — no changes to their behavior
- The canvas guards (`if doc.get("format") == "canvas"`) are checked before the existing `type == "doc"` checks
- All existing tests must continue to pass unchanged
