# File Attachments

PM Desktop supports file uploads and attachments on comments, allowing teams to share screenshots, documents, and other files.

---

## Overview

Files can be attached to:
- Task comments
- Note documents (images via editor toolbar)

Supported features:
- Drag and drop upload
- Click to browse upload
- Multiple file selection
- Image previews
- Download links
- File deletion

---

## Uploading Files

### Drag and Drop

1. Open a task and navigate to comments
2. Find a file on your computer
3. Drag it into the comment input area
4. Release to start upload
5. File uploads with progress indicator
6. Attach to your comment

### Click to Browse

1. Click the **Attach** button (paperclip icon) in the comment area
2. File browser opens
3. Select one or more files
4. Click **Open**
5. Files upload and attach

### Multiple Files

- Select multiple files using Ctrl/Cmd + Click
- Or Shift + Click for ranges
- All selected files upload simultaneously
- Each shows its own progress

---

## File Types

### Supported Types

PM Desktop accepts most common file types:

| Category | Examples |
|----------|----------|
| Images | PNG, JPG, GIF, SVG, WebP |
| Documents | PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX |
| Text | TXT, MD, CSV, JSON, XML |
| Archives | ZIP, RAR, 7Z, TAR, GZ |
| Code | JS, PY, TS, CSS, HTML |

### Size Limits

- **Maximum per file**: 100 MB
- **Recommended**: Keep files under 25 MB for best performance

### Restricted Types

Some file types may be blocked for security:
- Executable files (.exe, .bat, .sh)
- System files
- Check with your administrator for specific restrictions

---

## Viewing Attachments

### In Comments

Attachments appear below the comment text:

**Images**:
- Thumbnail preview displayed inline
- Click to view full size
- Supports zoom and pan

**Documents**:
- File icon with filename
- File size shown
- Click to download

### Attachment List

For tasks with many attachments:
- View all files in a consolidated list
- Sort by name, date, or size
- Quick actions available

---

## Image Previews

### Inline Thumbnails

Images show as thumbnails in comments:
- Auto-generated preview
- Click to expand
- Maintains aspect ratio

### Full-Size View

Click any image to open the preview modal:
- Full resolution display
- Zoom controls
- Navigation between multiple images
- Download button
- Close with Escape or X

### Supported Previews

| Format | Preview Support |
|--------|----------------|
| PNG | Full preview |
| JPG/JPEG | Full preview |
| GIF | Animated preview |
| WebP | Full preview |
| SVG | Full preview |
| PDF | First page preview |

---

## Downloading Files

### Single File

1. Hover over the attachment
2. Click the **Download** button (down arrow icon)
3. File downloads to your default location

### Direct Link

1. Right-click the attachment
2. Select "Copy link" or "Open in new tab"
3. Direct download URL is available

### Batch Download

For multiple files (coming soon):
- Select multiple attachments
- Click "Download All"
- Receives as ZIP archive

---

## Managing Attachments

### Viewing Details

Hover over an attachment to see:
- Original filename
- File size
- Upload date
- Uploader name

### Deleting Attachments

1. Hover over the attachment
2. Click the **Delete** button (X or trash icon)
3. Confirm deletion

**Permissions**:
- You can delete your own uploads
- Comment authors can delete attachments on their comments
- Admins can delete any attachment

**Warning**: Deleted files cannot be recovered.

---

## Upload Progress

### Progress Indicator

While uploading, you'll see:
- Progress bar with percentage
- File name being uploaded
- Cancel button (X)

### Multiple File Progress

Each file shows individual progress:
- Parallel uploads when possible
- Overall progress indicator
- Completion notifications

### Upload Errors

If an upload fails:
- Error message displayed
- Retry button available
- Check file size and type
- Verify network connection

---

## Best Practices

### File Organization

- Use descriptive filenames
- Include context in comment with attachment
- Group related files in single comment

### Image Attachments

- Crop screenshots to relevant area
- Use PNG for diagrams, JPG for photos
- Annotate images before upload if helpful

### Document Sharing

- Use PDF for finalized documents
- Include version in filename
- Reference specific sections in comments

### Large Files

- Compress files when possible
- Use links for very large files
- Consider breaking into smaller parts

---

## Storage and Limits

### File Storage

Files are stored securely:
- Encrypted at rest
- Backed up regularly
- Available as long as task exists

### Quotas

Your organization may have limits:
- Per-application storage limits
- Per-user upload limits
- Contact administrator for details

### Retention

Files remain available until:
- Explicitly deleted
- Parent task deleted
- Parent project deleted
- Organization policies apply

---

## Security

### Access Control

Files inherit task permissions:
- Only members with task access can view
- Download links require authentication
- Links expire for security

### Virus Scanning

Uploaded files may be scanned:
- Malware detection
- Suspicious file flagging
- Blocked file types

### Privacy

- Files not indexed by search engines
- No public access
- Encrypted connections

---

## Troubleshooting

### Upload Fails

**Check**:
- File size under 100 MB
- Supported file type
- Network connection stable
- Available storage quota

**Try**:
- Reduce file size
- Convert to supported format
- Upload smaller batches

### Preview Not Showing

**Check**:
- Supported preview format
- File uploaded completely
- File not corrupted

**Try**:
- Refresh the page
- Download and view locally

### Can't Delete File

**Check**:
- You have delete permission
- You own the comment or file
- Contact admin if needed

### Download Not Working

**Check**:
- Network connection
- Browser popup blocker
- Try right-click "Save as"

---

## Related Topics

- [Comments & Collaboration](./comments-collaboration.md) - Using files in discussions
- [Tasks & Kanban Board](./tasks.md) - Context for attachments
- [Notes & Knowledge Base](./notes-knowledge-base.md) - Document images and attachments
