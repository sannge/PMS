# Members & Permissions

PM Desktop uses role-based access control (RBAC) to manage who can view, edit, and administer applications, projects, and tasks.

---

## Overview

### Permission Hierarchy

```
Application (Owner, Manager, Member, Viewer)
    └── Project (inherited from application + project-specific roles)
            └── Task (inherited from project)
```

Permissions flow downward:
- Application membership grants access to all projects within that application
- Project access grants access to all tasks within
- Specific permissions determine what actions are allowed
- The AI assistant (Blair) respects these permissions -- it can only perform actions allowed by your role

---

## Member Roles

PM Desktop uses four roles at both the application and project level:

### Owner

The highest permission level, typically for application creators and administrators.

| Capability | Allowed |
|------------|---------|
| View content | Yes |
| Create/edit projects | Yes |
| Create/edit tasks | Yes |
| Delete projects | Yes |
| Delete application | Yes |
| Manage all members | Yes |
| Change any role | Yes |
| Override project status | Yes |

**Who should be Owner**:
- Application creators (automatic)
- Department heads
- Product managers
- Trusted administrators

### Manager

Can manage projects, members, and content, but cannot delete the application itself.

| Capability | Allowed |
|------------|---------|
| View content | Yes |
| Create/edit projects | Yes |
| Create/edit tasks | Yes |
| Delete projects | Yes |
| Delete application | No |
| Manage members (except Owners) | Yes |
| Invite members | Yes |
| Override project status | Yes |

**Who should be Manager**:
- Team leads
- Scrum masters
- Senior team members who need to manage others

### Member

Standard working member with full content creation capabilities.

| Capability | Allowed |
|------------|---------|
| View content | Yes |
| Create/edit projects | Yes |
| Create/edit tasks | Yes |
| Delete own content | Yes |
| Delete application | No |
| Invite members | Limited |
| Change roles | No |
| Override project status | No |

**Who should be Member**:
- Active team members
- Developers
- Designers
- Anyone who creates content

### Viewer

Read-only access for stakeholders who need visibility without editing.

| Capability | Allowed |
|------------|---------|
| View content | Yes |
| Add comments | Yes |
| Create/edit content | No |
| Delete content | No |
| Manage members | No |

**Who should be Viewer**:
- Stakeholders
- Executives needing visibility
- External consultants
- Team members from other departments

---

## RBAC Hierarchy

Application-level membership automatically grants access to projects within the application. This means:

- If you are a **Member** of an application, you can access all projects in that application
- You do not need to be separately added to each project
- Project-level roles can further refine permissions within a specific project
- The AI assistant checks your role before performing any write actions on your behalf

---

## Viewing Members

### Application Members

1. Open the application
2. Click the member avatars in the header
3. Or click the **Members** button

The member panel shows:
- **Avatar**: Profile picture
- **Name**: Display name
- **Email**: For identification
- **Role**: Current permission level (Owner, Manager, Member, or Viewer)

### Member Avatar Group

The compact avatar display shows:
- Up to 5 member avatars
- "+N" badge for additional members
- Hover for member names
- Click to open full list

---

## Inviting Members

### Sending Invitations

1. Open the application
2. Click **Invite Members** or the **+** button in member list
3. Fill in the invitation form:

| Field | Description |
|-------|-------------|
| Email | Recipient's email address |
| Role | Owner, Manager, Member, or Viewer |
| Message | Optional personal message |

4. Click **Send Invitation**

### Invitation Status

Invitations can be:
- **Pending**: Sent, awaiting response
- **Accepted**: User joined the application
- **Declined**: User rejected the invitation
- **Expired**: Invitation timed out

### Multiple Invitations

You can invite multiple people:
- Enter comma-separated emails
- Or send one at a time
- Each receives individual invitation

### Invitation Restrictions

- Members cannot invite Owners or Managers
- Viewers cannot invite anyone
- Email must be valid format
- Cannot invite existing members

---

## Responding to Invitations

### Receiving Invitations

When invited, you receive:
- In-app notification (bell icon shows count)
- Email notification (if enabled)

### Accepting an Invitation

1. Click the notification bell
2. Find the invitation notification
3. Click to open invitation details
4. Click **Accept**

You now have access to the application with the assigned role.

### Declining an Invitation

1. Open the invitation details
2. Click **Decline**
3. Optionally provide a reason

The inviter is notified of your response.

---

## Managing Member Roles

### Changing Roles

Owners and Managers (with restrictions) can change member roles:

1. Open the member list
2. Find the member to update
3. Click their current role
4. Select the new role
5. Confirm the change

### Role Change Restrictions

| Your Role | Can Change To |
|-----------|---------------|
| Owner | Any role |
| Manager | Member or Viewer (not Owner) |
| Member | Cannot change roles |
| Viewer | Cannot change roles |

### Promoting to Owner

Only Owners can promote others to Owner:
1. Find the member
2. Click role dropdown
3. Select **Owner**
4. Confirm transfer of power (if applicable)

### Demoting from Owner

- Application must have at least one Owner
- Cannot demote yourself if sole Owner
- Transfer ownership first

---

## Removing Members

### How to Remove

1. Open the member list
2. Find the member to remove
3. Click the **Remove** button (X or trash icon)
4. Confirm removal

### Removal Rules

- Owners can remove anyone except themselves (if sole owner)
- Managers can remove Members and Viewers
- Members and Viewers cannot remove anyone
- Removed members lose access immediately

### Self-Removal

- Click your own entry in member list
- Confirm leaving the application
- You cannot rejoin without new invitation

---

## Permission Effects

### What Viewers Can Do

- Browse applications, projects, tasks
- View all content and attachments
- Read comments and knowledge base documents
- Add their own comments
- Receive notifications
- Search content
- Ask Blair read-only questions about accessible content

### What Viewers Cannot Do

- Create or edit tasks
- Create or edit projects
- Create or edit knowledge base documents
- Delete any content
- Invite members
- Change settings

### What Members Can Do

Everything viewers can, plus:
- Create and edit tasks
- Create and edit projects
- Create and edit knowledge base documents
- Delete their own content
- Manage checklists
- Upload attachments
- Use Blair to create/update tasks and documents (with confirmation)

### What Members Cannot Do

- Delete the application
- Promote to Owner or Manager
- Remove Owners or Managers

---

## Project-Level Permissions

### Project Members

Projects can have specific member assignments:
- Indicates who's working on the project
- Helps with task filtering
- Required for some assignments

### Project Lead

A designated project leader:
- Displayed on project card
- Can override project status
- Primary contact for project

### Task Assignment

- Only members can be assigned to tasks
- Viewers can be assigned (for visibility)
- Assignment doesn't change role

---

## AI Assistant and Permissions

The AI assistant (Blair) respects the RBAC system:

- Blair checks your permissions before performing any write operation
- If you are a Viewer, Blair cannot create or edit content on your behalf
- Write operations (create task, update project, etc.) require confirmation from you before Blair executes them
- Blair can read and search any content you have access to based on your role

---

## Best Practices

### Initial Setup

1. Start with minimal access (Viewer)
2. Promote to Member as needed
3. Use Manager for team leads
4. Reserve Owner for trusted administrators
5. Document who needs what access

### Ongoing Management

1. Review members monthly
2. Remove departed team members
3. Audit role appropriateness
4. Keep Owner count low (2-3 max)

### Security

1. Use work emails only
2. Remove access when projects complete
3. Don't share Owner credentials
4. Report unauthorized access

### Onboarding New Members

1. Send invitation with appropriate role
2. Include welcome message
3. Point to relevant projects
4. Assign initial tasks (for Members)

---

## Troubleshooting

### Can't See Application

**Causes**:
- Not yet invited
- Invitation pending
- Removed from application

**Solutions**:
- Check notification bell for invitations
- Contact application owner

### Can't Edit Content

**Causes**:
- Viewer role only
- Not a member
- Specific item restrictions

**Solutions**:
- Request role upgrade from Owner
- Confirm membership
- Check specific permissions

### Can't Invite Members

**Causes**:
- Viewer or Member role
- Member trying to invite Owner
- Technical issue

**Solutions**:
- Request higher role
- Ask Owner or Manager to send invitation
- Contact support

### Can't Remove Member

**Causes**:
- Insufficient permission
- Trying to remove Owner
- Sole Owner removal

**Solutions**:
- Ask Owner to remove
- Transfer ownership first
- Must have at least one Owner

---

## Related Topics

- [Applications](./applications.md) - Application-level access
- [Projects](./projects.md) - Project-specific assignments
- [Notifications](./notifications.md) - Invitation notifications
