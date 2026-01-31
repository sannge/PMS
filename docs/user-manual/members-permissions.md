# Members & Permissions

PM Desktop uses role-based access control to manage who can view, edit, and administer applications, projects, and tasks.

---

## Overview

### Permission Hierarchy

```
Organization (future)
    └── Application (Owner, Editor, Viewer)
            └── Project (inherited + project-specific)
                    └── Task (inherited)
```

Permissions flow downward:
- Application access grants access to all projects within
- Project access grants access to all tasks within
- Specific permissions determine what actions are allowed

---

## Member Roles

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

### Editor

Standard working member with full content creation capabilities.

| Capability | Allowed |
|------------|---------|
| View content | Yes |
| Create/edit projects | Yes |
| Create/edit tasks | Yes |
| Delete own content | Yes |
| Delete application | No |
| Invite viewers | Yes |
| Change roles | Limited |
| Override project status | Yes |

**Who should be Editor**:
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

## Viewing Members

### Application Members

1. Open the application
2. Click the member avatars in the header
3. Or click the **Members** button

The member panel shows:
- **Avatar**: Profile picture
- **Name**: Display name
- **Email**: For identification
- **Role**: Current permission level

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
| Role | Owner, Editor, or Viewer |
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

- Editors cannot invite Owners
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

Owners and Editors (with restrictions) can change member roles:

1. Open the member list
2. Find the member to update
3. Click their current role
4. Select the new role
5. Confirm the change

### Role Change Restrictions

| Your Role | Can Change To |
|-----------|---------------|
| Owner | Any role |
| Editor | Viewer only (not Owner) |
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
- Editors can remove Viewers
- Viewers cannot remove anyone
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
- Read comments
- Add their own comments
- Receive notifications
- Search content

### What Viewers Cannot Do

- Create or edit tasks
- Create or edit projects
- Delete any content
- Invite members
- Change settings

### What Editors Can Do

Everything viewers can, plus:
- Create and edit tasks
- Create and edit projects
- Delete their own content
- Invite new viewers
- Manage checklists
- Upload attachments

### What Editors Cannot Do

- Delete the application
- Promote to Owner
- Remove Owners

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

## Auditing Access

### Viewing Access History

Coming soon:
- See when members were added
- Track role changes
- View invitation history

### Current Access Check

1. Open application members
2. Review current list
3. Remove unnecessary access
4. Verify roles are appropriate

---

## Best Practices

### Initial Setup

1. Start with minimal access (Viewer)
2. Promote to Editor as needed
3. Reserve Owner for trusted administrators
4. Document who needs what access

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
4. Assign initial tasks (for editors)

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
- Viewer role
- Editor trying to invite Owner
- Technical issue

**Solutions**:
- Request higher role
- Ask Owner to send invitation
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
