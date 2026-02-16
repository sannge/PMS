# Notes & Knowledge Base

PM Desktop includes a powerful note-taking system for documentation, wikis, and team knowledge sharing. Notes are organized hierarchically within applications.

---

## Overview

The Knowledge Base provides:
- Hierarchical note organization (folders and documents)
- Rich text editing with TipTap
- Multi-tab interface for multiple notes
- Multi-scope organization (application, project, or personal)
- Document locking for exclusive edit access
- Full-text search (Meilisearch)
- Soft delete with trash and restore
- Tag-based document organization
- Role-based permissions (Owner/Editor/Viewer)

---

## Accessing Notes

### From Sidebar

1. Click **Notes** in the left sidebar
2. Notes page opens with the tree view and editor

### Document Scopes

Notes are organized by scope:
- **Application scope**: Shared knowledge base for an entire application
- **Project scope**: Documentation specific to a project
- **Personal scope**: Private notes for the current user
- Use the tab bar to switch between scopes

---

## Notes Interface

### Layout

The notes interface has three main areas:

| Area | Purpose |
|------|---------|
| **Sidebar (Left)** | Tree view of folders and notes |
| **Tab Bar (Top)** | Open notes as browser-like tabs |
| **Editor (Center)** | Rich text editing area |

### Sidebar Tree

The left sidebar shows:
- **Folders**: Collapsible containers for organization
- **Documents**: Individual notes
- **Hierarchy**: Nested structure with indentation
- **Actions**: Right-click context menu

### Tab Bar

Multiple notes can be open simultaneously:
- Click a note to open it in a tab
- Tab shows note title
- Active tab is highlighted
- Close tabs with the X button
- Right-click for tab options

---

## Creating Notes

### New Root Note

1. Click the **+** button in the notes sidebar header
2. Enter the note title
3. Click **Create**

The note appears at the root level of the tree.

### New Child Note

1. Right-click on a folder or note
2. Select **New Child Note**
3. Enter the title
4. Click **Create**

The new note appears nested under the parent.

### New Folder

1. Click the folder **+** button
2. Or right-click and select **New Folder**
3. Enter the folder name
4. Click **Create**

Folders help organize related notes.

---

## Editing Notes

### Opening a Note

- Click a note in the sidebar tree
- Note opens in a new tab
- Editor becomes active

### Rich Text Editor

The TipTap editor supports:

| Format | How to Apply |
|--------|--------------|
| **Bold** | `Ctrl/Cmd + B` |
| *Italic* | `Ctrl/Cmd + I` |
| Heading 1 | `Ctrl/Cmd + Alt + 1` |
| Heading 2 | `Ctrl/Cmd + Alt + 2` |
| Bullet List | `Ctrl/Cmd + Shift + 8` |
| Numbered List | `Ctrl/Cmd + Shift + 7` |
| Code Block | ``` (triple backticks) |
| Quote | `>` at line start |
| Link | `Ctrl/Cmd + K` |

### Toolbar

The editor toolbar provides:
- Text formatting buttons
- Heading level selectors
- List toggles
- Link insertion
- Code block toggle

### Edit Mode and Saving

Documents use a lock-based editing workflow:
1. Click **Edit** to acquire a document lock
2. Make your changes in the editor
3. Click **Save** to persist changes and release the lock
4. Or click **Discard** to abandon changes
- Local drafts auto-save to IndexedDB every 2 seconds (for crash recovery)
- Only one user can edit a document at a time (lock-based)

---

## Organizing Notes

### Moving Notes

Drag and drop to reorganize:
1. Click and hold a note
2. Drag to new location
3. Drop on a folder or between notes
4. Hierarchy updates

### Renaming Notes

1. Right-click the note
2. Select **Rename**
3. Edit the title
4. Press Enter or click Save

### Nesting Notes

Create hierarchy by:
- Creating child notes
- Dragging notes onto folders
- Dropping notes onto other notes

### Expanding/Collapsing

- Click the arrow next to folders
- Collapse to hide children
- Expand to show nested items
- State remembered across sessions

---

## Managing Tabs

### Opening Tabs

- Click any note in the tree
- Each note opens in its own tab
- Tabs remain open until closed

### Switching Tabs

- Click a tab to make it active
- Active tab shows in the editor
- Tab highlight shows current selection

### Closing Tabs

| Action | How |
|--------|-----|
| Close current | Click X on tab |
| Close all | Right-click → Close All |
| Close others | Right-click → Close Others |

### Tab Persistence

- Open tabs are saved to session
- Restored when you return
- Active tab remembered

---

## Folders

### Creating Folders

1. Click the folder icon with **+**
2. Or right-click → **New Folder**
3. Enter folder name
4. Click **Create**

### Folder Behavior

- Folders contain notes and other folders
- Click to expand/collapse
- Cannot be directly edited (just containers)
- Delete removes all contents

### Folder Icons

- Closed folder: Collapsed state
- Open folder: Expanded state
- Folder colors: Coming soon

---

## Searching Notes

### Quick Search

1. Use the search bar in the notes header
2. Type your search query
3. Results filter in real-time
4. Click to open matching note

### Search Scope

Currently searches:
- Document titles and content
- Within the current scope (application, project, or personal)

### Full-Text Search

Powered by Meilisearch:
- Fast indexed search across all content
- Highlighted matches in results
- Ranked results by relevance
- Search within the current application scope

---

## Deleting Notes

### Delete a Note

1. Right-click the note
2. Select **Delete**
3. Confirm the deletion

**Warning**: Deleting a note also deletes all child notes.

### Delete a Folder

1. Right-click the folder
2. Select **Delete**
3. Confirm the deletion

All contents are permanently removed.

### Trash and Restore

Deleted documents are moved to trash (soft delete):
- View trashed documents via the trash view
- **Restore**: Right-click a trashed document and select **Restore**
- **Permanent Delete**: Remove a trashed document permanently
- Soft-deleted documents are excluded from search results

---

## Scope Selector

### Switching Scopes

The Knowledge Base supports multiple scopes. Use the tab bar to switch:

- **Personal**: Your private notes
- **Application tabs**: Click an application to view its shared knowledge base
- **Project scope**: Access project-specific documentation from the project view

### Navigation

- Click tabs to switch between scopes
- Each scope maintains its own tree of folders and documents
- Search is scoped to the currently active tab

---

## Collaborative Features

### Document Locking

Documents use exclusive locking for edit coordination:
- Only one user can edit a document at a time
- Other users see a "locked by [user]" indicator
- Lock is released when the editor saves or discards changes
- Locks can be force-released by document owners if needed

### Presence Indicators

- See who's viewing the same note
- Avatar icons show active users

### Permissions

Documents inherit permissions from their application:
- **Owner**: Full control (edit, delete, manage access)
- **Editor**: Can create and edit documents
- **Viewer**: Read-only access

### Version History (Coming Soon)

- Snapshots saved automatically
- View previous versions
- Restore old versions
- Compare changes

---

## Best Practices

### Organization

1. **Use folders logically**: Group by topic, team, or project
2. **Shallow hierarchy**: Avoid too many nesting levels
3. **Clear naming**: Descriptive titles for easy finding
4. **Consistent structure**: Apply patterns across notes

### Content

1. **One topic per note**: Keep notes focused
2. **Use headings**: Create scannable structure
3. **Link related notes**: Cross-reference between documents
4. **Keep updated**: Archive outdated information

### Collaboration

1. **Respect document locks**: Wait for others to finish editing before acquiring the lock
2. **Review regularly**: Keep content current
3. **Assign owners**: Someone responsible for each area
4. **Use tags**: Organize documents with custom tags for easy discovery

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

### Tabs

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + W` | Close current tab (coming soon) |
| `Cmd/Ctrl + Tab` | Next tab (coming soon) |

---

## Troubleshooting

### Note Not Saving

**Check**:
- Network connection active
- Not in read-only mode
- Editor has focus

**Try**:
- Copy content manually
- Refresh the page
- Check for error messages

### Tree Not Loading

**Check**:
- Application selected
- You have access to the application

**Try**:
- Refresh the page
- Select a different application
- Check for JavaScript errors

### Can't Create Notes

**Check**:
- You have Editor or Owner role
- Application is selected

**Try**:
- Verify your permissions
- Contact application owner

### Tabs Not Persisting

**Check**:
- LocalStorage enabled
- Not in private/incognito mode

**Try**:
- Clear browser cache
- Check browser settings

---

## Related Topics

- [Applications](./applications.md) - Notes are organized by application
- [Members & Permissions](./members-permissions.md) - Access control for notes
- [Tips & Keyboard Shortcuts](./tips-shortcuts.md) - Productivity features
