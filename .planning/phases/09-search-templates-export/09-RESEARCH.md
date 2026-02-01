# Phase 9: Search, Templates & Export - Research

**Researched:** 2026-01-31
**Domain:** PostgreSQL full-text search, document templates, Markdown export, SQLAlchemy FTS, Electron file I/O
**Confidence:** HIGH

## Summary

Phase 9 adds three capabilities to the knowledge base: full-text search across document titles and content, document templates (built-in and custom), and Markdown export. The codebase is well-positioned for all three features because Phase 4 already established the three-format content pipeline: `content_json` (editor), `content_markdown` (export-ready), and `content_plain` (search-ready plain text). This means search indexing and Markdown export already have their source data available on every document row.

**Critical finding: The project uses PostgreSQL (asyncpg), not MSSQL.** Despite CLAUDE.md listing "Microsoft SQL Server (via pyodbc)", the actual codebase uses `postgresql+asyncpg` connection strings, `sqlalchemy.dialects.postgresql.UUID`, and all Alembic migrations use PostgreSQL syntax (`gen_random_uuid()`, `now()`). The requirements.txt lists `asyncpg` and `psycopg2-binary`. The "PostgreSQL FTS" decision from the roadmap is therefore directly applicable -- use native `tsvector`/`tsquery` with GIN indexing.

For templates, no external library is needed. Templates are TipTap JSON documents stored either as database rows (custom templates) or as static constants (built-in templates). The "new from template" flow clones `content_json` into a new document. For export, `content_markdown` is already populated by the content pipeline on every save, so the export endpoint simply returns the existing `content_markdown` field. The frontend uses the existing `showSaveDialog` IPC plus a new `writeFile` IPC handler.

**Primary recommendation:** Add a `search_vector` generated `tsvector` column to the Documents table with a GIN index, create a `/documents/search` endpoint using `websearch_to_tsquery` + `ts_rank` + `ts_headline`, add a `DocumentTemplates` table for custom templates with static built-in template definitions, and expose `content_markdown` via a download endpoint that pairs with Electron's existing `showSaveDialog` IPC.

## Critical Database Clarification

The project context (CLAUDE.md) states "Microsoft SQL Server (via pyodbc)" but the actual codebase uses PostgreSQL:

| Evidence | Value |
|----------|-------|
| `fastapi-backend/app/config.py` database_url | `postgresql+asyncpg://...` |
| `fastapi-backend/requirements.txt` | `asyncpg>=0.29.0`, `psycopg2-binary>=2.9.9` |
| SQLAlchemy model UUID type | `sqlalchemy.dialects.postgresql.UUID` |
| Alembic migrations | `gen_random_uuid()`, `now()` PostgreSQL functions |
| `fastapi-backend/app/database.py` | `create_async_engine` with asyncpg |

**Confidence: HIGH** -- All code artifacts consistently show PostgreSQL. The CLAUDE.md MSSQL reference is stale/incorrect.

This means the roadmap decision "PostgreSQL FTS for v1 search" is directly implementable using native `tsvector`/`tsquery` -- no adapter needed.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PostgreSQL FTS | 16+ built-in | Full-text search (tsvector/tsquery/GIN) | Already the project's database; no external dependency |
| SQLAlchemy `Computed` | 2.0+ | Generated tsvector column definition | Native SQLAlchemy pattern for PostgreSQL generated columns |
| Alembic | 1.14+ | Migration for search_vector column and GIN index | Already in project for all schema changes |
| Electron `dialog` | 30.x | Save dialog for Markdown export | Already in project, `showSaveDialog` IPC exists |
| Node.js `fs/promises` | built-in | Write exported Markdown file to disk | No new dependency; used in main process IPC handler |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@tanstack/react-query` | ^5.90.20 | Search query hook with debounce | Already in project; search uses `useQuery` with `keepPreviousData` |
| `lucide-react` | existing | Icons for search results, template picker, export button | Already in project |
| `@radix-ui/react-dialog` | ^1.1.1 | Template picker dialog | Already in project |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PostgreSQL FTS | Meilisearch | Better fuzzy search & typo tolerance, but adds external service dependency; deferred to v1.x per roadmap |
| PostgreSQL FTS | LIKE/ILIKE queries | Simpler but no stemming, ranking, or snippet generation; poor performance on large datasets |
| Database templates | JSON files on disk | Simpler but no custom template persistence; can't share templates across users |
| IPC writeFile | Backend download endpoint | Would work but adds unnecessary network round-trip; Markdown is already on the client (from document response) |

**Installation:**
```bash
# Backend: No new packages needed
# PostgreSQL FTS is built-in, SQLAlchemy Computed is built-in

# Frontend: No new packages needed
# fs/promises is Node.js built-in, dialog IPC already exists
```

## Architecture Patterns

### Recommended Project Structure

```
fastapi-backend/app/
  routers/
    documents.py         # Add GET /documents/search endpoint
    document_templates.py  # New: CRUD for templates
  schemas/
    document.py          # Add SearchResult, SearchResponse schemas
    document_template.py # New: Template schemas
  models/
    document.py          # Add search_vector Computed column
    document_template.py # New: DocumentTemplate model
  services/
    document_service.py  # Add search query builder

electron-app/src/
  renderer/
    hooks/
      use-document-search.ts  # New: search query hook
      use-documents.ts         # Add useExportDocument
      use-document-templates.ts # New: template hooks
    components/knowledge/
      search-results.tsx        # New: search results panel
      template-picker-dialog.tsx # New: template selection dialog
      export-button.tsx         # New: export to Markdown button
  main/ipc/
    handlers.ts          # Add file:writeFile IPC handler
  preload/
    index.ts             # Add writeFile to ElectronAPI
```

### Pattern 1: PostgreSQL Full-Text Search with Generated Column

**What:** Store a precomputed `tsvector` as a generated column, indexed with GIN, and query using `websearch_to_tsquery` for user-friendly search input.

**When to use:** When searching document titles and content with relevance ranking.

**Example (Alembic migration):**
```python
# Source: PostgreSQL docs + SQLAlchemy 2.0 docs
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Add generated tsvector column
    op.add_column(
        'Documents',
        sa.Column(
            'search_vector',
            sa.Column('search_vector', sa.text("tsvector")),
            sa.Computed(
                "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content_plain, ''))",
                persisted=True
            ),
        )
    )
    # Create GIN index for fast full-text search
    op.create_index(
        'ix_documents_search_vector',
        'Documents',
        ['search_vector'],
        postgresql_using='gin',
    )
```

**Example (SQLAlchemy model):**
```python
from sqlalchemy import Column, Computed, Index
from sqlalchemy.dialects.postgresql import TSVECTOR

class Document(Base):
    # ... existing columns ...

    search_vector = Column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content_plain, ''))",
            persisted=True,
        ),
        nullable=True,
    )

    __table_args__ = (
        # ... existing args ...
        Index('ix_documents_search_vector', 'search_vector', postgresql_using='gin'),
    )
```

**Example (Search query):**
```python
from sqlalchemy import func, text

async def search_documents(
    db: AsyncSession,
    query: str,
    scope: str,
    scope_id: UUID,
    limit: int = 20,
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
                'MaxWords=35, MinWords=15, MaxFragments=2'
            ).label('snippet'),
        )
        .where(Document.search_vector.op('@@')(tsquery))
        .where(Document.deleted_at.is_(None))
        .where(get_scope_filter(Document, scope, scope_id))
        .order_by(text('rank DESC'))
        .limit(limit)
    )

    result = await db.execute(stmt)
    return result.mappings().all()
```

### Pattern 2: Template Storage (Built-in + Custom)

**What:** Built-in templates are static Python/TypeScript constants (TipTap JSON). Custom templates are stored in a `DocumentTemplates` table with the same scope model as documents.

**When to use:** For "New from template" flow.

**Example (Built-in template constant):**
```python
BUILT_IN_TEMPLATES = {
    "meeting-notes": {
        "name": "Meeting Notes",
        "description": "Structured meeting notes with agenda, attendees, and action items",
        "content_json": json.dumps({
            "type": "doc",
            "content": [
                {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": "Meeting Notes"}]},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Date"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "[Date]"}]},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Attendees"}]},
                {"type": "bulletList", "content": [
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "[Name]"}]}]}
                ]},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Agenda"}]},
                {"type": "paragraph"},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Discussion"}]},
                {"type": "paragraph"},
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Action Items"}]},
                {"type": "taskList", "content": [
                    {"type": "taskItem", "attrs": {"checked": False}, "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "[Action item]"}]}
                    ]}
                ]}
            ]
        })
    },
    # ... other templates
}
```

### Pattern 3: Markdown Export via Electron IPC

**What:** The document's `content_markdown` field (populated by the content pipeline on every save) is written to disk via Electron's `dialog.showSaveDialog()` + `fs.writeFile()`.

**When to use:** Export button in the editor toolbar or document context menu.

**Example (Frontend):**
```typescript
async function exportAsMarkdown(document: Document) {
  const result = await window.electronAPI.showSaveDialog({
    title: 'Export as Markdown',
    defaultPath: `${document.title.replace(/[<>:"/\\|?*]/g, '_')}.md`,
    filters: [{ name: 'Markdown', extensions: ['md'] }],
  })

  if (result.canceled || !result.filePath) return

  const markdown = document.content_markdown || ''
  await window.electronAPI.writeFile(result.filePath, markdown)
}
```

**Example (Main process IPC handler):**
```typescript
import { writeFile } from 'fs/promises'

ipcMain.handle('file:writeFile', async (_event, filePath: string, content: string) => {
  await writeFile(filePath, content, 'utf-8')
})
```

### Anti-Patterns to Avoid

- **Don't use LIKE '%query%' for search:** No stemming, no ranking, no snippets, O(n) table scan. Use `tsvector`/`tsquery` with GIN index.
- **Don't call `to_tsvector()` in the WHERE clause without an index:** This forces a sequential scan. Use a stored generated column with a GIN index.
- **Don't convert JSON to Markdown at export time:** The content pipeline already populates `content_markdown` on every save. Just read it.
- **Don't store built-in templates in the database:** They should be static constants that ship with the app. Only custom templates go in the database.
- **Don't use `to_tsquery()` for user input:** It will throw syntax errors on malformed input. Use `websearch_to_tsquery()` which never errors and supports intuitive web-search syntax.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Full-text search | Custom LIKE queries with string matching | PostgreSQL FTS (`tsvector`/`tsquery`/GIN) | Stemming, stop words, ranking, snippets, GIN index performance |
| Search snippet generation | Custom string slicing around matched terms | `ts_headline()` | Handles word boundaries, multiple fragments, configurable length |
| Query parsing | Custom tokenizer for user search input | `websearch_to_tsquery()` | Handles quotes, OR, negation, never throws syntax errors |
| File save dialog | Custom modal with path input | `dialog.showSaveDialog()` | Native OS dialog, recent locations, file type filters |
| Relevance ranking | Custom scoring algorithm | `ts_rank()` / `ts_rank_cd()` | Considers term frequency, word weights, document length normalization |

**Key insight:** PostgreSQL FTS is a complete search engine with tokenization, stemming, ranking, and snippets. The only thing it lacks compared to Meilisearch is fuzzy/typo-tolerant matching, which is explicitly deferred to v1.x.

## Common Pitfalls

### Pitfall 1: tsvector Column Not Updating on content_plain Changes

**What goes wrong:** The `search_vector` generated column depends on `title` and `content_plain`. If the content pipeline writes `content_plain` correctly but the generated column doesn't update, search returns stale results.
**Why it happens:** PostgreSQL `GENERATED ALWAYS AS ... STORED` columns update automatically when their source columns change -- this is not actually an issue with generated columns. The real risk is if `content_plain` is empty/null because the content pipeline failed.
**How to avoid:** Ensure the existing `save_document_content()` service always runs the content pipeline. Add a NOT NULL default of empty string for `content_plain` if needed.
**Warning signs:** New documents appear in search but edits don't update search results.

### Pitfall 2: GIN Index Not Used Due to Missing Configuration Name

**What goes wrong:** Queries use `to_tsvector(text)` (1-argument) but the index was built with `to_tsvector('english', text)` (2-argument). PostgreSQL won't use the index.
**Why it happens:** The 1-argument form uses `default_text_search_config` session variable, which may differ from the index.
**How to avoid:** Always use the 2-argument form with explicit `'english'` configuration in both the generated column definition AND the query. Match them exactly.
**Warning signs:** Search queries are slow despite GIN index existing.

### Pitfall 3: Search on Empty/Short Queries

**What goes wrong:** User types a single character or common stop word, `websearch_to_tsquery` returns empty result or matches everything.
**Why it happens:** Stop words like "the", "a", "is" are removed by the text search configuration. Single characters are too short.
**How to avoid:** Enforce minimum query length (2-3 characters) on the frontend. If `websearch_to_tsquery` returns an empty tsquery, fall back to a title ILIKE search or return empty results.
**Warning signs:** Search returns 0 results for short common words.

### Pitfall 4: Alembic Detecting False Changes on tsvector Index

**What goes wrong:** Every `alembic revision --autogenerate` detects the GIN index as changed and tries to drop/recreate it.
**Why it happens:** Known Alembic issue (#1390) with `to_tsvector()` expression indexes -- Alembic can't properly compare functional index expressions.
**How to avoid:** Use a generated column + simple GIN index on the column (not an expression index). This avoids the autogenerate comparison issue.
**Warning signs:** Alembic generates migration that drops and recreates the same index.

### Pitfall 5: Export Filename Sanitization

**What goes wrong:** Document title contains characters invalid for filenames (`< > : " / \ | ? *`), causing `writeFile` to fail.
**Why it happens:** Users can name documents anything; filesystem has restrictions.
**How to avoid:** Sanitize the title when generating the default filename: replace invalid chars with underscore.
**Warning signs:** Export fails silently or throws OS-level error.

### Pitfall 6: Template content_json Becomes Stale After Editor Schema Changes

**What goes wrong:** Built-in templates use a specific TipTap JSON structure. If the editor extensions change (e.g., new required attributes), templates produce invalid content.
**Why it happens:** Templates are static JSON snapshots, but the editor schema evolves.
**How to avoid:** Keep templates simple (use basic nodes: headings, paragraphs, lists, task lists). Include `schema_version` with templates. Test that all templates render correctly in the editor.
**Warning signs:** Creating a document from a template shows empty content or console errors.

## Code Examples

### Search Endpoint (FastAPI Router)

```python
# Source: PostgreSQL docs + project patterns
@router.get("/search", response_model=SearchResponse)
async def search_documents(
    q: str = Query(..., min_length=2, max_length=200, description="Search query"),
    scope: Literal["application", "project", "personal"] = Query(...),
    scope_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    tsquery = func.websearch_to_tsquery('english', q)

    stmt = (
        select(
            Document.id,
            Document.title,
            Document.application_id,
            Document.project_id,
            Document.user_id,
            Document.folder_id,
            Document.updated_at,
            func.ts_rank(Document.search_vector, tsquery).label('rank'),
            func.ts_headline(
                'english',
                func.coalesce(Document.content_plain, ''),
                tsquery,
                'MaxWords=35, MinWords=15, MaxFragments=2, StartSel=<mark>, StopSel=</mark>'
            ).label('snippet'),
        )
        .where(Document.search_vector.op('@@')(tsquery))
        .where(Document.deleted_at.is_(None))
        .where(get_scope_filter(Document, scope, scope_id))
        .order_by(text('rank DESC'))
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.mappings().all()

    return SearchResponse(
        items=[SearchResultItem(**row) for row in rows],
        query=q,
        total=len(rows),
    )
```

### Search Result Schema (Pydantic)

```python
class SearchResultItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    application_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    folder_id: Optional[UUID] = None
    updated_at: datetime
    rank: float
    snippet: str

class SearchResponse(BaseModel):
    items: list[SearchResultItem]
    query: str
    total: int
```

### DocumentTemplate Model

```python
class DocumentTemplate(Base):
    __tablename__ = "DocumentTemplates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    content_json = Column(Text, nullable=False)

    # Scope (same pattern as Documents)
    application_id = Column(UUID(as_uuid=True), ForeignKey("Applications.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("Users.id", ondelete="CASCADE"), nullable=True)

    # Is this a built-in template? (built-ins are created on first access, not stored)
    is_builtin = Column(Boolean, nullable=False, default=False)

    created_by = Column(UUID(as_uuid=True), ForeignKey("Users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

### Frontend Search Hook

```typescript
// Source: project patterns (use-documents.ts)
export function useDocumentSearch(
  query: string,
  scope: string,
  scopeId: string | null,
): UseQueryResult<SearchResponse, Error> {
  const token = useAuthStore((s) => s.token)
  const userId = useAuthStore((s) => s.user?.id ?? null)

  return useQuery({
    queryKey: ['documentSearch', query, scope, scopeId],
    queryFn: async () => {
      const resolved = resolveScope(scope, scopeId, userId)
      if (!resolved) return { items: [], query, total: 0 }

      const params = new URLSearchParams({
        q: query,
        scope: resolved.apiScope,
        scope_id: resolved.apiScopeId,
      })

      const response = await window.electronAPI.get<SearchResponse>(
        `/api/documents/search?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }
      return response.data
    },
    enabled: !!token && query.length >= 2 && (scope === 'personal' || !!scopeId),
    staleTime: 10_000,
    placeholderData: (prev) => prev, // keepPreviousData equivalent
  })
}
```

### Electron File Write IPC

```typescript
// Main process (handlers.ts)
import { writeFile } from 'fs/promises'

ipcMain.handle(
  'file:writeFile',
  async (_event, filePath: string, content: string) => {
    await writeFile(filePath, content, 'utf-8')
  }
)

// Preload (index.ts)
writeFile: (filePath: string, content: string) =>
  ipcRenderer.invoke('file:writeFile', filePath, content) as Promise<void>,
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LIKE '%query%' | PostgreSQL FTS (tsvector/tsquery) | PostgreSQL 8.3+ (2008) | Stemming, ranking, GIN index performance |
| `to_tsquery()` for user input | `websearch_to_tsquery()` | PostgreSQL 11 (2018) | Never throws syntax errors, intuitive syntax |
| Expression index on `to_tsvector()` | Generated `STORED` column + simple GIN index | PostgreSQL 12 (2019) | Avoids Alembic autogenerate false positives, cleaner model |
| Manual tsvector trigger | `GENERATED ALWAYS AS ... STORED` | PostgreSQL 12 (2019) | No trigger maintenance, automatic updates |

**Deprecated/outdated:**
- `to_tsquery()` for raw user input: Use `websearch_to_tsquery()` instead (safer, more intuitive)
- Trigger-based tsvector maintenance: Use generated columns instead (simpler, automatic)
- GiST indexes for FTS: GIN is preferred for text search (faster reads, acceptable write overhead)

## Open Questions

1. **Cross-scope search ("All" scope)**
   - What we know: The search endpoint requires a scope filter. The sidebar has an "All" scope option.
   - What's unclear: Should "All" scope search across all documents the user has access to? This requires permission-aware querying (user's applications + projects + personal).
   - Recommendation: For v1, support "All" by running the search with a permission-based filter (user's application memberships + personal docs). This is a UNION or OR-based query that may need optimization later.

2. **Search result highlighting in HTML**
   - What we know: `ts_headline` returns text with `<mark>` tags for highlighting.
   - What's unclear: Should the frontend render these as HTML (using `dangerouslySetInnerHTML`) or parse them into React elements?
   - Recommendation: Use `dangerouslySetInnerHTML` since `ts_headline` output is server-controlled and not user-injectable. Alternatively, use custom delimiters (e.g., `||START||` / `||END||`) and split/render in React for safety.

3. **Template sharing scope**
   - What we know: Built-in templates are global. Custom templates need a scope.
   - What's unclear: Should custom templates be scoped per-application (shared with team) or per-user (private)?
   - Recommendation: Scope custom templates per-application (team shared) with an optional user_id for private templates. This matches the document scope model.

## Sources

### Primary (HIGH confidence)
- [PostgreSQL 18 FTS Documentation](https://www.postgresql.org/docs/current/textsearch-intro.html) - tsvector, tsquery, ts_rank, ts_headline, websearch_to_tsquery
- [PostgreSQL 18 Tables and Indexes](https://www.postgresql.org/docs/current/textsearch-tables.html) - Generated columns, GIN indexes
- [PostgreSQL 18 Text Search Controls](https://www.postgresql.org/docs/current/textsearch-controls.html) - ts_rank, ts_headline options, websearch_to_tsquery syntax
- Codebase analysis - All Document model, router, schema, service, content_converter files verified
- [SQLAlchemy 2.0 PostgreSQL dialect docs](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html) - TSVECTOR type, match() operator, GIN index

### Secondary (MEDIUM confidence)
- [SQLAlchemy FTS with PostgreSQL (Amitosh)](https://amitosh.medium.com/full-text-search-fts-with-postgresql-and-sqlalchemy-edc436330a0c) - Computed column pattern, GIN index SQLAlchemy syntax
- [Electron Dialog API](https://www.electronjs.org/docs/latest/api/dialog) - showSaveDialog options and return values
- [Alembic GIN index issue #1390](https://github.com/sqlalchemy/alembic/issues/1390) - Known autogenerate false positive with expression indexes

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - PostgreSQL FTS is mature (15+ years), all libraries already in project
- Architecture: HIGH - Patterns directly derived from PostgreSQL docs and verified against codebase
- Pitfalls: HIGH - Well-documented PostgreSQL FTS gotchas confirmed with official docs
- Templates: MEDIUM - Template data model is standard CRUD; built-in template JSON structure needs validation against actual editor

**Research date:** 2026-01-31
**Valid until:** 2026-03-01 (stable domain, PostgreSQL FTS rarely changes)
