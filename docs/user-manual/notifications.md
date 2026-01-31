# Notifications

PM Desktop keeps you informed about important activities through in-app notifications and optional email alerts.

---

## Overview

Notifications alert you when:
- Someone @mentions you in a comment
- You're assigned to a task
- Task status changes on your assignments
- You receive an invitation
- Members join or leave
- Project updates occur

---

## Notification Bell

### Location

The notification bell icon is in the top-right corner of the title bar, next to your profile.

### Unread Count

A red badge shows the number of unread notifications:
- Shows up to 99
- 99+ for large counts
- No badge when all read

### Opening Notifications

Click the bell icon to open the notification dropdown:
- Recent notifications listed
- Unread items highlighted
- Quick actions available

---

## Notification Types

### @Mentions

When someone mentions you in a comment:

**Shows**:
- Who mentioned you
- The task/context
- Preview of the message

**Actions**:
- Click to open the task
- View the full comment
- Mark as read

### Task Assignments

When you're assigned to a task:

**Shows**:
- Who assigned you
- Task title
- Project context

**Actions**:
- Click to view task
- Accept or decline (coming soon)

### Status Changes

When a task you're involved with changes status:

**Shows**:
- Task title
- Old → New status
- Who made the change

**Actions**:
- Click to view updated task

### Invitations

When invited to an application:

**Shows**:
- Who invited you
- Application name
- Your assigned role

**Actions**:
- Accept invitation
- Decline invitation
- View application details

### Member Updates

When members are added or removed:

**Shows**:
- Who was added/removed
- Application affected
- Role assigned (if added)

### Project Updates

When projects are created, updated, or status changes:

**Shows**:
- Project name
- Type of change
- Who made it

---

## Managing Notifications

### Viewing All Notifications

1. Click the notification bell
2. Scroll through the list
3. Click "View All" for full page (if available)

### Marking as Read

**Single notification**:
1. Hover over the notification
2. Click the checkmark or "Mark Read"

**All notifications**:
1. Click "Mark All as Read" in the dropdown
2. All notifications marked read
3. Badge count resets

### Dismissing Notifications

1. Hover over the notification
2. Click the X or "Dismiss"
3. Notification removed from list

### Deleting Notifications

Some notifications can be permanently deleted:
1. Open notification options
2. Click "Delete"
3. Confirm deletion

---

## Notification Panel

### Panel Features

The notification dropdown includes:
- **Header**: "Notifications" title
- **Filter tabs**: All, Unread, Mentions (coming soon)
- **Notification list**: Recent notifications
- **Actions**: Mark all read, settings link

### Notification Cards

Each notification card shows:
- **Icon**: Type indicator (mention, task, etc.)
- **Title**: Brief description of event
- **Context**: Related item (task, project)
- **Time**: When it occurred
- **Actions**: Mark read, dismiss

### Empty State

When no notifications:
- "No new notifications" message
- All caught up indicator

---

## Notification Preferences

### In-App Settings (Coming Soon)

Control which notifications you receive:

| Type | Default | Configurable |
|------|---------|--------------|
| @Mentions | On | Yes |
| Task assignments | On | Yes |
| Status changes | On | Yes |
| Invitations | On | Always on |
| Project updates | On | Yes |

### Email Notifications (Coming Soon)

Configure email alerts:
- Immediate: Instant email for each notification
- Daily digest: Summary once per day
- Off: In-app only

### Quiet Hours (Coming Soon)

Set times when notifications are silenced:
- Define time range
- Choose days of week
- Notifications queue for later

---

## Desktop Notifications

### Browser/System Notifications

PM Desktop can show system notifications:
- Pop-up alerts outside the app
- Quick preview without switching windows
- Click to jump to relevant item

### Enabling Desktop Notifications

1. The app requests permission on first login
2. Click "Allow" when prompted
3. System notifications now active

### Disabling Desktop Notifications

**In your browser/OS**:
1. Go to system notification settings
2. Find PM Desktop
3. Toggle off notifications

---

## Real-Time Delivery

### How Notifications Arrive

- WebSocket connection pushes notifications instantly
- No need to refresh
- Works across all open tabs

### Notification Sound (Coming Soon)

- Audible alert for new notifications
- Configurable per notification type
- Can be muted entirely

### Connection Status

If disconnected:
- Notifications queue on server
- Delivered when connection restores
- No notifications lost

---

## Notification Best Practices

### Staying on Top of Work

1. Check notifications regularly
2. Act on mentions promptly
3. Clear read notifications periodically
4. Use filters to focus on important items

### Reducing Noise

1. Unwatch projects you're not active on
2. Configure email preferences
3. Use quiet hours during focus time
4. Mute non-essential notification types

### Team Etiquette

1. Use @mentions purposefully
2. Don't over-notify teammates
3. Be specific in notifications (clear titles)
4. Acknowledge mentions in reasonable time

---

## Troubleshooting

### Not Receiving Notifications

**Check**:
- You're logged in
- WebSocket connection active (green indicator)
- Notification permissions enabled
- Not on quiet hours

**Try**:
- Refresh the page
- Log out and back in
- Check browser notification settings

### Too Many Notifications

**Solutions**:
- Configure notification preferences
- Unwatch irrelevant projects
- Use digest mode for email
- Mute low-priority types

### Desktop Notifications Not Showing

**Check**:
- Browser permission granted
- System notifications enabled
- Focus assist/DND mode off
- PM Desktop allowed in notification settings

**Try**:
- Re-grant notification permission
- Check browser-specific settings
- Restart the application

### Notifications Not Marking as Read

**Check**:
- Click action completed
- Network connection stable

**Try**:
- Manually click "Mark as Read"
- Refresh the page
- Check for error messages

---

## Related Topics

- [Comments & Collaboration](./comments-collaboration.md) - @Mentions trigger notifications
- [Members & Permissions](./members-permissions.md) - Invitation notifications
- [Tasks & Kanban Board](./tasks.md) - Task assignment notifications
