# Phase 7: Images in Editor - Research

**Researched:** 2026-02-01
**Domain:** TipTap v2 Image Extension, MinIO Object Storage, ProseMirror paste/drop handlers
**Confidence:** HIGH

## Summary

Phase 7 adds image support (paste, upload, drag-and-drop, resize, placeholder animation) to the knowledge base editor. The research reveals that **nearly all required infrastructure already exists in the codebase**, making this phase primarily a wiring and adaptation task rather than new development.

The existing `RichTextEditor.tsx` (task description editor) already implements a complete image pipeline: custom `ResizableImage` extension extending `@tiptap/extension-image` with `ReactNodeViewRenderer`, `editorProps.handlePaste`/`handleDrop` for clipboard and drag-and-drop, upload to MinIO via `POST /api/files/upload`, and presigned URL retrieval. The knowledge base editor (`DocumentEditor`) needs to adopt these same patterns within its extension factory architecture.

The content converter (`content_converter.py`) currently does not handle `image` nodes -- it silently renders children of unknown nodes (graceful degradation), but image nodes have no children. This needs an explicit handler for proper Markdown (`![alt](url)`) and plain text (alt text or empty string) output.

**Primary recommendation:** Port the proven `ResizableImage` extension and upload flow from `RichTextEditor.tsx` into the knowledge editor's `createDocumentExtensions()` factory, adapting for the document-scoped context (document ID entity type, document-level auth). Add skeleton/placeholder loading animation as a CSS animation on a wrapper element while upload is in flight.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@tiptap/extension-image` | ^2.6.0 | Base Image node type for ProseMirror schema | Already installed in package.json; official TipTap extension |
| `@tiptap/react` (ReactNodeViewRenderer) | ^2.6.0 | React component rendering inside ProseMirror nodes | Already used project-wide; required for resize handles |
| MinIO (via `minio` Python package) | existing | Object storage for image blobs | Already configured with `pm-images` bucket |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lucide-react` (ImageIcon) | ^0.400.0 | Toolbar icon for image upload button | Already installed; used throughout toolbar |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom ResizableImage (extend Image) | `tiptap-extension-resize-image` npm package | Third-party dep adds maintenance risk; existing RichTextEditor already has a working custom implementation -- **use existing code** |
| `editorProps.handlePaste`/`handleDrop` | `@tiptap/extension-file-handler` | FileHandler is Pro-only for TipTap v2 (free only in v3); **not compatible with our v2 stay-put decision** |
| Custom placeholder component | `@tiptap/extension-placeholder` (for images) | Placeholder extension only handles empty-doc text; image upload placeholders need custom node or CSS approach |

### Installation
No new packages needed. `@tiptap/extension-image` is already in `package.json`.

## Architecture Patterns

### Recommended Project Structure
```
electron-app/src/renderer/components/knowledge/
├── editor-extensions.ts       # Add ResizableImage to createDocumentExtensions()
├── editor-toolbar.tsx         # Add image upload button section
├── document-editor.tsx        # Add editorProps for paste/drop, uploadImage callback
├── editor-types.ts            # Add onImageUpload to DocumentEditorProps
├── editor-styles.css          # Add image skeleton/placeholder CSS
├── ResizableImageView.tsx     # NEW: extracted React NodeView component
└── use-image-upload.ts        # NEW: hook encapsulating upload logic for documents

fastapi-backend/app/
├── services/content_converter.py  # Add image node handler
└── tests/test_content_converter.py # Add image conversion tests
```

### Pattern 1: ResizableImage Extension (Extend @tiptap/extension-image)
**What:** Extend the official Image extension to add a `width` attribute and a custom React NodeView with drag handles for resizing.
**When to use:** Always -- this is the v2 approach for image resizing since built-in `resize` config is v3-only.
**Example:**
```typescript
// Source: existing RichTextEditor.tsx lines 205-226
import Image from '@tiptap/extension-image'
import { ReactNodeViewRenderer } from '@tiptap/react'

const ResizableImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      width: {
        default: null,
        parseHTML: element => {
          const width = element.getAttribute('width') || element.style.width
          return width ? parseInt(String(width), 10) : null
        },
        renderHTML: attributes => {
          if (!attributes.width) return {}
          return { width: attributes.width, style: `width: ${attributes.width}px` }
        },
      },
    }
  },
  addNodeView() {
    return ReactNodeViewRenderer(ResizableImageView)
  },
})
```

### Pattern 2: Image Upload via editorProps (handlePaste + handleDrop)
**What:** Intercept paste and drop events via ProseMirror's `editorProps` to detect image files, upload them to MinIO, and insert the resulting URL.
**When to use:** Always -- the FileHandler extension is Pro-only on v2.
**Example:**
```typescript
// Source: existing RichTextEditor.tsx lines 1030-1078
editorProps: {
  handlePaste(view, event) {
    const items = Array.from(event.clipboardData?.items || [])
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        event.preventDefault()
        const file = item.getAsFile()
        if (!file) continue
        uploadImage(file).then((url) => {
          if (url) {
            const node = view.state.schema.nodes.image?.create({ src: url })
            if (node) {
              const tr = view.state.tr.replaceSelectionWith(node)
              view.dispatch(tr)
            }
          }
        })
        return true
      }
    }
    return false
  },
  handleDrop(view, event) {
    const files = Array.from(event.dataTransfer?.files || [])
    const imageFile = files.find(f => f.type.startsWith('image/'))
    if (imageFile) {
      event.preventDefault()
      uploadImage(imageFile).then((url) => {
        if (url) {
          const pos = view.posAtCoords({ left: event.clientX, top: event.clientY })
          const node = view.state.schema.nodes.image?.create({ src: url })
          if (node && pos) {
            const tr = view.state.tr.insert(pos.pos, node)
            view.dispatch(tr)
          }
        }
      })
      return true
    }
    return false
  },
}
```

### Pattern 3: Image Upload Flow (Frontend to MinIO via Backend)
**What:** Upload image file to `POST /api/files/upload`, receive attachment ID, fetch presigned download URL, use as image `src`.
**When to use:** For all image insertions (paste, drop, toolbar button).
**Example:**
```typescript
// Source: existing RichTextEditor.tsx lines 901-953
async function uploadImage(file: File): Promise<string | null> {
  if (file.size > 5 * 1024 * 1024) return null  // 5MB limit

  const formData = new FormData()
  formData.append('file', file)

  // Upload to MinIO via backend
  const uploadResponse = await fetch(`${apiUrl}/api/files/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })
  const attachment = await uploadResponse.json()

  // Get presigned download URL
  const downloadResponse = await fetch(`${apiUrl}/api/files/${attachment.id}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const { download_url } = await downloadResponse.json()
  return download_url
}
```

### Pattern 4: Skeleton/Placeholder While Uploading
**What:** Show a pulsing skeleton animation at the cursor position while the image uploads, then replace with the actual image.
**When to use:** For all async image insertions to provide visual feedback.
**Example approach:**
```typescript
// Insert a placeholder node with a temporary data URL or loading class
// Option A: Insert image with placeholder src, replace when upload completes
const placeholderId = crypto.randomUUID()
const placeholderNode = view.state.schema.nodes.image?.create({
  src: 'data:image/svg+xml,...', // small SVG skeleton
  alt: 'Uploading...',
  'data-uploading': placeholderId,
})
// Insert placeholder, then replace after upload:
uploadImage(file).then(url => {
  // Find the placeholder node by position or attribute and replace src
})

// Option B (simpler): Use CSS animation on the img element while src is loading
// The `onload` event naturally ends the skeleton state
```

### Pattern 5: Content Converter - Image Node Handling
**What:** Add handlers for `image` node type in the Markdown and plain text converters.
**When to use:** When saving documents (content pipeline runs on every save).
**Example:**
```python
# In _md_nodes():
elif t == "image":
    src = node.get("attrs", {}).get("src", "")
    alt = node.get("attrs", {}).get("alt", "")
    title = node.get("attrs", {}).get("title", "")
    if title:
        parts.append(f'![{alt}]({src} "{title}")\n\n')
    else:
        parts.append(f"![{alt}]({src})\n\n")

# In _extract_text_from_nodes():
elif node.get("type") == "image":
    alt = node.get("attrs", {}).get("alt", "")
    if alt:
        parts.append(alt)
```

### Anti-Patterns to Avoid
- **Storing base64 images in document JSON:** Bloats content_json column, causes slow saves, and breaks content conversion. Always upload to MinIO and store URL references.
- **Using FileHandler extension on v2:** It's a Pro extension on TipTap v2; only free in v3. Use `editorProps.handlePaste`/`handleDrop` instead.
- **Allowing arbitrary external image URLs:** External images can break or be used for tracking. Only allow images uploaded through the application's upload pipeline.
- **Not handling presigned URL expiry:** MinIO presigned URLs expire (default 1 hour). The editor must handle expired URLs gracefully -- either refresh on load or use a proxy endpoint.
- **Duplicating the ResizableImage code:** The existing `RichTextEditor.tsx` has a working implementation. Extract it to a shared location rather than copy-pasting.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Image node in ProseMirror schema | Custom ProseMirror node spec | `@tiptap/extension-image` (already installed) | Handles parsing, serialization, and schema definition correctly |
| File upload multipart handling | Custom fetch wrapper | Existing `POST /api/files/upload` endpoint | Already handles MinIO upload, attachment DB record, bucket routing |
| Image resize math | Custom resize algorithm | Mouse delta calculation from RichTextEditor.tsx | Already handles min-width (50px), prevents negative sizes |
| Presigned URL generation | Direct MinIO client calls from frontend | Backend `GET /api/files/{id}` endpoint | Keeps MinIO credentials server-side, handles auth |

**Key insight:** This phase is primarily a "port and adapt" task. The existing `RichTextEditor.tsx` already solves every technical challenge (resize, paste, drop, upload, presigned URLs). The work is extracting shared components, integrating into the knowledge editor's factory pattern, and adding skeleton loading.

## Common Pitfalls

### Pitfall 1: Presigned URL Expiration in Saved Documents
**What goes wrong:** Images load fine initially but break after 1 hour when presigned URLs expire. Documents saved with presigned URLs have broken images on re-open.
**Why it happens:** MinIO presigned URLs have a default 1-hour TTL. If the URL is stored as the image `src` in `content_json`, it expires.
**How to avoid:** Two approaches:
1. **Proxy endpoint** (recommended): Store the MinIO object key as a custom attribute on the image node, and use a backend proxy endpoint (e.g., `GET /api/images/{object_key}`) that generates fresh presigned URLs. The editor intercepts image loads and rewrites URLs.
2. **URL refresh on load**: When a document is opened, scan all image nodes, extract attachment IDs, batch-refresh presigned URLs, and update the editor content before rendering.
**Warning signs:** Images work in the editor session but appear broken when reopening the document later.

### Pitfall 2: Duplicate Image on Paste from Web
**What goes wrong:** Pasting an image from a web page inserts two images: one from the HTML content and one from the file item.
**Why it happens:** The clipboard event contains both an HTML `<img>` tag and the raw image file as separate items.
**How to avoid:** In `handlePaste`, check for file items first. If an image file is found, call `event.preventDefault()` to block the default HTML paste. Alternatively, use `transformPastedHTML` to strip `<img>` tags from pasted HTML.
**Warning signs:** Pasting from a browser results in duplicate images.

### Pitfall 3: Image Resize Not Persisted
**What goes wrong:** User resizes an image, but the width is lost on save/reload.
**Why it happens:** The custom `width` attribute is not included in the TipTap JSON serialization, or the content converter strips it.
**How to avoid:** Ensure the `width` attribute is defined in `addAttributes()` with proper `parseHTML` and `renderHTML` methods. Verify that `editor.getJSON()` includes the width in the image node's `attrs`.
**Warning signs:** Resized images revert to original size after page refresh.

### Pitfall 4: Large Image Upload Blocking the UI
**What goes wrong:** Uploading a 5MB image freezes the editor for several seconds with no feedback.
**Why it happens:** No visual feedback during the async upload operation.
**How to avoid:** Insert a placeholder/skeleton immediately on paste/drop, then replace with the actual image when upload completes. Show error state if upload fails.
**Warning signs:** Editor feels unresponsive when pasting large images.

### Pitfall 5: Content Converter Ignoring Image Nodes
**What goes wrong:** Images in documents are silently dropped from Markdown and plain text output, breaking AI consumption and search indexing.
**Why it happens:** The content converter's `_md_nodes()` function falls through to the "unknown node" handler, which renders children -- but image nodes have no children.
**How to avoid:** Add explicit `image` node handlers to both `_md_nodes()` (for Markdown) and `_extract_text_from_nodes()` (for plain text). Add test cases covering image nodes.
**Warning signs:** Documents with images have empty sections in their Markdown/plain text representations.

## Code Examples

### Complete ResizableImageView React Component
```typescript
// Source: existing RichTextEditor.tsx lines 147-201
// To be extracted to: components/knowledge/ResizableImageView.tsx
import { useCallback, useRef, useState } from 'react'
import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react'
import { cn } from '@/lib/utils'

export function ResizableImageView({ node, updateAttributes, selected }: NodeViewProps) {
  const [isResizing, setIsResizing] = useState(false)
  const imageRef = useRef<HTMLImageElement>(null)
  const startXRef = useRef(0)
  const startWidthRef = useRef(0)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsResizing(true)
    startXRef.current = e.clientX
    startWidthRef.current = imageRef.current?.offsetWidth || 0

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const diff = moveEvent.clientX - startXRef.current
      const newWidth = Math.max(50, startWidthRef.current + diff)
      updateAttributes({ width: newWidth })
    }

    const handleMouseUp = () => {
      setIsResizing(false)
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [updateAttributes])

  return (
    <NodeViewWrapper className="inline-block relative" data-drag-handle>
      <div className={cn(
        'inline-block relative group',
        selected && 'ring-2 ring-primary/50 rounded'
      )}>
        <img
          ref={imageRef}
          src={node.attrs.src}
          alt={node.attrs.alt || ''}
          title={node.attrs.title || ''}
          width={node.attrs.width || undefined}
          className="max-w-full h-auto rounded-md block"
          style={node.attrs.width ? { width: `${node.attrs.width}px` } : undefined}
          draggable={false}
        />
        <div
          onMouseDown={handleMouseDown}
          className={cn(
            'absolute bottom-0 right-0 w-4 h-4 cursor-se-resize',
            'bg-primary/60 rounded-tl-sm opacity-0 group-hover:opacity-100 transition-opacity',
            isResizing && 'opacity-100'
          )}
          title="Drag to resize"
        />
      </div>
    </NodeViewWrapper>
  )
}
```

### Skeleton/Placeholder CSS Animation
```css
/* editor-styles.css addition */
.ProseMirror img[data-uploading="true"] {
  min-height: 100px;
  min-width: 200px;
  background: linear-gradient(
    90deg,
    hsl(var(--muted)) 25%,
    hsl(var(--muted-foreground) / 0.1) 50%,
    hsl(var(--muted)) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
  border-radius: 0.375rem;
}

@keyframes skeleton-pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

### Content Converter Image Handler (Python)
```python
# In _md_nodes(), add before the else clause:
elif t == "image":
    attrs = node.get("attrs", {})
    src = attrs.get("src", "")
    alt = attrs.get("alt", "")
    title = attrs.get("title", "")
    if title:
        parts.append(f'![{alt}]({src} "{title}")\n\n')
    else:
        parts.append(f"![{alt}]({src})\n\n")

# In _extract_text_from_nodes(), add before the elif "content" in node:
elif node.get("type") == "image":
    alt = node.get("attrs", {}).get("alt", "")
    if alt:
        parts.append(f"[Image: {alt}]")
```

### Document Image Upload Hook
```typescript
// use-image-upload.ts -- encapsulates the upload flow for the knowledge editor
import { useCallback } from 'react'
import { useAuthStore } from '@/contexts/auth-context'

const MAX_IMAGE_SIZE = 10 * 1024 * 1024 // 10MB for documents (vs 5MB for task descriptions)

export function useImageUpload(documentId: string | null) {
  const token = useAuthStore((s) => s.token)

  const uploadImage = useCallback(async (file: File): Promise<string | null> => {
    if (file.size > MAX_IMAGE_SIZE) return null
    if (!token) return null

    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8001'
    const formData = new FormData()
    formData.append('file', file)

    // Upload with entity_type=document scope
    const params = new URLSearchParams()
    if (documentId) {
      params.set('entity_type', 'document')
      params.set('entity_id', documentId)
    }

    const uploadResponse = await fetch(
      `${apiUrl}/api/files/upload?${params}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      }
    )

    if (!uploadResponse.ok) throw new Error('Upload failed')
    const attachment = await uploadResponse.json()

    const downloadResponse = await fetch(
      `${apiUrl}/api/files/${attachment.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      }
    )

    if (!downloadResponse.ok) throw new Error('Failed to get URL')
    const { download_url } = await downloadResponse.json()
    return download_url
  }, [token, documentId])

  return { uploadImage }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom ProseMirror image node | `@tiptap/extension-image` with extend | TipTap v2 | Standard extension handles schema, parsing, serialization |
| `@tiptap-pro/extension-file-handler` (paid, v2) | `editorProps.handlePaste` + `handleDrop` | TipTap v2 | Free, no external dependency, full control |
| `Image.configure({ resize: {...} })` | Custom NodeView with ReactNodeViewRenderer | TipTap v2 (resize config is v3.10+ only) | Must use custom NodeView approach on v2 |
| Base64 inline images | MinIO object storage with presigned URLs | Current architecture | Scalable, no document bloat |

**Deprecated/outdated:**
- `@tiptap-pro/extension-file-handler`: Pro-only on v2; free version available only in v3. Not usable with our v2 stay-put decision.
- `Image.configure({ resize: {...} })`: Only available in TipTap v3.10+. On v2, must use `Image.extend()` with custom NodeView.

## Open Questions

1. **Presigned URL strategy for persisted documents**
   - What we know: The existing `RichTextEditor.tsx` stores presigned URLs directly as image `src` in JSON content. These expire after 1 hour.
   - What's unclear: Whether a proxy endpoint, URL-refresh-on-load, or long-lived URLs (configurable expiry) is the right approach for knowledge base documents that persist long-term.
   - Recommendation: Start with URL-refresh-on-load (scan image nodes when document opens, batch-refresh via `POST /api/files/download-urls`). This uses existing infrastructure. Consider a proxy endpoint in a future phase if refresh-on-load creates UX latency.

2. **Entity type for document image uploads**
   - What we know: The existing upload endpoint supports `entity_type` (task, comment) and `entity_id`. Documents are not currently a supported entity type.
   - What's unclear: Whether to add `document` as an entity type in the `EntityType` enum, or upload images without entity association.
   - Recommendation: Add `document` to the `EntityType` enum and pass `entity_type=document&entity_id={documentId}` on upload. This enables future features like listing all images in a document, or cleaning up orphaned images on document delete.

3. **Image size limit for knowledge documents**
   - What we know: Task descriptions use 5MB limit. The backend upload endpoint has a 100MB max.
   - What's unclear: What's the right limit for knowledge documents?
   - Recommendation: Use 10MB for knowledge documents (more generous than task descriptions, but well within backend limit). Validate client-side before upload.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `electron-app/src/renderer/components/editor/RichTextEditor.tsx` -- complete working implementation of ResizableImage, paste, drop, upload
- Existing codebase: `fastapi-backend/app/services/minio_service.py` -- MinIOService with pm-images bucket
- Existing codebase: `fastapi-backend/app/routers/files.py` -- upload/download endpoints
- Existing codebase: `electron-app/src/renderer/components/knowledge/editor-extensions.ts` -- extension factory
- Existing codebase: `fastapi-backend/app/services/content_converter.py` -- content pipeline (no image handler yet)
- [TipTap Image Extension Official Docs](https://tiptap.dev/docs/editor/extensions/nodes/image) -- configuration, commands, attributes

### Secondary (MEDIUM confidence)
- [TipTap FileHandler Extension Docs](https://tiptap.dev/docs/editor/extensions/functionality/filehandler) -- confirmed v3/Pro-only for v2
- [Codemzy Blog - Drag and Drop Image Uploads](https://www.codemzy.com/blog/tiptap-drag-drop-image) -- handleDrop pattern
- [Codemzy Blog - Pasting Images](https://www.codemzy.com/blog/tiptap-pasting-images) -- handlePaste pattern, duplicate image fix
- [@tiptap/extension-file-handler npm](https://www.npmjs.com/package/@tiptap/extension-file-handler) -- confirmed v3 only (3.14.0)

### Tertiary (LOW confidence)
- [tiptap-extension-resize-image npm](https://www.npmjs.com/package/tiptap-extension-resize-image) -- alternative resize package (not recommended: existing code is better)
- [GitHub Gist - Image Upload Extension](https://gist.github.com/slava-vishnyakov/16076dff1a77ddaca93c4bccd4ec4521) -- community patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and proven in codebase
- Architecture: HIGH -- existing RichTextEditor.tsx provides a complete reference implementation
- Pitfalls: HIGH -- presigned URL expiry and duplicate paste are well-documented; content converter gap identified by direct code inspection

**Research date:** 2026-02-01
**Valid until:** 2026-03-01 (stable -- TipTap v2 is not changing, MinIO is stable)
