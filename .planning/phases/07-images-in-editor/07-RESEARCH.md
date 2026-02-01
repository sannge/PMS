# Phase 7: Images in Editor - Research

**Researched:** 2026-01-31
**Domain:** TipTap image handling (paste/drop/upload/resize) + MinIO object storage
**Confidence:** HIGH

## Summary

This phase adds image support to the TipTap-based document editor: users can paste, drag-drop, or upload images which are stored in MinIO and referenced by URL. Images must be resizable via drag handles and show skeleton/placeholder animations while loading.

The project already has significant infrastructure in place. The backend MinIO service (`minio_service.py`) handles uploads/downloads/presigned URLs with a dedicated `pm-images` bucket. The file upload router (`routers/files.py`) handles multipart upload with entity association. The frontend already has `@tiptap/extension-image` v2.27.2 installed. The key new work is: (1) a dedicated document-image upload endpoint, (2) integrating file-handler events into TipTap, and (3) building a custom resizable image NodeView since TipTap v2 lacks built-in resize.

**Primary recommendation:** Use `@tiptap/extension-file-handler` (free, MIT) for paste/drop events. Build a custom `ResizableImage` extension extending `@tiptap/extension-image` with a React NodeView for resize handles. Reuse the existing `MinIOService` and `pm-images` bucket via a new lightweight document-image upload endpoint.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@tiptap/extension-image` | ^2.27.2 | Base image node rendering | Already installed; official TipTap extension |
| `@tiptap/extension-file-handler` | ^3.x (MIT) | Handle paste/drop file events | Official TipTap extension, open-sourced June 2025 under MIT |
| `minio` (Python) | >=7.2.0 | Object storage for images | Already installed; existing MinIOService with pm-images bucket |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@tiptap/react` | ^2.6.0 | ReactNodeViewRenderer for custom NodeView | Already installed; needed for resizable image component |
| `python-multipart` | >=0.0.17 | FastAPI file upload parsing | Already installed; needed for image upload endpoint |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom resize NodeView | `tiptap-extension-resize-image` (npm) | Third-party with 41K weekly downloads, but adds dependency for ~100 lines of code; custom gives full control over styling and behavior |
| `@tiptap/extension-file-handler` | Custom ProseMirror `handlePaste`/`handleDrop` via `editorProps` | FileHandler is now MIT, battle-tested, and avoids the duplicate-image-on-paste pitfall |
| Server-side upload | Presigned URL direct upload | Server-side is simpler for this use case since images are typically <10MB; presigned URLs add complexity for minimal gain in an Electron app |

**Installation:**
```bash
cd electron-app
npm install @tiptap/extension-file-handler
```

No new backend packages needed -- `minio` and `python-multipart` are already installed.

## Architecture Patterns

### Recommended Project Structure
```
electron-app/src/renderer/
├── components/knowledge/
│   ├── editor/
│   │   ├── extensions/
│   │   │   └── resizable-image.ts       # Custom Image extension with resize
│   │   ├── node-views/
│   │   │   └── resizable-image-view.tsx  # React NodeView component
│   │   └── image-upload.ts              # Upload helper (calls API, returns URL)
│   └── ...existing editor components...

fastapi-backend/app/
├── routers/
│   └── document_images.py               # Dedicated image upload endpoint
├── services/
│   └── minio_service.py                 # Already exists -- reuse
```

### Pattern 1: Custom Resizable Image Extension
**What:** Extend `@tiptap/extension-image` to add `width`/`height` attributes and a React NodeView with resize handles.
**When to use:** TipTap v2 (v3 has built-in resize; v2 does not).
**Example:**
```typescript
// Source: TipTap docs (React node views) + community patterns
import Image from '@tiptap/extension-image'
import { ReactNodeViewRenderer } from '@tiptap/react'
import { ResizableImageView } from './node-views/resizable-image-view'

export const ResizableImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      width: {
        default: null,
        renderHTML: (attributes) => {
          if (!attributes.width) return {}
          return { width: attributes.width }
        },
        parseHTML: (element) => element.getAttribute('width'),
      },
      height: {
        default: null,
        renderHTML: (attributes) => {
          if (!attributes.height) return {}
          return { height: attributes.height }
        },
        parseHTML: (element) => element.getAttribute('height'),
      },
    }
  },
  addNodeView() {
    return ReactNodeViewRenderer(ResizableImageView)
  },
})
```

### Pattern 2: FileHandler for Paste/Drop/Upload
**What:** Use `@tiptap/extension-file-handler` to intercept paste and drop events, upload to server, then insert image node with URL.
**When to use:** For all three image insertion methods (paste, drag-drop, toolbar button).
**Example:**
```typescript
// Source: TipTap FileHandler docs
import { FileHandler } from '@tiptap/extension-file-handler'

FileHandler.configure({
  allowedMimeTypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
  onPaste: (editor, files, htmlContent) => {
    // If HTML content has images (paste from web), let default handle it
    if (htmlContent) return false
    files.forEach(file => {
      uploadImageToServer(file).then(url => {
        editor.chain().focus().setImage({ src: url }).run()
      })
    })
  },
  onDrop: (editor, files, pos) => {
    files.forEach(file => {
      uploadImageToServer(file).then(url => {
        editor.chain().focus().setImage({ src: url }).run()
      })
    })
  },
})
```

### Pattern 3: Placeholder While Uploading
**What:** Insert a placeholder node (or a temporary data-URL) while the image uploads, then swap to the real URL on completion.
**When to use:** Every image insertion to show loading state.
**Example:**
```typescript
// Insert placeholder with loading state
const insertImageWithPlaceholder = async (editor: Editor, file: File, pos?: number) => {
  // Create a temporary object URL for instant preview
  const tempUrl = URL.createObjectURL(file)
  const insertPos = pos ?? editor.state.selection.anchor

  // Insert with a data attribute marking it as loading
  editor.chain()
    .focus()
    .insertContentAt(insertPos, {
      type: 'image',
      attrs: { src: tempUrl, alt: file.name, 'data-loading': 'true' }
    })
    .run()

  try {
    const permanentUrl = await uploadImageToServer(file)
    // Find and replace the temp image
    // Use a transaction to swap src and remove loading state
    // ...
  } finally {
    URL.revokeObjectURL(tempUrl)
  }
}
```

### Pattern 4: Server-Side Upload via Existing Infrastructure
**What:** Create a lightweight `/documents/images/upload` endpoint that reuses `MinIOService` and the existing `pm-images` bucket.
**When to use:** For all document image uploads.
**Example:**
```python
# Source: Existing patterns in routers/files.py
@router.post("/images/upload")
async def upload_document_image(
    file: UploadFile = File(...),
    document_id: UUID = Query(...),
    current_user: User = Depends(get_current_user),
    minio: MinIOService = Depends(get_minio_service),
) -> dict:
    # Validate image type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Only image files are allowed")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit for images
        raise HTTPException(413, "Image too large")

    object_name = minio.generate_object_name("document", str(document_id), file.filename)
    minio.upload_bytes("pm-images", object_name, content, file.content_type)
    url = minio.get_presigned_download_url("pm-images", object_name)

    return {"url": url, "object_name": object_name}
```

### Anti-Patterns to Avoid
- **Base64 in document JSON:** Never store base64-encoded images in the TipTap JSON content. This bloats the document, breaks search indexing, and makes the content_json column enormous. Always upload to MinIO and reference by URL.
- **Presigned upload URLs for Electron app:** Presigned PUT URLs are useful for browser-to-S3 uploads to bypass backend bandwidth, but in an Electron app the backend and frontend are on the same network. Server-side upload is simpler and allows validation.
- **Resizing via CSS only (no attribute persistence):** If you only apply width/height via CSS styles without updating node attributes, the size is lost on reload. Always persist dimensions as node attributes via `updateAttributes`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Paste/drop file interception | Custom ProseMirror plugin with handlePaste/handleDrop | `@tiptap/extension-file-handler` | Handles edge cases (duplicate image on paste from web, MIME type filtering, position tracking on drop) |
| Image MIME type detection | Extension-based checking | `file.type` (browser API) + server-side `content_type` validation | Browser provides reliable MIME types for file inputs; double-check on server |
| MinIO upload/bucket management | New storage service | Existing `MinIOService` singleton | Already handles bucket creation, object naming, presigned URLs |
| Object URL cleanup | Manual tracking | `URL.createObjectURL` / `URL.revokeObjectURL` in a try/finally | Browser API handles cleanup; just ensure revokeObjectURL is called |

**Key insight:** The project already has 90% of the backend infrastructure (MinIOService, pm-images bucket, file upload patterns, presigned URL generation). The new work is primarily frontend: wiring TipTap events to the upload API and building the resize NodeView.

## Common Pitfalls

### Pitfall 1: Duplicate Images on Paste from Web
**What goes wrong:** When a user copies an image from a webpage and pastes it, the clipboard contains both an HTML `<img>` tag and the raw image data. TipTap processes the HTML (inserting one image), and the FileHandler also processes the file data (inserting a second).
**Why it happens:** The paste event has multiple clipboard items: `text/html` and `image/*`.
**How to avoid:** In the `onPaste` handler, check if `htmlContent` is provided. If it contains an `<img>` tag, return `false` to let TipTap's default HTML paste handling take care of it.
**Warning signs:** Two copies of the same image appearing after paste.

### Pitfall 2: Presigned URL Expiration
**What goes wrong:** Images stored in MinIO with presigned URLs stop loading after the URL expires (default 1 hour).
**Why it happens:** The document JSON stores the presigned URL as `src`, which becomes stale.
**How to avoid:** Two approaches: (A) Store the MinIO object path (not the presigned URL) in the document JSON, and resolve to a fresh presigned URL on document load. (B) Configure the MinIO bucket with a public read policy for the pm-images bucket. Option B is simpler for an internal app.
**Warning signs:** Images that worked yesterday show broken icons today.

### Pitfall 3: Resize Handle Z-Index and Selection Conflicts
**What goes wrong:** Resize handles overlap with editor selection UI or don't respond to mouse events because of CSS stacking.
**Why it happens:** The TipTap editor, ProseMirror decorations, and custom NodeView all have competing z-index layers.
**How to avoid:** Use a dedicated CSS class for the resize container with explicit `position: relative` and handle z-index. Set `draggable: false` on the NodeView wrapper during resize to prevent ProseMirror's drag behavior from interfering.
**Warning signs:** Cannot grab resize handles; handles appear behind other elements.

### Pitfall 4: Large Image Upload Blocking the UI
**What goes wrong:** Uploading a 10MB image blocks the editor while the upload completes.
**Why it happens:** Synchronous upload flow -- insert image only after upload finishes.
**How to avoid:** Insert a placeholder immediately (using `URL.createObjectURL` for instant preview), upload in the background, then swap the src to the permanent URL.
**Warning signs:** Editor freezes for several seconds after pasting a large image.

### Pitfall 5: Width/Height Attribute Loss on Content Conversion
**What goes wrong:** Custom `width`/`height` attributes on the image node are lost when converting to Markdown or plain text.
**Why it happens:** The three-format content storage (JSON + Markdown + plain text) only preserves attributes that the conversion logic knows about.
**How to avoid:** Ensure the Markdown conversion for images includes width/height (e.g., `![alt](src =WIDTHxHEIGHT)` or just `![alt](src)` accepting dimension loss in Markdown). The JSON format will always preserve attributes.
**Warning signs:** Images revert to original size after save/reload.

## Code Examples

### Complete ResizableImageView React Component
```tsx
// Source: TipTap React NodeView docs + community patterns
import { NodeViewWrapper } from '@tiptap/react'
import type { NodeViewProps } from '@tiptap/react'
import { useCallback, useRef, useState } from 'react'

export function ResizableImageView({ node, updateAttributes, selected }: NodeViewProps) {
  const imgRef = useRef<HTMLImageElement>(null)
  const [isResizing, setIsResizing] = useState(false)

  const { src, alt, title, width, height } = node.attrs

  const handleResizeStart = useCallback((e: React.MouseEvent, corner: string) => {
    e.preventDefault()
    e.stopPropagation()
    setIsResizing(true)

    const startX = e.clientX
    const startY = e.clientY
    const startWidth = imgRef.current?.offsetWidth ?? 200
    const startHeight = imgRef.current?.offsetHeight ?? 200
    const aspectRatio = startWidth / startHeight

    const onMouseMove = (moveEvent: MouseEvent) => {
      const dx = moveEvent.clientX - startX
      let newWidth = Math.max(50, startWidth + dx)
      let newHeight = Math.round(newWidth / aspectRatio)
      if (imgRef.current) {
        imgRef.current.style.width = `${newWidth}px`
        imgRef.current.style.height = `${newHeight}px`
      }
    }

    const onMouseUp = () => {
      setIsResizing(false)
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
      if (imgRef.current) {
        updateAttributes({
          width: imgRef.current.offsetWidth,
          height: imgRef.current.offsetHeight,
        })
      }
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [updateAttributes])

  const isLoading = node.attrs['data-loading'] === 'true'

  return (
    <NodeViewWrapper className="relative inline-block" data-drag-handle>
      {isLoading && (
        <div className="absolute inset-0 bg-muted animate-pulse rounded" />
      )}
      <img
        ref={imgRef}
        src={src}
        alt={alt}
        title={title}
        width={width}
        height={height}
        className={`max-w-full ${selected ? 'ring-2 ring-primary' : ''}`}
        draggable={false}
      />
      {selected && !isLoading && (
        <>
          {['nw', 'ne', 'sw', 'se'].map(corner => (
            <div
              key={corner}
              className={`absolute w-3 h-3 bg-primary rounded-full cursor-${
                corner === 'nw' || corner === 'se' ? 'nwse' : 'nesw'
              }-resize ${
                corner.includes('n') ? 'top-0' : 'bottom-0'
              } ${
                corner.includes('w') ? 'left-0' : 'right-0'
              } -translate-x-1/2 -translate-y-1/2`}
              onMouseDown={(e) => handleResizeStart(e, corner)}
            />
          ))}
        </>
      )}
    </NodeViewWrapper>
  )
}
```

### Image Upload Helper
```typescript
// Source: Project patterns from existing API calls
const API_BASE = 'http://localhost:8001'

export async function uploadDocumentImage(
  file: File,
  documentId: string,
  authToken: string,
): Promise<{ url: string; objectName: string }> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(
    `${API_BASE}/documents/images/upload?document_id=${documentId}`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${authToken}` },
      body: formData,
    },
  )

  if (!response.ok) {
    throw new Error(`Image upload failed: ${response.status}`)
  }

  return response.json()
}
```

### Backend Document Image Upload Endpoint
```python
# Source: Existing patterns in routers/files.py + minio_service.py
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from uuid import UUID
from ..services.minio_service import MinIOService, get_minio_service
from ..services.auth_service import get_current_user
from ..models.user import User

router = APIRouter(prefix="/documents", tags=["document-images"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

@router.post("/images/upload")
async def upload_document_image(
    file: UploadFile = File(...),
    document_id: UUID = Query(..., description="Document this image belongs to"),
    current_user: User = Depends(get_current_user),
    minio: MinIOService = Depends(get_minio_service),
) -> dict:
    if not file.content_type or file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only image files are allowed")

    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image exceeds 10MB limit")

    object_name = minio.generate_object_name("document", str(document_id), file.filename or "image.png")
    minio.upload_bytes(MinIOService.IMAGES_BUCKET, object_name, content, file.content_type)
    download_url = minio.get_presigned_download_url(MinIOService.IMAGES_BUCKET, object_name)

    return {
        "url": download_url,
        "object_name": object_name,
        "file_name": file.filename,
        "file_size": len(content),
        "content_type": file.content_type,
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@tiptap-pro/extension-file-handler` (paid) | `@tiptap/extension-file-handler` (free MIT) | June 2025 | No Pro subscription needed |
| Custom ProseMirror handlePaste/handleDrop | FileHandler extension | 2024-2025 | Simpler, fewer edge cases |
| TipTap v3 `Image.configure({ resize })` | Custom NodeView in v2 | v3.10.0 (2025) | v2 projects must build custom resize |
| Base64 inline images | MinIO URL references | Industry standard | Smaller documents, cacheable images |

**Deprecated/outdated:**
- `@tiptap-pro/extension-file-handler`: Replaced by `@tiptap/extension-file-handler` (MIT). The `@tiptap-pro/*` namespace is being phased out for these extensions.
- ProseMirror `handleDOMEvents.paste` workaround: The FileHandler extension handles the duplicate-paste issue properly now.

## Open Questions

1. **Presigned URL expiration strategy**
   - What we know: Presigned URLs expire (default 1h). Document JSON stores the image src.
   - What's unclear: Whether to store permanent MinIO paths and resolve on load, or set bucket to public read.
   - Recommendation: For Phase 7, store the MinIO object path (`document/{id}/{uuid}_{filename}`) as a `data-minio-key` attribute alongside the `src`. On document load, batch-resolve all image URLs via a single API call. This keeps images secure without public bucket access. Alternatively, for simplicity, generate presigned URLs with a very long expiry (7 days) and refresh them on document open.

2. **Image cleanup on document deletion**
   - What we know: Documents can be soft-deleted and permanently deleted.
   - What's unclear: Whether to clean up MinIO objects when a document is permanently deleted, or use a lifecycle policy.
   - Recommendation: Defer cleanup to a background job. For Phase 7, images persist in MinIO even after document deletion. Add cleanup as a future enhancement.

3. **Toolbar "upload image" button UX**
   - What we know: Requirements mention upload button in addition to paste/drop.
   - What's unclear: Whether this should be a file picker dialog or an inline popover.
   - Recommendation: Simple file picker via `<input type="file" accept="image/*">` triggered by a toolbar button. Standard UX pattern.

## Sources

### Primary (HIGH confidence)
- TipTap Image extension docs: https://tiptap.dev/docs/editor/extensions/nodes/image - configuration, commands, attributes
- TipTap FileHandler extension docs: https://tiptap.dev/docs/editor/extensions/functionality/filehandler - onPaste, onDrop, allowedMimeTypes
- TipTap ResizableNodeView docs: https://tiptap.dev/docs/editor/api/resizable-nodeviews - resize API, callbacks, directions
- TipTap React NodeView docs: https://tiptap.dev/docs/editor/extensions/custom-extensions/node-views/react - ReactNodeViewRenderer, updateAttributes
- Existing codebase: `fastapi-backend/app/services/minio_service.py` - full MinIO integration
- Existing codebase: `fastapi-backend/app/routers/files.py` - file upload patterns
- Existing codebase: `electron-app/package.json` - installed TipTap v2.6-2.27.2 extensions

### Secondary (MEDIUM confidence)
- TipTap open-sourcing announcement (June 2025): https://tiptap.dev/blog/release-notes/were-open-sourcing-more-of-tiptap - FileHandler moved to MIT
- Community patterns for custom image resize: https://www.bigbinary.com/blog/building-custom-extensions-in-tiptap
- Codemzy blog on paste/drop: https://www.codemzy.com/blog/tiptap-drag-drop-image, https://www.codemzy.com/blog/tiptap-pasting-images

### Tertiary (LOW confidence)
- `tiptap-extension-resize-image` npm package (41K downloads): https://www.npmjs.com/package/tiptap-extension-resize-image - alternative to custom, but custom preferred for control
- Image resize config added in TipTap v3.10.0 (from search results, not verified in changelog)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official TipTap extensions verified in docs; MinIO service verified in codebase
- Architecture: HIGH - Patterns verified from TipTap docs and existing codebase patterns
- Pitfalls: MEDIUM - Duplicate-paste and URL-expiration pitfalls verified; resize z-index from community reports

**Research date:** 2026-01-31
**Valid until:** 2026-03-01 (stable; TipTap v2 is mature, MinIO SDK is stable)
