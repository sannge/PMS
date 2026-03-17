# Applications

Applications are the top-level containers in PM Desktop. They represent major initiatives, products, departments, or any logical grouping of related projects.

---

## Overview

```
Application
    ├── Projects (unlimited)
    ├── Members (with roles)
    ├── Knowledge Base (documents, folders, diagrams)
    └── AI Assistant context
```

Each application:

- Contains multiple projects
- Has its own set of members with specific roles
- Maintains an independent knowledge base (notes, documents, and diagrams)
- Tracks aggregated statistics across all projects
- Provides context for the AI assistant (Blair can search and manage within application scope)

---

## Viewing Applications

### Applications List

1. Click **Applications** in the sidebar
2. View all applications you have access to

Each application card displays:

- **Name**: The application title
- **Description**: Brief summary (if provided)
- **Member count**: Number of team members
- **Project count**: Number of projects within

### Searching Applications

Use the search bar at the top of the Applications page to filter:

- Type any text to search by name or description
- Results filter in real-time as you type
- Clear the search to show all applications

---

## Creating an Application

1. Navigate to **Applications** in the sidebar
2. Click the **New** button (top-right corner)
3. Fill in the application form:

| Field | Required | Description |
|-------|----------|-------------|
| Name | Yes | Display name for the application (e.g., "Product Suite 2024") |
| Description | No | Brief description of the application's purpose |

4. Click **Create**

You automatically become the **Owner** of the new application.

### Naming Tips

- Use clear, descriptive names
- Consider including team or product names
- Avoid abbreviations that others might not understand

---

## Viewing Application Details

Click any application card to open its detail view. The detail page shows:

### Header Section

- **Application name** and description
- **Member avatars**: Quick view of team members
- **Action buttons**: Edit, Archive, Delete, Invite Members

### Projects Section

- Grid or Kanban view of all projects
- Project cards with:
  - Name and key
  - Status indicators
  - Assigned lead
  - Task counts

### Quick Actions

- **New Project**: Create a project in this application
- **Search projects**: Filter the project list
- **View mode toggle**: Switch between grid and board views

---

## Editing an Application

1. Open the application (click on it from the list)
2. Click the **Edit** button (pencil icon) in the header
3. Modify the name or description
4. Click **Save**

Or from the applications list:

1. Hover over the application card
2. Click the **Edit** icon
3. Make your changes
4. Click **Save**

### What Can Be Edited

- Application name
- Application description

### What Cannot Be Edited

- Application ID (system-generated)
- Creation date
- Owner (can be transferred via member management)

---

## Archiving and Restoring Applications

Instead of permanently deleting an application, you can archive it to hide it from active views while preserving all data.

### Archiving

1. Open the application or find it in the list
2. Click the **Archive** button
3. Confirm the action

Archived applications are hidden from the default applications list but can be restored at any time.

### Restoring

1. Navigate to the archived applications view (filter or toggle in the applications list)
2. Find the archived application
3. Click **Restore**

The application and all its projects, tasks, and documents become active again.

---

## Deleting an Application

**Warning**: Deleting an application permanently removes all contained projects, tasks, comments, files, and notes.

1. Open the application or find it in the list
2. Click the **Delete** button (trash icon)
3. Read the confirmation warning carefully
4. Type the application name to confirm (if required)
5. Click **Delete** to confirm

### Deletion Rules

- Only **Owners** can delete applications
- Deletion is immediate and irreversible
- All members lose access instantly
- Consider archiving instead of deleting to preserve data

---

## Application Statistics

On the application detail page, you can see aggregated statistics:

| Statistic | Description |
|-----------|-------------|
| Projects | Total number of projects |
| Tasks | Total tasks across all projects |
| Active | Tasks currently in progress |
| Completed | Tasks marked as done |
| Members | Number of team members |

These update in real-time as work progresses.

---

## Switching Between Applications

### From the List

Click any application card to open it.

### From Notes

Use the Application Selector (keyboard shortcut: `Cmd/Ctrl + K`):

1. Press `Cmd + K` (Mac) or `Ctrl + K` (Windows/Linux)
2. Type to search for an application
3. Click or press Enter to switch

### Breadcrumb Navigation

When viewing a project or task, use the breadcrumb trail at the top to navigate back to the application level.

---

## Application Members

Each application has its own member list with role-based permissions:

| Role | Capabilities |
|------|--------------|
| Owner | Full control, can delete application, manage all members |
| Manager | Can manage projects, members (except Owners), and all content |
| Member | Can create/edit projects and tasks, contribute to knowledge base |
| Viewer | Read-only access, can add comments |

Application membership grants access to all projects within the application. See [Members & Permissions](./members-permissions.md) for detailed member management.

### Quick Member View

Click the member avatars in the application header to see the full member list.

---

## Knowledge Base

Each application has its own knowledge base where your team can create and organize documents, diagrams, and imported files. Documents scoped to an application are visible to all application members.

See [Notes & Knowledge Base](./notes-knowledge-base.md) for details on creating and managing documents.

---

## AI Assistant

Application members can use the AI assistant (Blair) within the context of an application. Blair respects your role-based permissions -- it can only perform actions that your role allows.

See [AI Assistant (Blair)](./tips-shortcuts.md#ai-assistant-blair) for more details.

---

## Best Practices

### Organizing Applications

- **One application per product/team**: Keep related work together
- **Avoid overlapping scope**: Clear boundaries prevent confusion
- **Use descriptive names**: Help team members find the right application

### Member Management

- **Start with minimal access**: Add viewers first, promote as needed
- **Regular audits**: Review member lists periodically
- **Document ownership**: Ensure backup owners exist

### Project Structure

- **Consistent naming**: Use patterns like "Sprint 1", "Sprint 2"
- **Logical groupings**: Group by feature, team, or time period
- **Archive completed work**: Use the archive feature for finished projects instead of deleting

---

## Troubleshooting

### Can't See an Application

- You may not have been invited yet
- Check your pending invitations (notification bell)
- Contact the application owner for access

### Can't Edit an Application

- You need Member, Manager, or Owner role to make changes
- Contact an Owner to upgrade your permissions

### Can't Delete an Application

- Only Owners can delete applications
- Verify you have Owner role in the member list

---

## Related Topics

- [Projects](./projects.md) - Managing projects within applications
- [Members & Permissions](./members-permissions.md) - Team and role management
- [Notes & Knowledge Base](./notes-knowledge-base.md) - Application-level documentation
