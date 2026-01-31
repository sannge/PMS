# Tasks & Kanban Board

Tasks are the individual work items in PM Desktop. They are managed on a visual Kanban board with drag-and-drop functionality.

---

## Overview

Tasks represent:
- Features to build
- Bugs to fix
- Documentation to write
- Any actionable work item

Each task contains:
- Title and description
- Status (column on Kanban board)
- Priority level
- Task type
- Assignees
- Checklists
- Comments
- File attachments

---

## The Kanban Board

### Understanding Columns

The Kanban board organizes tasks into status columns:

| Column | Purpose |
|--------|---------|
| **To Do** | Tasks ready to start but not yet in progress |
| **In Progress** | Currently being worked on |
| **In Review** | Completed work awaiting review |
| **Done** | Finished and approved tasks |

### Board Navigation

- **Scroll horizontally**: Use mouse scroll or trackpad
- **Collapse columns**: Click the column header arrow
- **Column counts**: See task count in each column header

---

## Creating Tasks

### Quick Create

1. Find the desired status column (e.g., "To Do")
2. Click the **+** button at the top of the column
3. Type the task title
4. Press **Enter** to create

The task appears immediately on the board.

### Detailed Create

1. Click **+ Add Task** or the **+** button
2. Fill in the full task form:

| Field | Required | Description |
|-------|----------|-------------|
| Title | Yes | Clear, action-oriented name |
| Description | No | Detailed requirements and context |
| Assignees | No | Who will work on this task |
| Priority | No | Low, Medium, High, or Critical |
| Type | No | Bug, Feature, Task, Epic, Story |
| Due Date | No | Deadline for completion |
| Estimated Hours | No | Expected time to complete |
| Parent Task | No | Link to parent for subtasks |

3. Click **Create**

### Task Title Best Practices

- Start with an action verb: "Add", "Fix", "Update", "Create"
- Be specific: "Fix login timeout on mobile" vs "Fix bug"
- Keep under 80 characters for readability

---

## Viewing Task Details

Click any task card to open the detail panel on the right side.

### Header Section

- **Task title**: Click to edit inline
- **Task key**: Auto-generated identifier (e.g., "SP1-15")
- **Status badge**: Current status with color
- **Close button**: Return to board view

### Description Section

- Rich text editor for detailed information
- Supports formatting: bold, italic, headings, lists
- Code blocks for technical content
- Links are automatically clickable

### Properties Panel

Quick access to task properties:

| Property | Description |
|----------|-------------|
| Status | Current workflow state |
| Assignees | Team members responsible |
| Priority | Urgency level |
| Type | Category of work |
| Due Date | Target completion date |
| Estimated Hours | Time budget |

### Tabs

- **Comments**: Discussion and updates
- **Checklists**: Sub-task tracking
- **Attachments**: Related files
- **Activity**: History log (coming soon)

---

## Moving Tasks (Status Changes)

### Drag and Drop

1. Click and hold a task card
2. Drag to the target column
3. Release to drop

The task's status updates instantly, and all team members see the change in real-time.

### Dropdown Change

1. Open the task detail panel
2. Click the **Status** dropdown
3. Select the new status
4. Status updates immediately

### Keyboard Shortcut

When a task is selected:
- **Arrow keys**: Navigate between tasks
- **Enter**: Open task details
- **Escape**: Close detail panel

---

## Editing Tasks

### Inline Title Edit

1. Click the task title in the detail panel
2. Edit the text
3. Click outside or press Enter to save

### Property Edits

1. Open the task detail panel
2. Click any property field
3. Select or enter new value
4. Changes save automatically

### Description Edit

1. Click the description area
2. Use the rich text editor
3. Changes save as you type (with debounce)

---

## Task Properties

### Status

Available statuses (may vary by configuration):

| Status | Color | Meaning |
|--------|-------|---------|
| To Do | Gray | Not started |
| In Progress | Blue | Currently working |
| In Review | Yellow | Awaiting review |
| Done | Green | Completed |
| Blocked | Red | Cannot proceed |

### Priority

| Priority | Icon | Use When |
|----------|------|----------|
| Low | Down arrow | Nice to have, no urgency |
| Medium | Dash | Normal priority |
| High | Up arrow | Important, needs attention soon |
| Critical | Double up arrow | Urgent, blocking others |

### Type

| Type | Description |
|------|-------------|
| Task | General work item |
| Bug | Defect or issue to fix |
| Feature | New functionality |
| Story | User story or requirement |
| Epic | Large initiative containing multiple tasks |

### Assignees

- **Multiple assignees**: Tasks can have several owners
- **Avatar display**: Assignees show as avatars on cards
- **Search**: Find team members by name
- **Unassign**: Click X to remove someone

### Due Date

- Click the date picker to set deadline
- Overdue tasks highlight in red
- Due soon (within 3 days) shows warning color

### Estimated Hours

- Enter expected hours to complete
- Helps with planning and capacity
- Track against actual time (coming soon)

---

## Deleting Tasks

1. Open the task detail panel
2. Click the **Delete** button (trash icon)
3. Confirm deletion in the dialog

**Warning**: Deleted tasks cannot be recovered. All comments, checklists, and attachments are also removed.

---

## Task Hierarchy

### Parent/Child Relationships

Tasks can be organized hierarchically:

- **Parent task**: High-level work item (like an Epic)
- **Subtasks**: Smaller pieces of the parent

### Creating Subtasks

1. Open a task to make it the parent
2. Click **Add Subtask** button
3. Create the subtask with its own properties

### Viewing Subtasks

- Parent tasks show subtask count on the card
- Open parent to see list of subtasks
- Each subtask links back to parent

### Subtask Rules

- Subtasks can have their own status independent of parent
- Completing all subtasks doesn't auto-complete parent
- Subtasks appear in their own board columns

---

## Task Cards on the Board

### Card Information

Each task card shows:

- **Title**: First line, truncated if long
- **Key**: Task identifier (e.g., "SP1-15")
- **Priority icon**: Colored arrow indicator
- **Type icon**: Bug, feature, etc.
- **Assignee avatars**: Who's working on it
- **Checklist progress**: X/Y items done
- **Comment count**: Number of comments
- **Due date**: If set, with color coding

### Card Colors

Cards may be colored based on:
- Priority (borders or accents)
- Overdue status (red highlight)
- Type (subtle background)

---

## Searching and Filtering Tasks

### Quick Search

Type in the board search bar to filter by:
- Task title
- Task key
- Description content

### Filters

Use the filter panel to show/hide tasks:

| Filter | Options |
|--------|---------|
| Status | Select specific columns |
| Priority | Low, Medium, High, Critical |
| Type | Bug, Feature, Task, etc. |
| Assignee | Specific team members |
| Due Date | Date range or overdue |

### Clearing Filters

Click **Clear Filters** to show all tasks again.

---

## Real-Time Updates

### Live Collaboration

- See task movements as teammates work
- Watch comments appear instantly
- Status changes sync immediately

### Presence Indicators

- Active viewers show as avatars
- See who's looking at the same task
- Real-time cursor positions (notes only)

### Conflict Prevention

- Last write wins for simple fields
- Notifications for conflicting edits
- Automatic merge for compatible changes

---

## Best Practices

### Writing Good Tasks

1. **Clear titles**: Start with action verbs
2. **Detailed descriptions**: Include acceptance criteria
3. **Right-sized**: 1-3 days of work ideally
4. **Single responsibility**: One outcome per task

### Managing Your Board

1. **Limit WIP**: Don't overload "In Progress"
2. **Regular grooming**: Move done tasks off board
3. **Use priorities**: Help team focus on what matters
4. **Update daily**: Keep status current

### Team Coordination

1. **Assign clearly**: Every active task needs an owner
2. **Comment updates**: Note progress and blockers
3. **Use checklists**: Break down complex tasks
4. **Review regularly**: Don't let tasks get stale

---

## Troubleshooting

### Task Won't Move

- Check you have edit permissions
- Verify the target status is valid
- Refresh the page if board seems stuck

### Changes Not Saving

- Check your network connection
- Look for error messages
- Avoid rapid consecutive edits

### Can't Find a Task

- Check all status columns
- Clear any active filters
- Search by task key directly
- Task may have been deleted

---

## Related Topics

- [Comments & Collaboration](./comments-collaboration.md) - Task discussions
- [Projects](./projects.md) - Container for tasks
- [Members & Permissions](./members-permissions.md) - Access control
