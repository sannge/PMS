# Notes & Knowledge Base

PM Desktop includes a powerful note-taking system for documentation, wikis, and team knowledge sharing. Notes are organized hierarchically within applications.

---

## Overview

The Knowledge Base provides:
- Hierarchical note organization (folders and documents)
- Rich text editing with TipTap
- Multi-tab interface for multiple notes
- Application-level organization
- Real-time collaborative editing (coming soon)
- Full-text search (coming soon)

---

## Accessing Notes

### From Sidebar

1. Click **Notes** in the left sidebar
2. Notes page opens with the tree view and editor

### Application Context

Notes are organized by application:
- Each application has its own knowledge base
- Use the Application Selector to switch between applications
- Press `Cmd/Ctrl + K` for quick application search

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

### Auto-Save

Changes save automatically:
- Saves as you type (debounced)
- No save button needed
- Last saved indicator shown

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
- Note titles
- Content within current application

### Full-Text Search (Coming Soon)

Powered by Meilisearch:
- Fast indexed search
- Search across all content
- Highlighted matches
- Ranked results

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

### Undo Delete

- Currently not supported
- Consider exporting important notes
- Future: Trash/recovery feature

---

## Application Selector

### Switching Applications

The Knowledge Base is application-specific. To switch:

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

## Collaborative Features

### Real-Time Editing (Coming Soon)

Multiple users editing simultaneously:
- See each other's cursors
- Changes merge automatically
- No conflicts or lost work
- Powered by Yjs CRDT

### Presence Indicators

- See who's viewing the same note
- Avatar icons show active users
- Cursor labels with names

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
3. **Link related notes**: Cross-reference (coming soon)
4. **Keep updated**: Archive outdated information

### Collaboration

1. **Communicate edits**: Let others know you're editing
2. **Review regularly**: Keep content current
3. **Assign owners**: Someone responsible for each area
4. **Use comments**: Discuss changes (coming soon)

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
