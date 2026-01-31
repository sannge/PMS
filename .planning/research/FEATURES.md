# Feature Research

**Domain:** Document / Knowledge Base Systems in Project Management Tools
**Researched:** 2026-01-31
**Confidence:** HIGH (based on analysis of Confluence, Notion, ClickUp, Coda, GitBook, Slite, Monday.com Docs)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Rich text editing (bold, italic, headings, lists)** | Every doc tool has this since 2015. Users won't consider a tool that lacks basic formatting. | LOW | TipTap handles this out of the box. Non-negotiable baseline. |
| **Auto-save** | Notion, Google Docs, ClickUp all auto-save silently. Users no longer expect a "Save" button. Losing work is unforgivable. | MEDIUM | Debounced save on inactivity (2-10s) is standard. Must include a visible "Saved" / "Saving..." indicator. Notion shows a sync status icon; Google Docs shows "Saving..." text. PM Desktop's 10s inactivity debounce is within normal range. |
| **Save status indicator** | Users need confidence their work is persisted. Notion shows a subtle sync checkmark; Google Docs shows "All changes saved" text. Absence creates anxiety. | LOW | Three states minimum: saving, saved, error. Show relative time ("Saved 5s ago") for extra confidence. |
| **Folder/hierarchy organization** | Confluence uses spaces + page trees, Notion uses nested pages, GitBook uses spaces + chapters. Every tool offers hierarchical structure. | MEDIUM | PM Desktop's nested folder approach is standard. Unlimited nesting is common but 3-4 levels deep is practical. |
| **Document scoping to teams/projects** | Confluence scopes to Spaces, Notion to Teamspaces, ClickUp to Spaces/Folders. Users expect docs to live alongside the work they describe. | MEDIUM | PM Desktop's three scopes (personal/application/project) map well to industry norms. The "embedded docs tab" approach (docs inside app/project detail) mirrors ClickUp and Confluence's integration patterns. |
| **Full-text search** | Every tool offers at minimum title + content search. Confluence has advanced search syntax; Notion has global search across all content. Users expect to type a query and find relevant docs. | MEDIUM | Basic database LIKE search is insufficient at scale. Full-text indexing (PostgreSQL tsvector or Meilisearch) is table stakes for 10K+ docs. PM Desktop's phased approach (basic first, Meilisearch later) is acceptable. |
| **Permissions / access control** | Confluence has three-tier (global/space/page). Notion has workspace + page-level sharing. ClickUp has space/folder/doc permissions. Users expect docs to respect existing team permissions. | MEDIUM | PM Desktop's approach of inheriting from Application/Project RBAC is solid. Page-level overrides are common but not required for v1 — scope-level permissions are sufficient when docs are always scoped. |
| **Soft delete / trash** | Notion has 30-day trash. Confluence has per-space trash with configurable retention. Every major tool has a trash/recovery mechanism. Permanent delete without recovery is a dealbreaker. | LOW | PM Desktop's 30-day auto-purge matches Notion exactly. Should include: trash view, search within trash, restore to original location (Notion does this; Confluence restores to root, which is worse UX). |
| **Images in documents** | Paste from clipboard, upload button, drag-and-drop. Notion, Confluence, ClickUp all support inline images. Documents without image support feel like plain-text editors. | MEDIUM | Clipboard paste is the most-used insertion method. Upload and drag-and-drop are expected. Image storage in MinIO (S3-compatible) is the right architecture — never store blobs in the database. |
| **Tables** | Notion, Confluence, ClickUp, Coda all support basic tables. Tables are essential for structured content in technical docs, meeting notes, comparison pages. | MEDIUM | TipTap has a table extension. Resizable columns are expected by users familiar with Notion/Confluence. Basic tables (add/remove rows/columns, merge cells) are table stakes; spreadsheet-level computation is not. |
| **Code blocks** | Any tool used by engineering teams must support syntax-highlighted code blocks. Confluence is criticized for weak code block highlighting. | LOW | TipTap has code block extensions with Prism/Shiki highlighting. Support top 10 languages at minimum. |
| **Checklists / task lists** | Notion, ClickUp, Confluence all have interactive checklists. Expected in meeting notes and action item tracking. | LOW | TipTap has a task list extension. Checkboxes that toggle state are sufficient; linking to actual tasks is a differentiator. |
| **Document templates (built-in)** | Confluence ships 70+ templates. Notion has a 30K+ template marketplace. ClickUp has 1000+ templates. Users expect at least a handful of built-in templates for common use cases. | LOW | 5-8 built-in templates are sufficient for v1: Meeting Notes, Design Doc, Decision Record, Project Brief, Sprint Retrospective, 1-on-1 Notes. More is better but diminishing returns. |
| **@ mentions for people** | Notion, Confluence, ClickUp all support @-mentioning team members in documents. This triggers notifications and creates accountability. | MEDIUM | PM Desktop plans @ mentions for Applications and Projects but not people. People mentions are more expected than entity mentions. Consider adding user @ mentions as table stakes — every competitor has them. |
| **Export (at least one format)** | Notion exports to Markdown, PDF, HTML, CSV. Confluence exports spaces. Users expect to get their data out. | LOW | Markdown export is the minimum viable format and the most useful for developers. PM Desktop's plan to export as .md is sufficient for v1. |
| **Concurrent access handling** | Users expect to not lose work when two people access the same document. Google Docs / Notion use real-time CRDT. Confluence uses collaborative editing or merge-on-save. Doing nothing (last write wins) is unacceptable. | HIGH | PM Desktop's lock-based approach is a valid middle ground. It's simpler than CRDT and provides clear UX ("Being edited by [name]"). Key design decisions: auto-lock release on inactivity (PM Desktop's 30s is reasonable), owner override capability, and graceful handling of crashed clients (server-side lock expiry). |
| **Version history (basic)** | Notion, Confluence, ClickUp all show page history with who edited and when. Users expect to see "what changed" and revert mistakes. | MEDIUM | PM Desktop explicitly defers this to post-v1 but designs schema for it. This is acceptable — many internal tools launch without version history. However, storing snapshots from day one (even without UI) is wise so history exists when the UI ships. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Docs embedded in Application/Project detail pages** | Users can view and edit documents in the context of the work they describe, without switching to a separate Notes screen. Confluence requires navigating to a separate space; Notion requires switching databases. Having an embedded "Docs" tab alongside tasks/kanban is a genuine workflow improvement. | MEDIUM | This is PM Desktop's strongest differentiator. No context-switching between project management and documentation. ClickUp does something similar but it's bolted on. |
| **Three-format content storage (JSON + Markdown + plaintext)** | Storing Markdown alongside editor JSON enables future AI agent consumption without runtime conversion. Most tools store only their editor format and convert on-demand. Pre-generating Markdown on save is a forward-looking architecture choice. | LOW | The conversion cost is paid once per save, not per read. Enables fast AI indexing, search indexing, and export without runtime conversion overhead. |
| **User-created templates** | Notion's community template ecosystem is massive but only works because of their marketplace. Allowing users to save any document as a template (for their team/organization) provides value without marketplace complexity. Confluence supports space-level and global custom templates. | LOW | "Save as template" on any document is high-value, low-effort. Combined with built-in templates, this covers most use cases. |
| **Tag system for cross-cutting organization** | Folders impose a single hierarchy. Tags allow a document to appear in multiple contexts (e.g., "architecture" + "Q1-planning"). Notion uses databases with properties for this; Confluence uses labels. A dedicated tag system alongside folders provides both structured and flexible organization. | MEDIUM | Tags are a genuine organizational improvement over folder-only systems. Filter-by-tag in the sidebar, combined with search, gives users multiple paths to find documents. |
| **@ mentions for Applications and Projects** | Linking documents to project entities creates a navigable knowledge graph. Clicking a @-mentioned project takes you to that project. This is stronger than generic page linking because the entities have semantic meaning in the PM context. | MEDIUM | Notion has page mentions and backlinks. PM Desktop can go further by linking to first-class PM entities (applications, projects) rather than just other documents. Backlinks showing "documents that mention this project" on the project page would be powerful. |
| **Scope-aware Notes screen** | A unified "Notes" screen that shows all documents the user has access to, filterable by scope (All / My Notes / by Application / by Project), is a strong navigation pattern. It gives users a single entry point for all documentation. | MEDIUM | This is similar to Confluence's "Recent" view but scoped to the user's permissions and organizational hierarchy. The scope filter is the key differentiator. |
| **Owner lock override** | Application owners can force-take an editing lock (saving the previous editor's work first). This prevents stuck locks from blocking work when a colleague is unavailable. | LOW | Confluence requires admin intervention or third-party plugins for this. PM Desktop's owner override is a pragmatic solution for enterprise teams. |
| **AI-ready content architecture** | Designing document storage with AI consumption in mind (clean Markdown, section-based splitting by headings, plaintext for search) positions PM Desktop for a future AI knowledge agent that can answer questions from project documentation. | LOW | This is an architecture differentiator, not a user-facing feature. But it enables future features that competitors are racing to add (Notion AI, Confluence Rovo). |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Real-time collaborative editing (CRDT/Yjs) in v1** | "Google Docs does it." Users see it in Notion and Confluence and expect it. | Massive complexity increase: Yjs integration, WebSocket room management per document, conflict resolution, cursor sharing, awareness protocol. For a team PM tool with 5K users, simultaneous editing of the same document is rare. The lock-based approach handles 95%+ of real-world scenarios. CRDT adds weeks of implementation for an edge case. | Lock-based editing with clear "Being edited by [name]" UX. Revisit CRDT if user feedback shows lock contention is a real problem. PM Desktop already has the WebSocket infrastructure to add this later. |
| **Full comment/annotation system on documents** | "Confluence has inline comments." Users want to discuss document content in-place. | Comments add a significant data model (comment threads, resolution state, notifications), UI complexity (inline markers, sidebar threads), and permission considerations. For an internal PM tool, task comments already exist for discussion. Adding a parallel comment system on documents creates confusion about where to discuss things. | Use task comments for discussion. If feedback demands it, add simple document-level comments (not inline) as a later phase. |
| **PDF/HTML export in v1** | "I need to share this with stakeholders who don't have accounts." | PDF generation requires a server-side rendering pipeline (Puppeteer, WeasyPrint, or similar). HTML export requires styling decisions. Both add significant complexity for a use case that Markdown export covers for most technical teams. | Markdown export in v1. Add PDF export in a later phase if requested. Most PM Desktop users will be internal team members with accounts. |
| **Offline editing** | "I want to edit docs on a plane." | Offline editing with sync requires: local storage of document state, conflict resolution when reconnecting, queue management for pending saves, and handling lock conflicts after reconnection. This is one of the hardest problems in document systems. Notion spent years getting offline right. | Require server connection. PM Desktop is an Electron desktop app used in enterprise settings where connectivity is reliable. Defer offline to a future major version. |
| **Notion-style databases in documents** | "Let me create a table that's actually a database with filters and sorts." | Blurs the line between document and database. Adds enormous complexity (custom properties, relation fields, rollups, views). PM Desktop already has project/task data structures for structured information. | Keep documents as rich text. Use the existing project management features for structured data. Documents are for prose, not data. |
| **Unlimited nested page hierarchy** | "I want pages within pages within pages, like Notion." | Deep nesting leads to lost content. Users create 8+ levels deep and can never find anything. Confluence suffers from this — deep page trees become navigation nightmares. | Folders + documents (not pages-within-pages). Limit folder nesting to 4-5 levels. Use tags for cross-cutting organization instead of deeper hierarchy. |
| **Public/external sharing links** | "I want to share a doc with someone outside the organization via link." | Security implications for an enterprise PM tool. Requires token-based access, expiration management, and careful permission scoping. Confluence and Notion both offer this but it's a frequent source of data leaks. | Internal-only access in v1. If needed, export to Markdown and share the file. Add external sharing with proper security controls in a later phase. |
| **Wiki-style page linking with backlinks graph** | "Show me a visual graph of how all my documents connect, like Obsidian." | Graph visualization is compelling in demos but rarely used in practice. Obsidian's graph view is a marketing feature; most users navigate via search or folders. Building a graph renderer adds significant frontend complexity. | Support @ mentions that create navigable links. Show a simple "linked from" list (backlinks) on each document. Skip the visual graph. |

## Feature Dependencies

```
[Rich Text Editor (TipTap)]
    └──requires──> [Image Upload (MinIO)]
    └──requires──> [Table Extension]
    └──requires──> [Code Block Extension]
    └──requires──> [Checklist Extension]

[Auto-Save]
    └──requires──> [Rich Text Editor]
    └──requires──> [Save Status Indicator]
    └──requires──> [Dirty Check (skip redundant saves)]

[Lock-Based Editing]
    └──requires──> [Auto-Save]
    └──requires──> [WebSocket Infrastructure (existing)]
    └──requires──> [Server-Side Lock Expiry]

[Document CRUD]
    └──requires──> [Folder Hierarchy]
    └──requires──> [Scope System (personal/app/project)]
    └──requires──> [Permissions (inherits from RBAC)]

[Templates]
    └──requires──> [Document CRUD]
    └──requires──> [Rich Text Editor]

[Search]
    └──requires──> [Document CRUD]
    └──requires──> [Content Storage (plaintext for indexing)]

[Tags]
    └──requires──> [Document CRUD]
    └──enhances──> [Search (filter by tag)]
    └──enhances──> [Notes Screen Sidebar]

[@ Mentions]
    └──requires──> [Rich Text Editor]
    └──requires──> [Application/Project API (existing)]
    └──enhances──> [Document Linking]

[Trash / Soft Delete]
    └──requires──> [Document CRUD]
    └──requires──> [Auto-Purge Background Job]

[Export (Markdown)]
    └──requires──> [Content Storage (Markdown format)]

[Embedded Docs Tab]
    └──requires──> [Document CRUD]
    └──requires──> [Rich Text Editor]
    └──requires──> [Application/Project Detail Pages (existing)]

[Notes Screen]
    └──requires──> [Document CRUD]
    └──requires──> [Folder Tree Component]
    └──requires──> [Search]
    └──requires──> [Browser-Style Tabs]
```

### Dependency Notes

- **Auto-Save requires Rich Text Editor:** The editor must expose content state and change detection before auto-save can be implemented.
- **Lock-Based Editing requires Auto-Save:** When releasing a lock (on inactivity or manual stop), the system must auto-save first to prevent data loss. Lock and save are tightly coupled.
- **Templates require Document CRUD:** Templates are stored as documents with a `is_template` flag. The document creation flow must exist before templates can be built on top.
- **Search requires Content Storage:** Full-text search indexes plaintext content. The three-format storage pipeline (JSON -> Markdown -> plaintext) must be in place before search indexing works.
- **Tags enhance Search and Notes Screen:** Tags are optional but significantly improve both search filtering and sidebar navigation. They can be added after core document CRUD is stable.
- **Embedded Docs Tab requires full document system:** The embedded experience in Application/Project detail pages reuses the same editor and document components, so the standalone Notes screen should be built first.

## MVP Definition

### Launch With (v1)

Minimum viable product -- what's needed to validate the concept.

- [x] **Document CRUD with folder hierarchy** -- core data model, three scopes, nested folders, unfiled section
- [x] **Rich text editor** -- TipTap with bold, italic, headings, lists, checklists, tables, images, code blocks, links
- [x] **Auto-save with status indicator** -- 10s debounce, "Saved Xs ago" display, save on navigate away
- [x] **Lock-based concurrent access** -- editing lock, "Being edited by [name]" read-only mode, auto-release on inactivity, owner override
- [x] **Notes screen** -- left sidebar (folder tree, search), browser-style tabs, main editor area
- [x] **Basic search** -- title + content search via database (PostgreSQL full-text or LIKE with index)
- [x] **Permissions** -- inherit from Application/Project RBAC (Owner/Editor/Viewer), personal notes private to creator
- [x] **Soft delete with trash** -- 30-day auto-purge, trash view with restore capability
- [x] **Three-format content storage** -- TipTap JSON + Markdown + plaintext generated on save

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] **Built-in templates** (5-8 common types) -- add once document creation flow is validated and usage patterns are clear
- [ ] **User-created templates** ("Save as template") -- add once built-in templates prove the concept
- [ ] **Tag system** -- add once users have enough documents that folder-only organization becomes limiting
- [ ] **@ mentions for Applications and Projects** -- add once the editor is stable and entity linking API is ready
- [ ] **Embedded Docs tab in Application/Project detail** -- add once Notes screen is stable; reuses same components
- [ ] **Markdown export** -- low effort, add whenever content storage pipeline is confirmed working
- [ ] **Scope filter on Notes screen** (All / My Notes / by Application / by Project) -- add once multi-scope usage is validated

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **Meilisearch full-text search** -- defer until document volume exceeds PostgreSQL full-text performance (~50K+ docs)
- [ ] **Version history UI** -- schema supports it from day one, but UI can wait for user demand
- [ ] **@ mentions for users (people mentions)** -- requires notification integration; defer until templates and tags ship
- [ ] **PDF export** -- requires server-side rendering pipeline; defer unless strong user demand
- [ ] **Document-level comments** -- defer until users demonstrate need beyond task comments
- [ ] **Real-time collaborative editing (CRDT)** -- defer unless lock contention becomes a real problem
- [ ] **Backlinks ("linked from" list)** -- defer until @ mention usage generates enough links to make this valuable

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Document CRUD + folders | HIGH | MEDIUM | P1 |
| Rich text editor (full toolbar) | HIGH | MEDIUM | P1 |
| Auto-save + status indicator | HIGH | MEDIUM | P1 |
| Lock-based concurrent access | HIGH | HIGH | P1 |
| Notes screen (sidebar + tabs + editor) | HIGH | HIGH | P1 |
| Permissions (scope-based RBAC) | HIGH | MEDIUM | P1 |
| Basic search (title + content) | HIGH | LOW | P1 |
| Soft delete / trash | HIGH | LOW | P1 |
| Three-format content storage | MEDIUM | MEDIUM | P1 |
| Built-in templates | MEDIUM | LOW | P2 |
| User-created templates | MEDIUM | LOW | P2 |
| Tag system | MEDIUM | MEDIUM | P2 |
| @ mentions (apps/projects) | MEDIUM | MEDIUM | P2 |
| Embedded Docs tab | HIGH | MEDIUM | P2 |
| Markdown export | MEDIUM | LOW | P2 |
| Scope filter on Notes screen | MEDIUM | LOW | P2 |
| Meilisearch integration | MEDIUM | HIGH | P3 |
| Version history UI | MEDIUM | HIGH | P3 |
| @ mentions (users) | MEDIUM | MEDIUM | P3 |
| PDF export | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Confluence | Notion | ClickUp Docs | GitBook | PM Desktop (Our Plan) |
|---------|------------|--------|--------------|---------|----------------------|
| **Rich text editing** | Full WYSIWYG, macros for extended content | Block-based, flexible, databases in docs | Full WYSIWYG, AI writing assist | Notion-like editor + Git workflow | TipTap WYSIWYG with tables, images, code blocks |
| **Auto-save** | Auto-save drafts, publish workflow | Continuous auto-save, sync indicator | Auto-save, no publish concept | Auto-save with Git-style branching | 10s debounce auto-save, "Saved Xs ago" indicator |
| **Concurrent editing** | Real-time collaborative (default) or merge-on-save | Real-time CRDT (Yjs-based) | Real-time collaborative | Branch-based editing, merge requests | Lock-based with owner override |
| **Organization** | Spaces > page trees (unlimited nesting) | Teamspaces > nested pages + databases | Spaces > folders > docs | Spaces > chapters > pages | Scopes (personal/app/project) > folders > docs |
| **Search** | Advanced syntax, AI semantic search (Rovo) | Global search, AI-powered, database filters | Full-text, filter by space/folder | Indexed search, AI-powered | Basic PostgreSQL FTS v1, Meilisearch v2 |
| **Templates** | 70+ built-in, space + global custom templates | 30K+ marketplace, any page is a template | 1000+ template center | Template-based doc creation | 5-8 built-in + user-created |
| **Permissions** | Global/space/page + RBAC roles | Workspace/page + sharing | Space/folder/doc level | Spaces with role-based access | Inherits from Application/Project RBAC |
| **Trash** | Per-space trash, configurable retention, archive option | 30-day trash, restore to original location | Trash with restore | Version history (Git-based) | 30-day auto-purge trash |
| **@ mentions** | Users, pages, Jira issues | Users, pages, dates, databases | Users, tasks, docs | Users | Applications, Projects (users in v2) |
| **Export** | Space-level export (PDF, HTML, XML) | PDF, HTML, Markdown, CSV | PDF, Markdown | PDF, ePub | Markdown (PDF in v2) |
| **Version history** | Full page history, side-by-side diff, revert | Page history, side-by-side compare, revert | Version history with compare | Git-based version control (full history) | Schema supports it; UI deferred to v2 |
| **Comments** | Inline comments, resolved threads | Page comments, inline discussion | Doc comments | N/A | Deferred (use task comments) |
| **Unique strength** | Enterprise-grade, Jira integration, macros | All-in-one workspace, databases, AI | Deep PM integration, AI writing | Git-based workflow, developer-focused | Docs embedded in PM context, AI-ready storage |

## Recommendations for PM Desktop

### What the plan gets right

1. **Lock-based editing is a pragmatic choice.** CRDT is expensive to build and maintain. For an internal PM tool, lock-based editing with clear UX is sufficient. Confluence offered merge-on-save for years before adding real-time collaboration.

2. **Three-format content storage is forward-looking.** No competitor stores Markdown alongside their editor format by default. This positions PM Desktop for AI features without runtime conversion costs.

3. **Scope-based permissions inheriting from RBAC is clean.** Avoids the complexity of page-level permission overrides that Confluence and Notion both struggle with (orphaned permissions, confused users).

4. **30-day trash with auto-purge matches industry standard** (Notion uses the exact same model).

5. **Embedded Docs tab is a genuine differentiator.** No competitor makes it this seamless to access project documentation from the project context.

### What to reconsider

1. **Add @ mentions for users (people), not just entities.** Every competitor supports @-mentioning team members. This is closer to table stakes than a differentiator. Consider adding it to v1.x at minimum.

2. **Version history schema from day one is wise, but consider shipping minimal UI sooner.** Even a simple "last 10 versions" list with restore capability would put PM Desktop ahead of shipping nothing. Confluence and Notion both highlight version history as a key selling point.

3. **Basic search might need to be better than "basic."** PostgreSQL full-text search (tsvector + tsquery) is nearly free to add on top of the existing database and provides significantly better results than LIKE queries. Recommend using PostgreSQL FTS from day one rather than deferring to Meilisearch.

4. **Image resizing in editor is genuinely important.** Users paste screenshots that are too large. Without resize handles, every pasted image fills the full width. This is a common complaint about tools that lack it.

## Sources

- [Confluence vs Notion Comparison (The Digital Project Manager)](https://thedigitalprojectmanager.com/tools/confluence-vs-notion/)
- [Confluence vs Notion (Atlassian Official)](https://www.atlassian.com/software/confluence/comparison/confluence-vs-notion)
- [Notion Auto-Save & Offline Guide](https://www.notion.com/help/guides/working-offline-in-notion-everything-you-need-to-know)
- [Confluence Concurrent Editing (Atlassian Docs)](https://confluence.atlassian.com/doc/concurrent-editing-and-merging-changes-144719.html)
- [Edit Lock for Confluence (Seibert Media)](https://seibert.group/blog/en/edit-lock-for-confluence-better-protection-against-simultaneous-editing-of-confluence-pages/)
- [Notion Delete & Restore Content (Help Center)](https://www.notion.com/help/duplicate-delete-and-restore-content)
- [Confluence Delete or Restore a Page (Atlassian Docs)](https://confluence.atlassian.com/doc/delete-or-restore-a-page-139429.html)
- [Confluence Retention Rules (Atlassian Docs)](https://confluence.atlassian.com/doc/set-retention-rules-to-delete-unwanted-data-1108681072.html)
- [Notion Template Guide (Official)](https://www.notion.com/help/guides/the-ultimate-guide-to-notion-templates)
- [Confluence Templates (Atlassian)](https://www.atlassian.com/software/confluence/templates)
- [Notion Links & Backlinks (Help Center)](https://www.notion.com/help/create-links-and-backlinks)
- [Confluence Page-Level Permissions (Atlassian Support)](https://support.atlassian.com/confluence-cloud/docs/manage-permissions-on-the-page-level/)
- [Confluence RBAC (StiltSoft)](https://stiltsoft.com/blog/role-based-access-control-rbac-in-confluence-cloud/)
- [GitBook Official](https://www.gitbook.com/)
- [GitBook Review 2026 (Research.com)](https://research.com/software/reviews/gitbook)
- [Meilisearch Searchable Knowledge Base](https://www.meilisearch.com/blog/searchable-knowledge-base)
- [ClickUp Features](https://clickup.com/features)
- [GitHub Primer Save Patterns](https://primer.style/ui-patterns/saving/)
- [Outline Knowledge Base (GitHub)](https://github.com/outline/outline)
- [Notion Page History Version Control (ONES Blog)](https://ones.com/blog/notion-page-history-version-control/)

---
*Feature research for: Document / Knowledge Base Systems in Project Management Tools*
*Researched: 2026-01-31*
