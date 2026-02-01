# Phase 9: Search, Templates & Export - Research

**Researched:** 2026-02-01
**Domain:** PostgreSQL Full-Text Search, Document Templates, Markdown Export
**Confidence:** HIGH

## Summary

Phase 9 adds three capabilities: full-text search across documents, document templates (built-in + custom), and Markdown export. The codebase is well-prepared for all three features due to prior architectural decisions.

**Search (SRCH-01/02/03):** The Documents table already stores `content_plain` (populated by `content_converter.py` on every auto-save). PostgreSQL FTS via `tsvector`/`tsquery` is the decided approach (Meilisearch deferred). The implementation requires: (1) a new `search_vector` tsvector column on Documents with a GIN index, (2) a trigger to keep it updated from `title` + `content_plain`, and (3) a search endpoint using `websearch_to_tsquery` for user-friendly query parsing and `ts_headline` for result snippets.

**Templates (TMPL-01/02/03):** Requires a new `DocumentTemplates` table storing TipTap JSON content. Built-in templates are seeded via migration. Custom templates are user-created from existing documents. The "new from template" flow inserts the template's `content_json` as the initial content of a new document. No new libraries needed.

**Export (EXPR-01):** The `content_markdown` field is already populated on every save by `content_converter.py`. The export endpoint simply returns this content. In Electron, the renderer calls `showSaveDialog` (already exposed) then writes via a new `fs:writeFile` IPC handler (needs to be added). No server-side streaming needed since content is already in the database.

**Primary recommendation:** Use PostgreSQL trigger (not generated column) for the search vector so title can be weighted higher than body (`setweight('A')` for title, `setweight('B')` for content). Use `websearch_to_tsquery` for the search endpoint to handle user input gracefully. Export is entirely client-side after fetching the document.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PostgreSQL FTS | Built-in (PG 14+) | tsvector/tsquery search | Decision locked: PG FTS for v1, Meilisearch deferred |
| SQLAlchemy 2.0 | 2.x (existing) | ORM + FTS query construction | Already in stack; `func.to_tsvector`, `func.websearch_to_tsquery` |
| Alembic | Existing | Migration for search vector column + trigger | Standard migration tool |
| FastAPI Response | Built-in | StreamingResponse for export | Already available |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `func` namespace (SQLAlchemy) | 2.x | `to_tsvector`, `websearch_to_tsquery`, `ts_headline`, `ts_rank` | All FTS queries |
| Electron `dialog` | 30 (existing) | `showSaveDialog` for export file location | Export flow |
| Electron `fs` (via IPC) | Node.js built-in | Write markdown file to disk | New IPC handler needed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PG trigger for tsvector | Generated column | Generated columns cannot use `setweight()` for ranking title > body. Trigger is required for weighted search. |
| `websearch_to_tsquery` | `plainto_tsquery` | `websearch_to_tsquery` handles quotes, OR, negation (user-friendly). `plainto_tsquery` converts all terms to AND. Use `websearch_to_tsquery`. |
| Server-side export endpoint | Client-side export (read content_markdown, write to file) | Server endpoint is unnecessary: `content_markdown` is already in the document response. Client can use Electron's `showSaveDialog` + IPC `fs.writeFile` directly. Use **client-side approach**. |
| Separate templates table | JSON file for built-in templates | Database table unifies built-in and custom templates with the same query pattern. Use **database table**. |

### Installation

No new npm packages or pip packages needed. All functionality uses existing stack.

## Architecture Patterns

### Recommended Project Structure

```
fastapi-backend/
├── app/
│   ├── models/
│   │   └── document_template.py       # NEW: DocumentTemplate model
│   ├── schemas/
│   │   ├── document.py                # MODIFY: add search result schema
│   │   └── document_template.py       # NEW: template schemas
│   ├── routers/
│   │   ├── documents.py               # MODIFY: add search endpoint
│   │   └── document_templates.py      # NEW: template CRUD router
│   └── services/
│       └── document_service.py        # MODIFY: add search query builder
├── alembic/
│   └── versions/
│       ├── YYYYMMDD_add_search_vector.py       # NEW: tsvector + trigger + GIN
│       └── YYYYMMDD_add_document_templates.py  # NEW: templates table + seed

electron-app/
├── src/
│   ├── main/
│   │   └── ipc/
│   │       └── handlers.ts            # MODIFY: add fs:writeFile handler
│   ├── preload/
│   │   └── index.ts                   # MODIFY: expose writeFile API
│   └── renderer/
│       ├── components/knowledge/
│       │   ├── search-bar.tsx          # MODIFY: connect to search API
│       │   ├── search-results.tsx      # NEW: search results list
│       │   ├── template-picker.tsx     # NEW: template selection dialog
│       │   └── export-button.tsx       # NEW: export to markdown button
│       └── hooks/
│           ├── use-documents.ts        # MODIFY: add useSearchDocuments
│           └── use-document-templates.ts # NEW: template query hooks
```

### Pattern 1: PostgreSQL FTS with Weighted Trigger

**What:** A database trigger that maintains a `search_vector` tsvector column with weighted terms (title=A, content=B). A GIN index enables fast `@@` matching.

**When to use:** When search needs to rank title matches higher than body matches.

**Example:**

```sql
-- Migration: Add search_vector column
ALTER TABLE "Documents" ADD COLUMN search_vector tsvector;

-- Migration: Create weighted trigger function
CREATE OR REPLACE FUNCTION documents_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.content_plain, '')), 'B');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER documents_search_vector_trigger
  BEFORE INSERT OR UPDATE OF title, content_plain ON "Documents"
  FOR EACH ROW
  EXECUTE FUNCTION documents_search_vector_update();

-- Migration: GIN index for fast search
CREATE INDEX ix_documents_search_vector ON "Documents" USING GIN (search_vector);

-- Migration: Backfill existing documents
UPDATE "Documents" SET search_vector =
  setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(content_plain, '')), 'B');
```

Source: [PostgreSQL FTS Documentation](https://www.postgresql.org/docs/current/textsearch-tables.html)

### Pattern 2: Search Query with Ranking and Snippets

**What:** A SQLAlchemy query that uses `websearch_to_tsquery` for parsing, `ts_rank` for relevance ordering, and `ts_headline` for snippets.

**When to use:** The search endpoint.

**Example:**

```python
from sqlalchemy import func, select, literal_column

async def search_documents(
    query: str,
    scope: str | None,
    scope_id: UUID | None,
    limit: int,
    db: AsyncSession,
) -> list[dict]:
    tsquery = func.websearch_to_tsquery('english', query)

    stmt = (
        select(
            Document.id,
            Document.title,
            Document.application_id,
            Document.project_id,
            Document.user_id,
            Document.updated_at,
            func.ts_rank(Document.search_vector, tsquery).label('rank'),
            func.ts_headline(
                'english',
                Document.content_plain,
                tsquery,
                'StartSel=<mark>, StopSel=</mark>, MaxWords=40, MinWords=15'
            ).label('snippet'),
        )
        .where(Document.search_vector.op('@@')(tsquery))
        .where(Document.deleted_at.is_(None))
        .order_by(literal_column('rank').desc())
        .limit(limit)
    )

    # Optional scope filter
    if scope and scope_id:
        stmt = stmt.where(get_scope_filter(Document, scope, scope_id))

    result = await db.execute(stmt)
    return [dict(row._mapping) for row in result.all()]
```

Source: [SQLAlchemy PostgreSQL Dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html), [PostgreSQL ts_headline](https://www.postgresql.org/docs/current/textsearch-controls.html)

### Pattern 3: Template Data Model

**What:** A `DocumentTemplates` table that stores both built-in and custom templates with TipTap JSON content.

**When to use:** Template management.

**Example:**

```python
class DocumentTemplate(Base):
    __tablename__ = "DocumentTemplates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    content_json = Column(Text, nullable=False)  # TipTap JSON
    is_builtin = Column(Boolean, nullable=False, default=False)
    # Scope: built-in templates have all NULLs; custom templates have owner scope
    application_id = Column(UUID, ForeignKey("Applications.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID, ForeignKey("Users.id", ondelete="CASCADE"), nullable=True)
    created_by = Column(UUID, ForeignKey("Users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

### Pattern 4: Client-Side Markdown Export (Electron)

**What:** Export uses the already-available `content_markdown` field from the document response. The renderer shows a save dialog, then writes the file via a new IPC handler.

**When to use:** EXPR-01 export flow.

**Example (renderer):**

```typescript
async function exportAsMarkdown(document: Document): Promise<void> {
  if (!document.content_markdown) return

  const result = await window.electronAPI.showSaveDialog({
    title: 'Export as Markdown',
    defaultPath: `${sanitizeFilename(document.title)}.md`,
    filters: [{ name: 'Markdown', extensions: ['md'] }],
  })

  if (result.canceled || !result.filePath) return

  await window.electronAPI.writeFile(result.filePath, document.content_markdown)
}
```

**Example (IPC handler in main process):**

```typescript
import { promises as fs } from 'fs'

ipcMain.handle('fs:writeFile', async (_event, filePath: string, content: string) => {
  await fs.writeFile(filePath, content, 'utf-8')
  return { success: true }
})
```

### Anti-Patterns to Avoid

- **Calling `ts_headline` on all matching rows:** `ts_headline` is expensive. Always apply it only to the final paginated result set (LIMIT first, then headline). Use a subquery or CTE to first get matching IDs with rank, then join back for snippets.
- **Using `to_tsquery` for user input:** `to_tsquery` requires strict syntax (AND, OR operators). User input will break it. Always use `websearch_to_tsquery` which handles natural language input.
- **Generating markdown at export time:** The `content_markdown` field is already maintained on every save by `content_converter.py`. Never re-generate it at export time -- just read it.
- **Server-side file download endpoint for Electron:** This is an Electron app, not a browser. The renderer can directly use `showSaveDialog` + `fs.writeFile` via IPC. No need for a server download endpoint.
- **Separate search index table:** PostgreSQL's built-in tsvector column + GIN index on the Documents table is sufficient for v1 scale (tens of thousands of documents). A separate search index adds complexity with no benefit.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Full-text search ranking | Custom LIKE/ILIKE scoring | `ts_rank` + `ts_rank_cd` | Handles stemming, stop words, term proximity, weighted ranking |
| Search query parsing | Custom query parser | `websearch_to_tsquery` | Handles quotes, OR, negation, AND automatically |
| Search result snippets | String slicing around match | `ts_headline` | Handles multi-term highlighting, word-boundary-aware truncation |
| Stemming/stop words | Custom word processing | PostgreSQL `english` config | Handles "running" -> "run", removes "the", "a", etc. |
| File save dialog | Custom file path input | Electron `showSaveDialog` | Native OS file picker, handles permissions, existing file warnings |

**Key insight:** PostgreSQL FTS is a complete search engine -- ranking, snippets, stemming, stop words, phrase matching are all built in. The only code to write is the SQL query and the API endpoint.

## Common Pitfalls

### Pitfall 1: Forgetting to Backfill Search Vectors

**What goes wrong:** The trigger only fires on INSERT/UPDATE. Existing documents will have NULL search vectors and won't appear in search results.
**Why it happens:** Developers add the trigger but forget the backfill step.
**How to avoid:** Include a `UPDATE "Documents" SET search_vector = ...` in the Alembic migration, after creating the trigger.
**Warning signs:** Search returns 0 results despite documents existing.

### Pitfall 2: ts_headline Performance on Large Result Sets

**What goes wrong:** `ts_headline` is called on every matching row, causing slow queries when many documents match.
**Why it happens:** The headline function re-parses the document text for each row.
**How to avoid:** Apply `ts_headline` only to the final paginated results. Use a CTE/subquery: first select IDs + rank with LIMIT, then join back for headline.
**Warning signs:** Search queries taking >500ms.

### Pitfall 3: Search Vector Not Updated on Auto-Save

**What goes wrong:** The trigger fires on `UPDATE OF title, content_plain`, but `save_document_content()` in `document_service.py` updates `content_plain` via Python (SQLAlchemy attribute assignment). The trigger must detect the column change.
**Why it happens:** The trigger uses `BEFORE UPDATE OF title, content_plain` which fires when those columns are included in the UPDATE SET clause -- SQLAlchemy's attribute assignment does generate these columns in the UPDATE statement.
**How to avoid:** Verify the trigger fires by checking `search_vector` is populated after a save. The current `save_document_content()` sets `document.content_plain = tiptap_json_to_plain_text(content_dict)`, which will be included in the UPDATE statement and trigger the vector update.
**Warning signs:** Search vectors stay stale after editing documents.

### Pitfall 4: Template Content Becoming Stale

**What goes wrong:** Built-in template content stored in migrations cannot be updated without a new migration.
**Why it happens:** Templates are seeded in Alembic migrations which only run once.
**How to avoid:** Seed built-in templates with a startup hook or use `INSERT ... ON CONFLICT (name, is_builtin) DO UPDATE` in the migration so re-running is idempotent. Alternatively, store built-in templates as Python constants and upsert on app startup.
**Warning signs:** Built-in templates have outdated content after schema changes.

### Pitfall 5: Missing writeFile IPC Handler for Electron Export

**What goes wrong:** The renderer calls `window.electronAPI.writeFile()` but the IPC handler doesn't exist, causing an unhandled rejection.
**Why it happens:** The preload already exposes `showSaveDialog` but there's no `fs:writeFile` handler registered.
**How to avoid:** Add both the IPC handler in `handlers.ts` and the preload API exposure in `index.ts` before implementing the export UI.
**Warning signs:** Export dialog opens but file is never written.

## Code Examples

### Search Endpoint (FastAPI)

```python
# Source: Verified pattern from PostgreSQL docs + SQLAlchemy dialect docs

@router.get("/search", response_model=DocumentSearchResponse)
async def search_documents(
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    scope: Optional[Literal["application", "project", "personal"]] = Query(None),
    scope_id: Optional[UUID] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentSearchResponse:
    tsquery = func.websearch_to_tsquery('english', q)

    # Subquery: find matching document IDs with rank (no ts_headline yet)
    ranked = (
        select(
            Document.id,
            func.ts_rank(Document.search_vector, tsquery).label('rank'),
        )
        .where(Document.search_vector.op('@@')(tsquery))
        .where(Document.deleted_at.is_(None))
    )

    if scope and scope_id:
        ranked = ranked.where(get_scope_filter(Document, scope, scope_id))

    ranked = ranked.order_by(literal_column('rank').desc()).limit(limit)
    ranked_cte = ranked.cte('ranked')

    # Main query: join back for full fields + ts_headline (only on limited set)
    stmt = (
        select(
            Document.id,
            Document.title,
            Document.application_id,
            Document.project_id,
            Document.user_id,
            Document.updated_at,
            ranked_cte.c.rank,
            func.ts_headline(
                'english',
                func.coalesce(Document.content_plain, ''),
                tsquery,
                'StartSel=<mark>, StopSel=</mark>, MaxWords=40, MinWords=15'
            ).label('snippet'),
        )
        .join(ranked_cte, Document.id == ranked_cte.c.id)
        .order_by(ranked_cte.c.rank.desc())
    )

    result = await db.execute(stmt)
    return DocumentSearchResponse(items=[...])
```

### Search Result Schema (Pydantic)

```python
class DocumentSearchResult(BaseModel):
    id: UUID
    title: str
    application_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    updated_at: datetime
    rank: float
    snippet: str  # HTML with <mark> tags

class DocumentSearchResponse(BaseModel):
    items: list[DocumentSearchResult]
```

### Template CRUD Schemas

```python
class DocumentTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    content_json: str  # TipTap JSON string

class DocumentTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: Optional[str] = None
    content_json: str
    is_builtin: bool
    application_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    created_by: Optional[UUID] = None
    created_at: datetime
```

### Built-In Template Content Examples

```python
BUILTIN_TEMPLATES = {
    "Meeting Notes": {
        "description": "Structured meeting notes with attendees, agenda, and action items",
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
                    {"type": "taskItem", "attrs": {"checked": False}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "[Action] - [Owner]"}]}]},
                ]},
            ]
        }),
    },
    # ... Design Doc, Decision Record, Project Brief, Sprint Retrospective
}
```

### Electron Export Flow

```typescript
// Renderer: export-button.tsx
import { useDocument } from '@/hooks/use-documents'

function ExportButton({ documentId }: { documentId: string }) {
  const { data: doc } = useDocument(documentId)

  const handleExport = async () => {
    if (!doc?.content_markdown) return

    const result = await window.electronAPI.showSaveDialog({
      title: 'Export as Markdown',
      defaultPath: `${doc.title.replace(/[<>:"/\\|?*]/g, '_')}.md`,
      filters: [{ name: 'Markdown', extensions: ['md'] }],
    })

    if (!result.canceled && result.filePath) {
      await window.electronAPI.writeFile(result.filePath, doc.content_markdown)
    }
  }

  return <Button onClick={handleExport}>Export Markdown</Button>
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LIKE/ILIKE queries | tsvector + GIN + `websearch_to_tsquery` | PostgreSQL 11+ (websearch_to_tsquery) | Order of magnitude faster; relevance ranking; stemming |
| Expression index (`to_tsvector(title \|\| body)`) | Stored tsvector column + trigger | Always preferred for multi-column weighted search | Allows `setweight` for title > body ranking |
| `to_tsquery` with manual parsing | `websearch_to_tsquery` | PostgreSQL 11 (2018) | Handles user input without syntax errors |
| Server-side file download in Electron | Client-side IPC `showSaveDialog` + `fs.writeFile` | Electron best practice | Native OS file dialog, no temp files, no server round-trip |

**Deprecated/outdated:**
- `plainto_tsquery`: Still works but `websearch_to_tsquery` is strictly better for user-facing search (supports quotes, negation).
- Expression indexes for FTS: Still valid but stored columns are faster for queries (no re-computation at query time).

## Open Questions

1. **Search across all scopes vs. scoped search**
   - What we know: The search bar in the sidebar currently sets `searchQuery` in KnowledgeBaseContext. The requirements say "search document titles and content" without specifying scope behavior.
   - What's unclear: Should search respect the current scope filter, or search across all documents the user has access to?
   - Recommendation: Support both via optional `scope`/`scope_id` query params on the search endpoint. If scope is provided, search within scope. If omitted, search all accessible documents. The UI can pass the current scope from KnowledgeBaseContext.

2. **Permission filtering on search results**
   - What we know: Documents have scope-based permissions (application/project/personal). Users should only see documents they have access to.
   - What's unclear: The current search bar is a client-side filter. The new server-side search needs permission filtering.
   - Recommendation: For v1, the search endpoint filters by scope (the user already selected their scope). Personal docs filter by `user_id = current_user.id`. Application/project docs are accessible to all members (existing RBAC). The "all" scope case requires a UNION or OR across the user's accessible scopes -- this may need a list of the user's application/project memberships.

3. **Template scope: application-level or global?**
   - What we know: Built-in templates are global. Custom templates need a scope.
   - What's unclear: Should custom templates be per-application, per-user, or both?
   - Recommendation: Custom templates are per-user (personal) or per-application. The `DocumentTemplates` table has optional `application_id` and `user_id` columns (same pattern as Documents). Built-in templates have all scope FKs null + `is_builtin=True`.

## Sources

### Primary (HIGH confidence)
- [PostgreSQL 18 FTS Documentation](https://www.postgresql.org/docs/current/textsearch-tables.html) - tsvector columns, triggers, GIN indexes
- [PostgreSQL ts_headline Documentation](https://www.postgresql.org/docs/current/textsearch-controls.html) - snippet generation, options
- [PostgreSQL FTS Functions](https://www.postgresql.org/docs/current/functions-textsearch.html) - websearch_to_tsquery, ts_rank
- [SQLAlchemy 2.0 PostgreSQL Dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html) - func namespace for FTS
- [FastAPI Custom Responses](https://fastapi.tiangolo.com/advanced/custom-response/) - StreamingResponse
- Codebase: `fastapi-backend/app/services/content_converter.py` - Existing JSON-to-Markdown and JSON-to-plain-text converters
- Codebase: `fastapi-backend/app/services/document_service.py` - `save_document_content()` already populates `content_plain` and `content_markdown`
- Codebase: `electron-app/src/preload/index.ts` - `showSaveDialog` already exposed, `writeFile` IPC handler needed
- Codebase: `electron-app/src/main/ipc/handlers.ts` - IPC handler registration pattern

### Secondary (MEDIUM confidence)
- [Optimizing FTS with tsvector columns and triggers](https://thoughtbot.com/blog/optimizing-full-text-search-with-postgres-tsvector-columns-and-triggers) - trigger vs generated column comparison
- [Mastering FastAPI Responses](https://blog.amritpanta.com.np/2025/4/24/mastering-fastapi-responses-from-json-to-streaming-like-a-pro/) - StreamingResponse patterns

### Tertiary (LOW confidence)
- None - all findings verified with official documentation or codebase inspection

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - PostgreSQL FTS is mature, well-documented, and the decision was locked
- Architecture: HIGH - Patterns verified against official PostgreSQL docs and existing codebase patterns
- Pitfalls: HIGH - Based on PostgreSQL documentation warnings and codebase inspection

**Research date:** 2026-02-01
**Valid until:** 2026-03-01 (stable technology, no fast-moving dependencies)
