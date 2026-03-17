# File Attachments

PM Desktop supports file uploads and attachments on comments and documents, allowing teams to share screenshots, documents, diagrams, and other files.

---

## Overview

Files can be attached to:
- Task comments
- Note documents (images via editor toolbar)
- Knowledge base folders

Supported features:
- Drag and drop upload
- Click to browse upload
- Multiple file selection
- Image previews
- File previews (PDF, Word, Excel)
- Draw.io diagram support
- Batch document import
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
| Diagrams | VSDX (Visio), Draw.io/diagrams.net files |
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

## File Previews

PM Desktop provides inline previews for several file types, so you can view content without downloading.

### Image Previews

Images show as thumbnails in comments:
- Auto-generated preview
- Click to expand to full size
- Supports zoom and pan
- Maintains aspect ratio

### PDF Previews

- First page rendered as a preview
- Click to view the full document
- Download button available

### Word and Excel Previews

- Document content rendered inline when possible
- Click to download for full editing

### Draw.io Diagrams

- Diagram preview rendered as an image
- Click to open in the diagram editor (see [Canvas Diagrams](#canvas-diagrams) below)

---

## Canvas Diagrams

PM Desktop integrates with Draw.io for creating and editing diagrams directly within the application.

### Creating a Diagram

1. In the knowledge base, create a new document or open an existing one
2. Use the diagram/canvas tool to insert a Draw.io diagram
3. The Draw.io editor opens within PM Desktop
4. Create your diagram using the full Draw.io toolset (shapes, connectors, text, etc.)
5. Save to store the diagram within your document

### Editing a Diagram

1. Click on an existing diagram in a document
2. The Draw.io editor opens
3. Make your changes
4. Save to update

### Diagram Previews

- Diagrams are stored with a PNG preview for quick viewing
- The preview updates when you save changes
- Other users see the preview without opening the editor

### Use Cases for Diagrams

- Architecture and system design
- Flowcharts and process diagrams
- Wireframes and mockups
- Org charts and relationship maps
- Network topology diagrams

---

## Batch Document Import

You can import multiple documents into the knowledge base at once. This is useful for migrating existing documentation into PM Desktop.

### Supported Import Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| PDF | .pdf | Text extracted and indexed for search |
| Word | .docx | Content converted and indexed |
| PowerPoint | .pptx | Slide content extracted |
| Excel | .xlsx | Spreadsheet content extracted |
| Visio | .vsdx | Diagram content imported |

### How to Import

1. Navigate to a folder in the knowledge base
2. Click the **Import** button
3. Select one or more files from your computer
4. Files are processed and created as documents in the current folder
5. Content is extracted, indexed for search, and made available for AI retrieval

### After Import

- Imported documents appear in the folder tree
- Content is searchable via full-text search
- Documents are available for the AI assistant to reference
- You can edit imported content using the rich text editor

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

Note: Download links are temporary (expire after 1 hour) and are regenerated on demand for security.

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
- Consider importing into the knowledge base for searchability

### Large Files

- Compress files when possible
- Use links for very large files
- Consider breaking into smaller parts

---

## Storage and Limits

### File Storage

Files are stored in MinIO object storage (S3-compatible):
- Images (PNG, JPEG, GIF, WebP) are stored in a dedicated `pm-images` bucket
- All other files (PDF, DOCX, ZIP, etc.) are stored in a `pm-attachments` bucket
- Files are organized by entity: `{entity_type}/{entity_id}/{unique_id}_{filename}`
- Download links are temporary (expire after 1 hour) and regenerated on demand
- Draw.io diagram previews are stored as PNG images alongside document attachments

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
- Link may have expired -- navigate back and click download again

---

## Related Topics

- [Comments & Collaboration](./comments-collaboration.md) - Using files in discussions
- [Tasks & Kanban Board](./tasks.md) - Context for attachments
- [Notes & Knowledge Base](./notes-knowledge-base.md) - Document images, diagrams, and imports
