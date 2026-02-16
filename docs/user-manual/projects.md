# Projects

Projects are containers for related tasks within an application. They represent sprints, features, releases, or any logical grouping of work items.

---

## Overview

```
Project
    ├── Tasks (unlimited)
    ├── Kanban Board (status-based columns)
    ├── Members (project-specific assignments)
    └── Status (aggregated from tasks)
```

Each project:

- Belongs to exactly one application
- Contains multiple tasks organized on a Kanban board
- Has a unique key for quick reference (e.g., "SPRINT-1")
- Tracks progress through task status aggregation

---

## Viewing Projects

### From an Application

1. Navigate to an application
2. View all projects within in grid or board view
3. Click any project to open it

### Direct Projects List

1. Click **Projects** in the sidebar
2. View projects across all your applications
3. Use search to find specific projects

### Project Card Information

Each project card displays:

- **Name**: Project display name
- **Key**: Unique identifier (e.g., "SP1")
- **Status**: Overall project status (derived or overridden)
- **Progress**: Visual indicator of task completion
- **Lead**: Assigned project lead (if set)

---

## Creating a Project

1. Open the parent application
2. Click **New Project** or the **+** button
3. Fill in the project form:

| Field | Required | Description |
|-------|----------|-------------|
| Name | Yes | Display name (e.g., "Sprint 1 - User Authentication") |
| Key | Yes | Short unique identifier (e.g., "SP1", "AUTH") |
| Description | No | Project scope and objectives |
| Lead | No | Primary responsible person |

4. Click **Create**

### Project Key Guidelines

- **Keep it short**: 2-6 characters work best
- **Make it memorable**: Use abbreviations that make sense
- **Unique within application**: Each project needs a distinct key
- **Alphanumeric**: Letters and numbers only (no special characters)

**Examples**:
- "SPRINT1" or "SP1" for Sprint 1
- "AUTH" for authentication feature
- "Q1REL" for Q1 release

---

## Project Detail View

Click a project to open its detail view, which includes:

### Header Section

- **Project name** and key
- **Status badge**: Current project status
- **Progress bar**: Visual completion percentage
- **Action buttons**: Edit, Delete, Members, Settings

### Kanban Board

The main workspace showing tasks organized by status columns:

- **To Do**: Tasks not yet started
- **In Progress**: Active work
- **In Review**: Awaiting review
- **Issue**: Tasks with blockers or problems
- **Done**: Completed tasks

Each project is created with these 5 default status columns.

### Side Panels

- **Task Detail**: Opens when clicking a task
- **Members Panel**: Project member management
- **Filters**: Task filtering options

---

## Editing a Project

1. Open the project
2. Click the **Edit** button in the header
3. Modify any editable fields:
   - Name
   - Key (if no tasks reference it yet)
   - Description
   - Lead assignment
4. Click **Save**

### What Can Be Changed

- Project name and description
- Project lead
- Project key (with restrictions)

### What Cannot Be Changed

- Parent application
- Project ID (system-generated)
- Creation date

---

## Deleting a Project

**Warning**: Deleting a project permanently removes all tasks, comments, checklists, and attachments within it.

1. Open the project
2. Click the **Delete** button
3. Read the confirmation warning
4. Confirm deletion

### Deletion Rules

- Requires Editor or Owner role
- All tasks are permanently deleted
- Consider archiving instead of deleting (coming soon)

---

## Project Status

### Status Derivation

Project status is automatically calculated from task statuses:

| Condition | Derived Status |
|-----------|---------------|
| All tasks in "Done" | Completed |
| Any task "In Progress" | In Progress |
| All tasks "To Do" | Not Started |
| Mixed statuses | In Progress |

### Status Override

Project leads and admins can manually override the derived status:

1. Click the **Status Override** icon in the project header
2. Select a new status from the dropdown
3. Optionally add a reason for the override
4. Click **Apply**

The override persists until:
- You clear the override
- An admin removes it

**When to Override**:
- Project blocked by external factors
- Status doesn't reflect actual progress
- Communicating special circumstances to team

### Clearing an Override

1. Click the Status Override icon
2. Click **Clear Override**
3. Project reverts to automatic status calculation

---

## Project Views

### Grid View

- Projects displayed as cards in a grid
- Best for browsing many projects
- Shows key information at a glance

### Kanban View

- Projects shown as columns on a board
- Useful for tracking project status
- Drag projects between statuses (if enabled)

Toggle between views using the view switcher in the toolbar.

---

## Project Search and Filters

### Quick Search

Type in the search bar to filter projects by:

- Project name
- Project key
- Description text

### Advanced Filters (Coming Soon)

- Filter by status
- Filter by lead
- Filter by date range
- Filter by member assignment

---

## Working with Tasks

From the project detail view, you can:

### Creating Tasks

1. Click the **+** button in any column
2. Or click **Add Task** at the bottom of a column
3. Enter the task title and press Enter

### Moving Tasks

- **Drag and drop** task cards between columns
- Status updates automatically when dropped
- Real-time sync keeps all viewers updated

### Opening Task Details

Click any task card to open the detail panel with:

- Full description editor
- Assignee selection
- Priority and type settings
- Checklists
- Comments
- File attachments

See [Tasks & Kanban Board](./tasks.md) for complete task management.

---

## Project Members

### Viewing Members

1. Click the **Members** button in the project header
2. View all members with their roles
3. See their avatar, name, and role

### Member Capabilities

| Role | Project Capabilities |
|------|---------------------|
| Owner | Full control, can delete project |
| Editor | Create/edit tasks, manage members |
| Viewer | View tasks, add comments |

### Assigning Members

1. Open the Members panel
2. Click **Add Member**
3. Search for the user
4. Select their role
5. Click **Add**

---

## Real-Time Collaboration

### Live Updates

The Kanban board updates in real-time:

- See tasks move as teammates work
- Watch new tasks appear instantly
- Status changes reflect immediately

### Presence Indicators

- **Active users**: Avatar icons show who's viewing
- **Editing indicators**: See who's working on what

### WebSocket Connection

A small indicator shows connection status:
- **Green dot**: Connected, real-time updates active
- **Yellow dot**: Reconnecting
- **Red dot**: Disconnected, working offline

---

## Best Practices

### Naming Projects

- Use consistent naming conventions
- Include context (e.g., "Sprint 1 - Jan 2024")
- Avoid generic names like "Project" or "Work"

### Project Keys

- Keep them memorable and short
- Use patterns across similar projects (SP1, SP2, SP3)
- Document key meanings in the description

### Task Organization

- Keep task counts manageable per column
- Archive completed projects regularly
- Use checklists for large tasks instead of many small ones

### Team Coordination

- Assign a project lead for accountability
- Use status overrides to communicate blocks
- Regular standups using the Kanban view

---

## Troubleshooting

### Can't Create Projects

- Verify you have Editor or Owner role in the application
- Check that the project key is unique
- Ensure all required fields are filled

### Can't See a Project

- You may not have access to the parent application
- The project may have been deleted
- Contact the application owner

### Status Not Updating

- Refresh the page if real-time sync appears stuck
- Check your network connection
- Verify the status override isn't blocking updates

---

## Related Topics

- [Applications](./applications.md) - Parent container for projects
- [Tasks & Kanban Board](./tasks.md) - Managing tasks within projects
- [Members & Permissions](./members-permissions.md) - Role-based access control
