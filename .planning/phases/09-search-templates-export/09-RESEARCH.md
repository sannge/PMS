# Phase 9: Search, Templates & Export - Research

**Researched:** 2026-01-31
**Domain:** PostgreSQL full-text search, document templates, Markdown export
**Confidence:** HIGH

## Summary

Phase 9 adds three distinct features to the knowledge base: (1) PostgreSQL full-text search with relevance-ranked results and snippet generation, (2) built-in and custom document templates, and (3) Markdown file export. The project already stores `content_plain` on every document (populated by the Phase 4 content pipeline), which is the ideal field for full-text search indexing. The database is PostgreSQL with asyncpg driver (confirmed from `config.py`, `database.py`, `requirements.txt`, and all Alembic migrations).

For search, the recommended approach is a **stored generated tsvector column** with a **GIN index** on the Documents table, combining `title` and `content_plain` with different weights (A for title, B for content). The search endpoint uses `websearch_to_tsquery` (user-friendly query syntax) with `ts_rank` for ordering and `ts_headline` for snippet generation. All of this is achievable through SQLAlchemy's `func` namespace without additional libraries.

For templates, the simplest approach is a new `DocumentTemplate` model storing template name, description, category (built-in vs custom), scope, and `content_json` (TipTap JSON). Built-in templates are seeded via an Alembic data migration. "Save as template" copies a document's `content_json` into a new template row. "New from template" copies the template's `content_json` into a new document.

For Markdown export, the document's `content_markdown` field (already populated by the Phase 4 auto-save pipeline) is served directly as a file download via FastAPI's `Response` with `Content-Disposition: attachment` header. No conversion is needed at export time.

**Primary recommendation:** Add a generated tsvector column + GIN index via Alembic migration; build search endpoint using `websearch_to_tsquery` + `ts_rank` + `ts_headline`; create a `DocumentTemplate` model with seeded built-in templates; serve `content_markdown` as a downloadable `.md` file.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy `func` (PostgreSQL dialect) | 2.0+ | `to_tsvector`, `websearch_to_tsquery`, `ts_rank`, `ts_headline` | Built into SQLAlchemy's PostgreSQL dialect; no extra packages needed |
| Alembic | 1.14+ | Migration for tsvector column + GIN index | Already in project |
| FastAPI `Response` | 0.115+ | File download response for Markdown export | Built into FastAPI; no extra packages needed |
| `@tanstack/react-query` | 5.90+ | Search query hook with debounce | Already in project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lucide-react` | 0.400+ | Search, Download, FileTemplate icons | Already in project |
| `@radix-ui/react-dialog` | 1.1+ | Template picker dialog, save-as-template dialog | Already in project |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PostgreSQL FTS | Meilisearch | Better relevance ranking and typo tolerance, but adds external service dependency. Deferred to v1.x per project decision |
| Generated tsvector column | Runtime `to_tsvector()` in query | Runtime conversion is slower; cannot use GIN index effectively. Generated column pre-computes on INSERT/UPDATE |
| `websearch_to_tsquery` | `plainto_tsquery` | `plainto_tsquery` does not support quoted phrases or negation operators. `websearch_to_tsquery` accepts natural search syntax ("meeting notes" -draft) |
| Serving `content_markdown` directly | Converting `content_json` to Markdown at export time | Unnecessary work; Phase 4 pipeline already maintains `content_markdown` on every save |
| `@tiptap/markdown` extension for client-side export | Server-side `content_markdown` field | Would require adding new npm dependency (~`@tiptap/markdown`); server already has the data |

**Installation:**
```bash
# Backend - No new packages needed
# All FTS functions available via SQLAlchemy's PostgreSQL dialect
# FastAPI Response is built-in

# Frontend - No new packages needed
# All UI components (Dialog, Input, ScrollArea) already installed
```

## Architecture Patterns

### Recommended Project Structure
```
fastapi-backend/app/
├── models/
│   └── document_template.py     # NEW: DocumentTemplate model
├── schemas/
│   └── document_template.py     # NEW: Template request/response schemas
│   └── document.py              # EXTEND: SearchResult schema
├── routers/
│   └── documents.py             # EXTEND: search endpoint, export endpoint
│   └── document_templates.py    # NEW: template CRUD endpoints
├── services/
│   └── search_service.py        # NEW: FTS query builder
│   └── document_service.py      # EXTEND: template operations
└── tests/
    └── test_search.py           # NEW: FTS query tests
    └── test_templates.py        # NEW: template CRUD tests
    └── test_export.py           # NEW: export endpoint test

electron-app/src/renderer/
├── components/knowledge/
│   ├── search-bar.tsx           # EXTEND: wire to API search (currently local filter only)
│   ├── search-results.tsx       # NEW: search results list with snippets
│   ├── template-picker.tsx      # NEW: dialog for choosing a template
│   └── export-button.tsx        # NEW: download button in editor toolbar
├── hooks/
│   └── use-knowledge-queries.ts # EXTEND: useSearchDocuments, useTemplates queries
└── contexts/
    └── knowledge-base-context.tsx # No changes needed (searchQuery already exists)
```

### Pattern 1: PostgreSQL Full-Text Search with Generated Column

**What:** A stored generated tsvector column on the Documents table that combines title (weight A) and content_plain (weight B). A GIN index on this column enables fast full-text search. The search endpoint uses `websearch_to_tsquery` for user-friendly query parsing.

**When to use:** Any full-text search on PostgreSQL without external search engines.

**Key design decisions:**
- Use `GENERATED ALWAYS AS` stored column rather than a trigger -- simpler, auto-maintained by PostgreSQL on every INSERT/UPDATE.
- Weight title as 'A' (highest) and content as 'B' so title matches rank higher.
- Use `websearch_to_tsquery` which accepts natural search input like `"meeting notes" -draft` without requiring special syntax.
- Apply `ts_headline` ONLY to the final page of results (after LIMIT), not to all matching documents. `ts_headline` is expensive because it operates on the original text, not the tsvector.
- Use `COALESCE` to handle NULL `content_plain` gracefully.

**Alembic migration:**
```python
# Manual migration (Alembic autogenerate has known issues with tsvector expressions)
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Add generated tsvector column
    op.execute("""
        ALTER TABLE "Documents"
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(content_plain, '')), 'B')
        ) STORED
    """)

    # Create GIN index for fast full-text search
    op.execute("""
        CREATE INDEX ix_documents_search_vector
        ON "Documents"
        USING GIN (search_vector)
    """)

def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_documents_search_vector')
    op.execute('ALTER TABLE "Documents" DROP COLUMN IF EXISTS search_vector')
```

**SQLAlchemy model addition:**
```python
from sqlalchemy.dialects.postgresql import TSVECTOR

class Document(Base):
    # ... existing columns ...

    # Generated full-text search vector (read-only, maintained by PostgreSQL)
    search_vector = Column(
        TSVECTOR,
        # Computed is not needed here since we use raw SQL in migration
        # SQLAlchemy just needs to know the column exists for queries
        nullable=True,
    )
```

**Search query pattern:**
```python
from sqlalchemy import func, select, literal_column
from sqlalchemy.dialects.postgresql import TSVECTOR

async def search_documents(
    db: AsyncSession,
    query_text: str,
    scope: str | None = None,
    scope_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Full-text search with ranked results and snippets."""
    ts_query = func.websearch_to_tsquery('english', query_text)

    # Base query: filter by search vector match
    stmt = (
        select(
            Document,
            func.ts_rank(Document.search_vector, ts_query).label('rank'),
            func.ts_headline(
                'english',
                func.coalesce(Document.content_plain, ''),
                ts_query,
                'StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MaxWords=30, MinWords=15'
            ).label('snippet'),
        )
        .where(Document.search_vector.op('@@')(ts_query))
        .where(Document.deleted_at.is_(None))
    )

    # Optional scope filter
    if scope and scope_id:
        stmt = stmt.where(get_scope_filter(Document, scope, scope_id))

    # Order by relevance, then recency
    stmt = stmt.order_by(
        literal_column('rank').desc(),
        Document.updated_at.desc(),
    )
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    return result.all()
```

### Pattern 2: Document Templates with Built-in Seeding

**What:** A `DocumentTemplate` model storing template metadata and content_json. Built-in templates are seeded via an Alembic data migration. Custom templates are created by users from existing documents.

**When to use:** Any document system that needs predefined document structures.

**Key design decisions:**
- Templates are scope-aware: built-in templates have `is_builtin=True` and no scope FKs (available everywhere). Custom templates follow the same scope model as documents (application/project/personal).
- Template content is stored as TipTap JSON (`content_json`) -- the same format used by the editor. No conversion needed when creating a document from a template.
- Built-in templates are seeded as data rows (not hardcoded in application code) so they can be updated via migrations.
- "Save as template" is a POST endpoint that copies a document's current `content_json` and `title` into a new template.

**Model:**
```python
class DocumentTemplate(Base):
    __tablename__ = "DocumentTemplates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    category = Column(String(100), nullable=False, default="custom")
    content_json = Column(Text, nullable=False)
    is_builtin = Column(Boolean, nullable=False, default=False)

    # Scope FKs (null for built-in templates)
    application_id = Column(UUID(as_uuid=True), ForeignKey("Applications.id"), nullable=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("Projects.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("Users.id"), nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("Users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

**Built-in template content examples (TipTap JSON):**
```python
BUILTIN_TEMPLATES = [
    {
        "name": "Meeting Notes",
        "description": "Structured meeting notes with attendees, agenda, and action items",
        "category": "meetings",
        "content_json": json.dumps({
            "type": "doc",
            "content": [
                {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": "Meeting Notes"}]},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Date"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "[Date]"}]},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Attendees"}]},
                {"type": "bulletList", "content": [
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "[Name]"}]}]},
                ]},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Agenda"}]},
                {"type": "orderedList", "content": [
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "[Topic]"}]}]},
                ]},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Discussion"}]},
                {"type": "paragraph"},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Action Items"}]},
                {"type": "taskList", "content": [
                    {"type": "taskItem", "attrs": {"checked": False}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "[Action item]"}]}]},
                ]},
            ]
        }),
    },
    # ... similar structures for Design Doc, Decision Record, Project Brief, Sprint Retrospective
]
```

### Pattern 3: Markdown Export via Direct Response

**What:** A GET endpoint that reads the document's pre-computed `content_markdown` field and returns it as a downloadable `.md` file. No conversion is needed at export time because the Phase 4 auto-save pipeline already maintains `content_markdown` on every save.

**When to use:** Exporting document content as a file download.

**Example:**
```python
from fastapi import Response

@router.get("/{document_id}/export/markdown")
async def export_document_markdown(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export document content as a downloadable Markdown file."""
    doc = await get_document_or_404(document_id, db)

    # Build Markdown content with title as H1
    markdown = f"# {doc.title}\n\n{doc.content_markdown or ''}"

    # Sanitize filename
    safe_title = "".join(c for c in doc.title if c.isalnum() or c in " -_").strip()
    filename = f"{safe_title or 'document'}.md"

    return Response(
        content=markdown.encode("utf-8"),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
```

**Frontend download trigger:**
```typescript
async function downloadMarkdown(documentId: string) {
  const response = await fetch(`/api/documents/${documentId}/export/markdown`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = response.headers.get('Content-Disposition')
    ?.match(/filename="(.+)"/)?.[1] || 'document.md'
  a.click()
  URL.revokeObjectURL(url)
}
```

### Anti-Patterns to Avoid

- **Calling `ts_headline` on all matching rows:** `ts_headline` is expensive. Apply it only to the final paginated result set (subquery pattern: first filter+rank+limit, then apply `ts_headline` to the limited rows).
- **Using `to_tsquery` directly with user input:** `to_tsquery` requires properly formatted tsquery syntax. Raw user input will cause parse errors. Use `websearch_to_tsquery` which handles natural search input safely.
- **Storing templates as JSON config files:** Templates should be database rows so custom templates can be persisted, scoped, and queried alongside documents. Built-in templates are seeded via migration.
- **Converting content_json to Markdown at export time:** The `content_markdown` field is already maintained by the Phase 4 pipeline. Re-converting wastes CPU and risks inconsistency between saved markdown and exported markdown.
- **Using Alembic autogenerate for tsvector columns:** Alembic has known bugs where it repeatedly detects tsvector expression-based indexes as changed, generating spurious migrations. Write the migration manually with raw SQL.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Full-text search | Custom LIKE/ILIKE queries | PostgreSQL tsvector/tsquery + GIN index | LIKE cannot rank results, handle stemming, or generate snippets. FTS handles all of these natively |
| Search snippet generation | Custom string slicing around match | `ts_headline()` PostgreSQL function | Handles multi-word queries, fragment selection, and configurable word boundaries |
| Search query parsing | Custom query tokenizer | `websearch_to_tsquery()` | Handles quoted phrases, negation, OR operators natively with web-search-like syntax |
| File download in browser | Custom blob handling | `<a download>` + `URL.createObjectURL` | Standard browser API, no library needed |
| Template content format | Custom template DSL | TipTap JSON (same as document content_json) | No conversion needed; editor can load template content directly via `setContent()` |

**Key insight:** PostgreSQL's full-text search is comprehensive enough for v1. It handles stemming, ranking, snippets, and phrase search. The `content_plain` field (populated by Phase 4) is the ideal search corpus. No external search engine is needed for this phase.

## Common Pitfalls

### Pitfall 1: tsvector Column Not Updating
**What goes wrong:** Search results don't include recently edited documents.
**Why it happens:** If using triggers instead of generated columns, the trigger might not fire. With generated columns, this cannot happen -- PostgreSQL automatically recomputes the column on every UPDATE.
**How to avoid:** Use `GENERATED ALWAYS AS ... STORED` rather than triggers. Verify with a test: update a document's title, then search for the new title.
**Warning signs:** Newly created/edited documents not appearing in search results.

### Pitfall 2: ts_headline Performance on Large Result Sets
**What goes wrong:** Search endpoint becomes slow (>500ms) when many documents match.
**Why it happens:** `ts_headline` operates on the original document text (not the tsvector), running text analysis on every matched row.
**How to avoid:** Use a subquery pattern: first query filters, ranks, and limits to N rows; outer query applies `ts_headline` only to those N rows. Alternatively, apply `ts_headline` in the application layer after the DB returns results.
**Warning signs:** Search latency increasing linearly with number of matching documents.

### Pitfall 3: Empty Search Query Handling
**What goes wrong:** Empty or whitespace-only search query causes `websearch_to_tsquery` to return an empty tsquery, which matches nothing or causes an error.
**Why it happens:** No input validation before passing to PostgreSQL.
**How to avoid:** Validate `query_text.strip()` is non-empty before executing the FTS query. Return empty results for empty queries. Also handle the case where `websearch_to_tsquery` returns an empty tsquery (e.g., query contains only stop words like "the").
**Warning signs:** 500 errors when user types common words or spaces.

### Pitfall 4: Template Scope Mismatch
**What goes wrong:** User sees templates from a different scope (e.g., project-scoped templates in a personal document view).
**Why it happens:** Template listing endpoint doesn't filter by scope.
**How to avoid:** Template list endpoint should return: (1) all built-in templates (is_builtin=True) + (2) custom templates matching the current scope. The frontend template picker should filter based on the current document's scope.
**Warning signs:** Users seeing irrelevant custom templates in the picker.

### Pitfall 5: Markdown Export with Empty content_markdown
**What goes wrong:** User exports a document and gets an empty `.md` file.
**Why it happens:** Document was created before Phase 4 pipeline was deployed, or `content_markdown` was never populated (e.g., document created via API without content pipeline).
**How to avoid:** In the export endpoint, if `content_markdown` is NULL or empty, fall back to converting `content_json` on the fly using the `tiptap_json_to_markdown()` function from Phase 4's content converter. This is acceptable for export (one-off operation, not hot path).
**Warning signs:** Empty or near-empty Markdown files for documents that have content in the editor.

### Pitfall 6: Alembic Autogenerate Loop for tsvector Indexes
**What goes wrong:** Every `alembic revision --autogenerate` creates a migration to drop and recreate the tsvector GIN index, even when nothing changed.
**Why it happens:** Known Alembic bug (issue #1390) -- expression-based indexes are not properly reflected, so autogenerate always sees them as "changed."
**How to avoid:** Write the tsvector migration manually (not autogenerate). Add the index name to Alembic's exclusion list in `env.py` if needed: `include_name` callback that skips `ix_documents_search_vector`.
**Warning signs:** Duplicate migration files adding/removing the same index.

## Code Examples

### Search Endpoint (FastAPI)
```python
# fastapi-backend/app/routers/documents.py

class SearchResult(BaseModel):
    """Search result with snippet and relevance score."""
    id: UUID
    title: str
    snippet: str
    scope: str  # "application" | "project" | "personal"
    scope_id: UUID
    updated_at: datetime
    rank: float

class SearchResponse(BaseModel):
    """Paginated search response."""
    items: list[SearchResult]
    total_count: int

@router.get("/search", response_model=SearchResponse)
async def search_documents(
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    scope: Optional[Literal["application", "project", "personal"]] = Query(None),
    scope_id: Optional[UUID] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """
    Full-text search across document titles and content.
    Returns relevance-ranked results with content snippets.
    """
    from sqlalchemy import func, literal_column

    ts_query = func.websearch_to_tsquery('english', q)

    # Count total matches
    count_stmt = (
        select(func.count())
        .select_from(Document)
        .where(Document.search_vector.op('@@')(ts_query))
        .where(Document.deleted_at.is_(None))
    )

    # Main query with rank and snippet
    stmt = (
        select(
            Document,
            func.ts_rank(Document.search_vector, ts_query).label('rank'),
            func.ts_headline(
                'english',
                func.coalesce(Document.content_plain, ''),
                ts_query,
                'MaxFragments=2, MaxWords=30, MinWords=15, '
                'StartSel=<mark>, StopSel=</mark>, FragmentDelimiter= ... '
            ).label('snippet'),
        )
        .where(Document.search_vector.op('@@')(ts_query))
        .where(Document.deleted_at.is_(None))
        .order_by(literal_column('rank').desc(), Document.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if scope and scope_id:
        scope_filter = get_scope_filter(Document, scope, scope_id)
        count_stmt = count_stmt.where(scope_filter)
        stmt = stmt.where(scope_filter)

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(stmt)).all()

    items = []
    for doc, rank, snippet in rows:
        # Determine scope
        if doc.application_id:
            doc_scope, doc_scope_id = "application", doc.application_id
        elif doc.project_id:
            doc_scope, doc_scope_id = "project", doc.project_id
        else:
            doc_scope, doc_scope_id = "personal", doc.user_id

        items.append(SearchResult(
            id=doc.id,
            title=doc.title,
            snippet=snippet or "",
            scope=doc_scope,
            scope_id=doc_scope_id,
            updated_at=doc.updated_at,
            rank=rank,
        ))

    return SearchResponse(items=items, total_count=total)
```

### Template CRUD Endpoints (FastAPI)
```python
# fastapi-backend/app/routers/document_templates.py

@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    scope: Optional[Literal["application", "project", "personal"]] = Query(None),
    scope_id: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TemplateResponse]:
    """List available templates: all built-ins + custom templates matching scope."""
    stmt = select(DocumentTemplate).where(
        or_(
            DocumentTemplate.is_builtin == True,
            # Custom templates for current scope
            *(
                [get_scope_filter(DocumentTemplate, scope, scope_id)]
                if scope and scope_id else []
            ),
        )
    )
    result = await db.execute(stmt)
    return [TemplateResponse.model_validate(t) for t in result.scalars().all()]

@router.post("/from-document/{document_id}", response_model=TemplateResponse)
async def save_document_as_template(
    document_id: UUID,
    body: SaveAsTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Save an existing document as a custom template."""
    doc = await get_document_or_404(document_id, db)
    template = DocumentTemplate(
        name=body.name,
        description=body.description,
        category="custom",
        content_json=doc.content_json,
        is_builtin=False,
        created_by=current_user.id,
    )
    # Copy scope from document
    set_scope_fks(template, *get_document_scope(doc))
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return TemplateResponse.model_validate(template)
```

### Frontend Search Results Component
```typescript
// electron-app/src/renderer/components/knowledge/search-results.tsx

interface SearchResult {
  id: string
  title: string
  snippet: string
  scope: string
  scopeId: string
  updatedAt: string
  rank: number
}

function SearchResults({ query }: { query: string }) {
  const { data, isLoading } = useSearchDocuments(query)
  const { selectDocument } = useKnowledgeBase()

  if (!query.trim()) return null
  if (isLoading) return <div className="p-4 text-xs text-muted-foreground">Searching...</div>
  if (!data?.items.length) return <div className="p-4 text-xs text-muted-foreground">No results</div>

  return (
    <div className="flex flex-col gap-1 p-2">
      {data.items.map((result) => (
        <button
          key={result.id}
          onClick={() => selectDocument(result.id)}
          className="text-left p-2 rounded-md hover:bg-muted/50 transition-colors"
        >
          <div className="text-sm font-medium truncate">{result.title}</div>
          <div
            className="text-xs text-muted-foreground line-clamp-2 mt-0.5"
            dangerouslySetInnerHTML={{ __html: result.snippet }}
          />
          <div className="text-xs text-muted-foreground mt-1">
            {formatRelativeTime(result.updatedAt)}
          </div>
        </button>
      ))}
    </div>
  )
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `LIKE '%term%'` queries | `tsvector/tsquery` with GIN index | PostgreSQL 8.3+ (mature) | Stemming, ranking, snippets, 10-100x faster on large tables |
| `to_tsquery` with manual formatting | `websearch_to_tsquery` | PostgreSQL 11+ | User-friendly search syntax without query language knowledge |
| Trigger-maintained tsvector | `GENERATED ALWAYS AS ... STORED` | PostgreSQL 12+ | Simpler, no trigger management, auto-maintained |
| Manual HTML snippet extraction | `ts_headline` with fragment options | PostgreSQL 8.3+ (improved in 12+) | Configurable fragments, word boundaries, highlighting |
| `@tiptap/markdown` for export | Pre-computed `content_markdown` field | Phase 4 design decision | No runtime conversion, no extra dependency |

**Deprecated/outdated:**
- `plainto_tsquery`: Still works but `websearch_to_tsquery` is strictly better for user-facing search (supports phrases, negation)
- `tsvector` triggers: Generated columns (PostgreSQL 12+) are preferred for simplicity
- Separate search index table: Unnecessary when using generated columns on the main table

## Open Questions

1. **Cross-scope search permissions**
   - What we know: Documents have scope (application/project/personal). Users should only see search results from scopes they have access to.
   - What's unclear: Whether search should always be scoped (user must select scope first) or can search across all accessible scopes.
   - Recommendation: For v1, require scope parameter on search (matches existing sidebar scope filter). Cross-scope search can be added later by joining with membership tables.

2. **Search result count performance**
   - What we know: `COUNT(*)` on a full-text search query can be slow on large tables because PostgreSQL must evaluate the tsvector match for every row.
   - What's unclear: At 5000 concurrent users with potentially millions of documents, will the count query be a bottleneck?
   - Recommendation: For v1, include total_count. If it becomes slow, switch to an estimated count (`EXPLAIN` output parsing) or remove total_count in favor of "load more" pagination.

3. **Built-in template updates across versions**
   - What we know: Built-in templates are seeded via migration. If we improve a template, we need a new migration.
   - What's unclear: Should existing documents created from old templates be updated?
   - Recommendation: No. Templates are starting points. New migrations can update built-in template rows (matched by name + is_builtin=True) without affecting documents already created from them.

## Sources

### Primary (HIGH confidence)
- Codebase: `fastapi-backend/app/models/document.py` -- Document model with `content_plain`, `content_markdown`, `content_json` fields
- Codebase: `fastapi-backend/app/services/document_service.py` -- `convert_tiptap_to_markdown()` and `convert_tiptap_to_plain_text()` stubs (Phase 4)
- Codebase: `fastapi-backend/app/routers/documents.py` -- Existing CRUD patterns, scope filtering, cursor pagination
- Codebase: `fastapi-backend/app/config.py` -- PostgreSQL connection string (`postgresql+asyncpg`)
- Codebase: `fastapi-backend/app/database.py` -- Async SQLAlchemy with asyncpg driver
- Codebase: `electron-app/src/renderer/components/knowledge/search-bar.tsx` -- Existing debounced search bar (currently client-side only)
- Codebase: `electron-app/src/renderer/contexts/knowledge-base-context.tsx` -- `searchQuery` and `setSearch` already in context
- [PostgreSQL FTS Documentation](https://www.postgresql.org/docs/current/textsearch-controls.html) -- `ts_headline`, `ts_rank`, `websearch_to_tsquery`
- [SQLAlchemy PostgreSQL Dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html) -- `func` namespace for FTS functions
- [FastAPI Custom Responses](https://fastapi.tiangolo.com/advanced/custom-response/) -- StreamingResponse, Response for file downloads
- `.planning/phases/04-auto-save-content-pipeline/04-RESEARCH.md` -- Content pipeline design (Phase 4 populates content_markdown and content_plain)

### Secondary (MEDIUM confidence)
- [Alembic tsvector index issue #1390](https://github.com/sqlalchemy/alembic/issues/1390) -- Known autogenerate bug with expression-based indexes
- [Full-text Search with PostgreSQL and SQLAlchemy (Medium)](https://amitosh.medium.com/full-text-search-fts-with-postgresql-and-sqlalchemy-edc436330a0c) -- Practical patterns for SQLAlchemy FTS
- [TipTap Markdown Extension docs](https://tiptap.dev/docs/editor/markdown/getting-started/basic-usage) -- `getMarkdown()` and `editor.markdown.serialize()` API
- [SQLAlchemy FTS Issue #5231](https://github.com/sqlalchemy/sqlalchemy/issues/5231) -- Community examples of FTS in SQLAlchemy

### Tertiary (LOW confidence)
- [TipTap Conversion overview](https://tiptap.dev/docs/conversion/getting-started/overview) -- TipTap Pro conversion features (not needed for our approach)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- PostgreSQL FTS is mature (15+ years), SQLAlchemy dialect support confirmed in docs, all infrastructure exists in codebase
- Architecture: HIGH -- Patterns directly follow existing codebase conventions (scope filtering, cursor pagination, model structure)
- Search implementation: HIGH -- PostgreSQL FTS with generated columns and GIN indexes is well-documented and battle-tested
- Templates: HIGH -- Simple CRUD model following existing Document patterns; built-in seeding via Alembic data migration is standard
- Export: HIGH -- Trivial endpoint; `content_markdown` already maintained by Phase 4 pipeline; FastAPI Response is built-in
- Pitfalls: HIGH -- Well-documented PostgreSQL FTS gotchas (ts_headline performance, empty query handling, Alembic autogenerate issues)

**Research date:** 2026-01-31
**Valid until:** 2026-03-02 (stable domain, 30 days)
