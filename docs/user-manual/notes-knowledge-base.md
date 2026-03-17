# Notes & Knowledge Base

PM Desktop includes a powerful knowledge management system for documentation, wikis, diagrams, and team knowledge sharing. Documents are organized hierarchically and support real-time collaborative editing, full-text search, and AI-powered retrieval.

---

## Overview

The Knowledge Base provides:
- Hierarchical document and folder organization
- Rich text editing with TipTap
- Three document scopes: personal, application, and project
- Real-time collaborative editing via document locking and WebSocket sync
- Document locking to coordinate editing
- Presence indicators with cursor positions
- Document snapshots and version history
- Tags for categorization and filtering
- Full-text search via Meilisearch (with semantic and typo-tolerant matching)
- Canvas/Draw.io diagrams
- Batch document import (PDF, DOCX, PPTX, XLSX, VSDX)
- Document embedding for AI-powered search and retrieval
- Soft delete (trash) with restore
- Multi-tab interface for multiple notes
- Role-based permissions (Owner/Manager/Member can edit, Viewers read-only)

---

## Accessing Notes

### From Sidebar

1. Click **Notes** in the left sidebar
2. Notes page opens with the tree view and editor

### Application Context

Notes can be organized by application:
- Each application has its own knowledge base
- Use the Application Selector to switch between applications
- Press `Cmd/Ctrl + K` for quick application search

---

## Document Scopes

Documents can exist in three different scopes:

| Scope | Visible To | Use For |
|-------|-----------|---------|
| **Personal** | Only you | Private notes, drafts, personal reference |
| **Application** | All application members | Shared documentation, team wikis, onboarding guides |
| **Project** | All project members | Project-specific specs, meeting notes, design decisions |

When creating a document, you choose its scope based on who needs access.

---

## Notes Interface

### Layout

The notes interface has three main areas:

| Area | Purpose |
|------|---------|
| **Sidebar (Left)** | Tree view of folders and documents |
| **Tab Bar (Top)** | Open documents as browser-like tabs |
| **Editor (Center)** | Rich text editing area |

### Sidebar Tree

The left sidebar shows:
- **Folders**: Collapsible containers for organization
- **Documents**: Individual notes and documents
- **Hierarchy**: Nested structure with indentation
- **Tags**: Tag indicators on documents
- **Actions**: Right-click context menu for create, rename, delete, move

### Tab Bar

Multiple documents can be open simultaneously:
- Click a document to open it in a tab
- Tab shows document title
- Active tab is highlighted
- Close tabs with the X button
- Right-click for tab options

---

## Creating Documents

### New Root Document

1. Click the **+** button in the notes sidebar header
2. Enter the document title
3. Select the scope (personal, application, or project)
4. Click **Create**

The document appears at the root level of the tree.

### New Child Document

1. Right-click on a folder or document
2. Select **New Child Document**
3. Enter the title
4. Click **Create**

The new document appears nested under the parent.

### New Folder

1. Click the folder **+** button
2. Or right-click and select **New Folder**
3. Enter the folder name
4. Click **Create**

Folders help organize related documents.

---

## Editing Documents

### Opening a Document

- Click a document in the sidebar tree
- Document opens in a new tab
- Editor becomes active

### Rich Text Editor

The TipTap editor supports:

| Format | How to Apply |
|--------|--------------|
| **Bold** | `Ctrl/Cmd + B` |
| *Italic* | `Ctrl/Cmd + I` |
| Underline | `Ctrl/Cmd + U` |
| Heading 1 | `Ctrl/Cmd + Alt + 1` |
| Heading 2 | `Ctrl/Cmd + Alt + 2` |
| Heading 3 | `Ctrl/Cmd + Alt + 3` |
| Bullet List | `Ctrl/Cmd + Shift + 8` |
| Numbered List | `Ctrl/Cmd + Shift + 7` |
| Code Block | ``` (triple backticks) |
| Quote | `>` at line start |
| Link | `Ctrl/Cmd + K` |
| Table | Insert via toolbar |
| Image | Insert via toolbar or drag-and-drop |

### Toolbar

The editor toolbar provides:
- Text formatting buttons
- Heading level selectors
- List toggles
- Link insertion
- Image insertion
- Table creation
- Code block toggle
- Diagram/canvas insertion

### Auto-Save

Changes save automatically:
- Saves as you type (debounced)
- No save button needed
- Last saved indicator shown

---

## Document Locking

Document locking prevents multiple users from making conflicting edits at the same time.

### How Locking Works

- When you start editing a document, you acquire a lock
- Other users see a lock indicator and cannot edit until the lock is released
- The lock holder's name and avatar are displayed
- Locks are released when you close the document or navigate away

### Force-Taking a Lock

If a lock appears stale (the holder may have disconnected):
- An Owner or Manager can force-take the lock
- The original holder is notified that their lock was taken
- This prevents documents from being permanently locked by disconnected users

### Lock Status Indicators

- **Unlocked**: Document is available for editing
- **Locked by you**: You hold the editing lock
- **Locked by another user**: Shows who holds the lock; you can view but not edit

---

## Real-Time Collaborative Editing

Multiple users can view and collaborate on documents in real-time.

### How It Works

- PM Desktop uses document locking with WebSocket-based synchronization
- When you edit a document, it is locked to prevent conflicting changes from others
- Other users can view the document in real-time and see who is currently editing
- Presence indicators show active viewers and the current editor

### Presence Indicators

When others are viewing or editing the same document:
- **Avatar icons**: Appear at the top of the document showing active users
- **Colored cursors**: Each user's cursor has a unique color and name label
- **Selection highlights**: See what text others have selected

### Collaboration Tips

- Use document locking when making major structural changes
- For small edits, real-time co-editing works seamlessly
- Communicate with your team via task comments if coordinating large document changes

---

## Document Snapshots and Version History

PM Desktop automatically saves snapshots of your documents so you can review and restore previous versions.

### Viewing Snapshots

1. Open a document
2. Click the **History** or **Snapshots** button
3. Browse the list of saved versions with timestamps
4. Click a snapshot to preview its content

### Restoring a Previous Version

1. Open the snapshot you want to restore
2. Click **Restore**
3. The document content reverts to the selected snapshot
4. A new snapshot is created for the current content before restoration

---

## Tags

Tags help you categorize and filter documents across your knowledge base.

### Adding Tags

1. Open a document
2. Click the **Tags** area (usually below the title or in the sidebar)
3. Type a tag name and press Enter to add it
4. Add multiple tags to a single document

### Filtering by Tags

1. In the knowledge base sidebar, use the tag filter
2. Select one or more tags
3. The tree view filters to show only documents matching the selected tags

### Tag Best Practices

- Use consistent naming conventions (e.g., lowercase, hyphens)
- Keep tags broad enough to be reusable (e.g., "design", "api", "onboarding")
- Don't over-tag -- 2-5 tags per document is typically sufficient

---

## Organizing Documents

### Moving Documents

Drag and drop to reorganize:
1. Click and hold a document
2. Drag to new location
3. Drop on a folder or between documents
4. Hierarchy updates

### Renaming Documents

1. Right-click the document
2. Select **Rename**
3. Edit the title
4. Press Enter or click Save

### Nesting Documents

Create hierarchy by:
- Creating child documents
- Dragging documents onto folders
- Dropping documents onto other documents

### Expanding/Collapsing

- Click the arrow next to folders
- Collapse to hide children
- Expand to show nested items
- State remembered across sessions

---

## Managing Tabs

### Opening Tabs

- Click any document in the tree
- Each document opens in its own tab
- Tabs remain open until closed

### Switching Tabs

- Click a tab to make it active
- Active tab shows in the editor
- Tab highlight shows current selection

### Closing Tabs

| Action | How |
|--------|-----|
| Close current | Click X on tab |
| Close all | Right-click, then Close All |
| Close others | Right-click, then Close Others |

### Tab Persistence

- Open tabs are saved to session
- Restored when you return
- Active tab remembered

---

## Folders

### Creating Folders

1. Click the folder icon with **+**
2. Or right-click, then **New Folder**
3. Enter folder name
4. Click **Create**

### Folder Behavior

- Folders contain documents and other folders
- Click to expand/collapse
- Cannot be directly edited (just containers)
- Folders can have file attachments associated with them
- Deleting a folder moves contents to trash

---

## Searching Documents

### Quick Search

1. Use the search bar in the notes header
2. Type your search query
3. Results filter in real-time
4. Click to open matching document

### Full-Text Search

Powered by Meilisearch, the search engine provides:
- Fast indexed search across all document content
- Highlighted matches in results
- Ranked results by relevance
- Typo-tolerant matching (finds results even with spelling mistakes)
- Semantic search (finds conceptually related content, not just exact keyword matches)
- Search within the current application scope

### Searching with the AI Assistant

You can also ask Blair to search your knowledge base using natural language. For example:
- "Find documents about our API authentication design"
- "What do our notes say about the deployment process?"

Blair uses a combination of full-text search, semantic search, and typo-tolerant matching to find the most relevant documents.

---

## Canvas and Draw.io Diagrams

The knowledge base supports creating and editing diagrams using the Draw.io integration.

### Creating a Diagram

1. In the editor toolbar, click the **Diagram** or **Canvas** button
2. The Draw.io editor opens within PM Desktop
3. Create your diagram using shapes, connectors, text, and other tools
4. Save to store the diagram within your document

### Editing a Diagram

1. Click on an existing diagram in a document
2. The Draw.io editor opens
3. Make your changes
4. Save to update

### Diagram Features

- Full Draw.io toolset (shapes, connectors, text, styling)
- PNG preview generated automatically for quick viewing
- Diagrams stored within the document structure
- Supports flowcharts, architecture diagrams, wireframes, org charts, and more

See [File Attachments](./files-attachments.md#canvas-diagrams) for more details.

---

## Batch Document Import

You can import multiple files into the knowledge base at once, which is useful for migrating existing documentation.

### Supported Formats

| Format | Extension |
|--------|-----------|
| PDF | .pdf |
| Word | .docx |
| PowerPoint | .pptx |
| Excel | .xlsx |
| Visio | .vsdx |

### How to Import

1. Navigate to a folder in the knowledge base
2. Click the **Import** button
3. Select one or more files from your computer
4. Files are processed and created as documents

### After Import

- Content is extracted from each file
- Documents are indexed for full-text search
- Content is embedded for AI-powered retrieval
- You can edit imported content using the rich text editor

See [File Attachments](./files-attachments.md#batch-document-import) for more details.

---

## Document Embedding and AI Search

Documents in the knowledge base are automatically processed for AI-powered search and retrieval.

### How It Works

- When a document is created or updated, its content is broken into chunks
- Each chunk is converted into a vector embedding (a mathematical representation of its meaning)
- When you search or ask the AI assistant a question, these embeddings are used to find the most relevant content
- This goes beyond keyword matching -- it understands the meaning and context of your query

### Sync Status

A sync badge on each document shows its embedding status:
- **Synced**: Document is fully indexed and available for AI search
- **Syncing**: Document is being processed
- **Pending**: Document is queued for processing

---

## Soft Delete and Restore

Documents use soft deletion (trash) rather than permanent removal, giving you a safety net.

### Deleting a Document

1. Right-click the document
2. Select **Delete**
3. Confirm the deletion

The document moves to the trash and is hidden from the active tree view.

### Restoring a Document

1. Navigate to the trash view
2. Find the deleted document
3. Click **Restore**

The document returns to its original location in the tree.

### Permanent Deletion

Documents in the trash can be permanently deleted if needed. This action is irreversible.

### Deleting Folders

1. Right-click the folder
2. Select **Delete**
3. All contents move to trash

---

## AI Assistant Integration

The AI assistant (Blair) can interact with the knowledge base in several ways:

- **Search**: Ask Blair to find documents on any topic
- **Read**: Blair can read and summarize document content
- **Update**: Ask Blair to update document content (with your confirmation)
- **Delete**: Ask Blair to delete documents (with your confirmation)
- **Export**: Ask Blair to export a document as PDF

All write operations require your confirmation before Blair executes them. Blair respects your role-based permissions.

---

## Application Selector

### Switching Applications

The Knowledge Base can show documents from different applications. To switch:

1. Click the application name in the header
2. Or press `Cmd/Ctrl + K`
3. Search for the target application
4. Click or press Enter to switch

### Command Palette

The `Cmd/Ctrl + K` shortcut opens a quick selector:
- Search by application name
- See project counts
- View last updated time
- Quick keyboard navigation

---

## Permissions

Documents inherit permissions from their scope:
- **Personal documents**: Only visible to you
- **Application documents**: Visible to all application members, editable by Members and above
- **Project documents**: Visible to all project members, editable by Members and above

| Role | Can View | Can Edit | Can Delete |
|------|----------|----------|------------|
| Owner | Yes | Yes | Yes |
| Manager | Yes | Yes | Yes |
| Member | Yes | Yes | Own documents |
| Viewer | Yes | No | No |

---

## Best Practices

### Organization

1. **Use folders logically**: Group by topic, team, or project
2. **Shallow hierarchy**: Avoid too many nesting levels (2-3 deep is ideal)
3. **Clear naming**: Descriptive titles for easy finding
4. **Consistent structure**: Apply patterns across documents
5. **Use tags**: Categorize for cross-cutting concerns

### Content

1. **One topic per document**: Keep documents focused
2. **Use headings**: Create scannable structure
3. **Link related documents**: Cross-reference between documents
4. **Keep updated**: Archive outdated information
5. **Use diagrams**: Visual representations for architecture and processes

### Collaboration

1. **Use document locking**: Lock documents while making major edits
2. **Review regularly**: Keep content current
3. **Assign owners**: Someone responsible for each area
4. **Leverage real-time editing**: Collaborate live with team members
5. **Use tags consistently**: Agree on tag conventions with your team

---

## Keyboard Shortcuts

### Navigation

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + K` | Open application selector |
| `Escape` | Close modal/panel |

### Editor

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + B` | Bold |
| `Cmd/Ctrl + I` | Italic |
| `Cmd/Ctrl + U` | Underline |
| `Cmd/Ctrl + K` | Insert link |
| `Cmd/Ctrl + Z` | Undo |
| `Cmd/Ctrl + Shift + Z` | Redo |

---

## Troubleshooting

### Document Not Saving

**Check**:
- Network connection active
- You hold the document lock (not locked by another user)
- You have edit permissions (Member or above)
- Editor has focus

**Try**:
- Copy content manually as a backup
- Refresh the page
- Check for error messages

### Tree Not Loading

**Check**:
- Application selected
- You have access to the application

**Try**:
- Refresh the page
- Select a different application
- Check for error messages

### Can't Create Documents

**Check**:
- You have Member, Manager, or Owner role
- Application or project is selected

**Try**:
- Verify your permissions
- Contact application owner

### Document Locked by Another User

**Check**:
- See who holds the lock (name displayed on the lock indicator)
- The lock holder may have disconnected

**Try**:
- Wait for the lock to be released
- Contact the lock holder
- Ask an Owner or Manager to force-take the lock if it appears stale

### Search Not Finding Documents

**Check**:
- Document embedding status (sync badge)
- You are searching within the correct application scope

**Try**:
- Wait for the document to finish syncing
- Try different search terms
- Use the AI assistant for semantic search

### Tabs Not Persisting

**Check**:
- LocalStorage enabled
- Not in private/incognito mode

**Try**:
- Clear browser cache
- Check browser settings

---

## Related Topics

- [Applications](./applications.md) - Documents are organized by application
- [Projects](./projects.md) - Project-scoped documents
- [File Attachments](./files-attachments.md) - Document images, diagrams, and imports
- [Members & Permissions](./members-permissions.md) - Access control for documents
- [Tips & Keyboard Shortcuts](./tips-shortcuts.md) - Productivity features
