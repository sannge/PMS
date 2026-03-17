# Comments & Collaboration

PM Desktop enables rich collaboration through task comments, threaded replies, @mentions, checklists, and real-time presence features.

---

## Task Comments

Comments allow team members to discuss work, share updates, and make decisions directly on tasks.

### Viewing Comments

1. Open any task by clicking its card
2. Click the **Comments** tab in the detail panel
3. Comments appear in chronological order (oldest first)

### Comment Display

Each comment shows:
- **Author avatar**: Commenter's profile picture
- **Author name**: Who posted the comment
- **Timestamp**: When posted (relative time, e.g., "2 hours ago")
- **Content**: The formatted message
- **Attachments**: Any files attached to the comment
- **Reply count**: Number of threaded replies (if any)

---

## Adding Comments

### Writing a Comment

1. Open a task
2. Scroll to the comment input at the bottom
3. Type your message
4. Click **Send** or press `Ctrl/Cmd + Enter`

### Adding Comments with the AI Assistant

You can ask Blair to add a comment to a task. For example, "Add a comment to SP1-15 saying 'Deployment completed successfully.'" Blair will confirm before posting.

### Rich Text Formatting

Comments support formatting:

| Format | How to Apply |
|--------|--------------|
| **Bold** | `Ctrl/Cmd + B` or wrap with `**text**` |
| *Italic* | `Ctrl/Cmd + I` or wrap with `*text*` |
| Code | Wrap with backticks `` `code` `` |
| Link | Paste URL or use link button |
| Lists | Start line with `-` or `1.` |

### Adding Attachments

1. Click the **Attach** button (paperclip icon)
2. Select file(s) from your computer
3. Or drag and drop files into the comment area
4. Files upload and attach to your comment

See [File Attachments](./files-attachments.md) for more details.

---

## @Mentions

Tag team members to notify them and draw their attention to a comment.

### How to Mention

1. Type `@` followed by the person's name
2. A dropdown appears with matching members
3. Click a name or use arrow keys and Enter to select
4. The mention appears highlighted in the comment

Mentions are stored as structured data, so they remain linked to the correct user even if display names change.

### Mention Dropdown

The dropdown shows:
- **Avatar**: Profile picture
- **Display name**: User's name
- **Email**: For identification

### Mention Notifications

When you mention someone:
- They receive an in-app notification
- The notification links to the specific comment
- Email notification may be sent (based on settings)

### Best Practices for Mentions

- Mention people who need to take action
- Don't over-mention (notification fatigue)
- Use for questions, assignments, or important updates
- Combine with clear asks: "@John Can you review this?"

---

## Threaded Replies

Comments support threaded replies, allowing focused discussions on specific topics within a task.

### Replying to a Comment

1. Find the comment you want to reply to
2. Click the **Reply** button
3. Type your reply
4. Click **Send** or press `Ctrl/Cmd + Enter`

### Viewing Threads

- Replies appear nested under the parent comment
- Thread count is shown on the parent comment
- Click to expand or collapse a thread

### When to Use Threads

- Responding to a specific question or point
- Following up on a particular topic without cluttering the main comment stream
- Having a back-and-forth discussion about a specific aspect of the task

---

## Editing Comments

### Edit Your Comments

1. Hover over your comment
2. Click the **Edit** button (pencil icon)
3. Modify the text
4. Click **Save** or press `Ctrl/Cmd + Enter`

### Edit Permissions

- You can only edit your own comments
- Edits are saved immediately

---

## Deleting Comments

### Delete Your Comments

1. Hover over your comment
2. Click the **Delete** button (trash icon)
3. Confirm deletion

### Delete Permissions

- You can delete your own comments
- Admins/Owners can delete any comment
- Deleted comments are permanently removed

---

## Checklists

Checklists help track sub-tasks, requirements, or steps within a task.

### Viewing Checklists

1. Open a task
2. Click the **Checklists** tab
3. View all checklists and their items

### Checklist Display

Each checklist shows:
- **Title**: Checklist name (e.g., "Testing Steps")
- **Progress bar**: Visual completion status
- **Progress text**: "3/5 items complete"
- **Items**: Individual checklist items with ordered positioning

---

## Creating Checklists

### Add a Checklist

1. Open the task detail panel
2. Click the **Checklists** tab
3. Click **Add Checklist**
4. Enter a checklist title (e.g., "Acceptance Criteria")
5. Press Enter or click Create

You can also ask the AI assistant to create checklists: "Add a checklist called 'Testing Steps' to task SP1-15."

### Multiple Checklists

Tasks can have multiple checklists for different purposes:

- **Acceptance Criteria**: Definition of done
- **Testing Steps**: QA verification
- **Deployment Tasks**: Release activities
- **Review Points**: Code review checklist

---

## Managing Checklist Items

### Adding Items

1. Click **Add Item** in the checklist
2. Type the item text
3. Press Enter to add
4. Continue adding more items

You can also ask Blair to add items: "Add item 'Verify login flow' to the Testing Steps checklist on SP1-15."

### Completing Items

- Click the checkbox to mark complete
- Click again to unmark
- Progress bar updates automatically

Blair can toggle items too: "Mark the first item in 'Testing Steps' as complete on SP1-15."

### Editing Items

1. Click the item text
2. Edit inline
3. Click outside to save

### Deleting Items

1. Hover over the item
2. Click the **X** button
3. Item is removed immediately

### Reordering Items

1. Click and hold the drag handle (grip icon)
2. Drag to new position
3. Release to drop

---

## Checklist Best Practices

### Writing Good Items

- Be specific and actionable
- One action per item
- Use verbs: "Test login flow", "Update documentation"

### Organizing Checklists

- Group related items in the same checklist
- Use separate checklists for different concerns
- Keep checklists focused (5-15 items ideal)

### Progress Tracking

- Review checklist progress in standups
- Close task when all checklists complete
- Use for definition of done

---

## Real-Time Presence

PM Desktop shows who's currently viewing and working on the same content.

### Presence Indicators

Look for avatar icons showing active users:
- **Project board**: See who's viewing the project
- **Task detail**: See who's looking at the same task
- **Notes**: See real-time collaborators with cursor positions

### What Presence Shows

- **Avatar**: User's profile picture
- **Name** (on hover): User's display name
- **Status**: Online/viewing indicator

### Privacy

- Presence only shows for members with access
- You see others, they see you
- No detailed activity tracking

---

## Real-Time Updates

### Automatic Sync

All changes sync instantly via WebSocket:
- Comments and replies appear immediately for all viewers
- Checklist updates reflect in real-time
- Status changes show without refresh
- Presence indicators update automatically

### Conflict Handling

When multiple users edit simultaneously:
- Last write wins for simple fields
- No data loss for distinct changes
- Refresh if you notice inconsistencies

### Connection Status

A small indicator shows your connection:
- **Green**: Connected, real-time active
- **Yellow**: Reconnecting
- **Red**: Offline (changes queue for sync)

---

## Collaboration Workflows

### Code Review Pattern

1. Developer moves task to "In Review"
2. @mentions reviewer: "@Jane Ready for review"
3. Reviewer adds checklist: "Review Points"
4. Reviewer checks items as reviewed
5. Reviewer comments feedback or approval
6. Developer addresses feedback
7. Reviewer completes checklist and approves

### Bug Triage Pattern

1. Bug created with description
2. Add checklist: "Investigation"
3. Work through investigation items
4. Comment findings
5. @mention assignee with solution
6. Track fix with new checklist
7. Complete and move to Done

### Sprint Planning Pattern

1. Create task for feature
2. Add "Requirements" checklist
3. Break down into items
4. Assign team member
5. Team discusses in comments
6. Track progress via checklist

---

## Best Practices

### Comments

- Keep comments focused and relevant
- Use formatting for readability
- @mention sparingly but appropriately
- Use threaded replies to keep discussions organized
- Update progress regularly

### Checklists

- Create before starting work
- Keep items small and achievable
- Update as you complete work
- Don't leave stale incomplete items

### Collaboration

- Acknowledge mentions promptly
- Check notifications regularly
- Communicate blockers early
- Celebrate completions in comments

---

## Troubleshooting

### Comment Not Posting

- Check network connection
- Look for error messages
- Try refreshing the page
- Avoid very large file attachments

### @Mention Not Working

- Ensure exact name match
- User must be a member of the project's application
- Wait for dropdown to appear
- Use arrow keys to select

### Checklist Not Saving

- Check for error messages
- Ensure you have edit permissions
- Refresh and retry

---

## Related Topics

- [Tasks & Kanban Board](./tasks.md) - Task management context
- [File Attachments](./files-attachments.md) - Attaching files to comments
- [Notifications](./notifications.md) - Getting notified about mentions
