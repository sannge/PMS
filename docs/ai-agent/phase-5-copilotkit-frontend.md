# Phase 5: CopilotKit Frontend (Chat Sidebar)

**Goal**: User-facing AI chat sidebar with streaming, tool execution visibility, and confirmation dialogs.

**Depends on**: Phase 4 (agent backend)
**Blocks**: Phase 7 (admin UI builds on these patterns)

---

## Task 5.1: Frontend Dependencies

### Modify: `electron-app/package.json`

Add to `dependencies`:
```json
"@copilotkit/react-core": "^1.x",
"@copilotkit/react-ui": "^1.x"
```

Run:
```bash
cd electron-app && npm install
```

### Acceptance Criteria
- [ ] Dependencies install without conflicts
- [ ] TypeScript types available for both packages
- [ ] `npm run typecheck` passes

---

## Task 5.2: CopilotKit Provider

### New File: `electron-app/src/renderer/components/ai/copilot-provider.tsx`

```tsx
import { CopilotKit } from "@copilotkit/react-core"

interface CopilotProviderProps {
  children: React.ReactNode
}

export function CopilotProvider({ children }: CopilotProviderProps) {
  /**
   * Wraps the app in CopilotKit context.
   * - Connects to /api/copilotkit endpoint
   * - Injects auth token from existing auth store (useAuthStore)
   * - Configures agent name: "blair"
   *
   * Auth token pattern:
   * - Read from useAuthStore().token (existing auth store)
   * - Pass as header in CopilotKit's runtimeUrl config
   */

  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      // Auth headers configuration
      // Agent configuration
    >
      {children}
    </CopilotKit>
  )
}
```

### Modify: `electron-app/src/renderer/pages/dashboard.tsx`

Wrap dashboard content in `<CopilotProvider>`:

```tsx
// In DashboardPage component:
return (
  <CopilotProvider>
    {/* existing dashboard content */}
    <AiSidebar />
  </CopilotProvider>
)
```

### Acceptance Criteria
- [ ] CopilotKit context available to all dashboard children
- [ ] Auth token passed correctly to backend
- [ ] Provider doesn't render anything visible (wrapper only)
- [ ] Works with existing auth flow (token refresh, logout)

---

## Task 5.3: AI Sidebar Component

### New File: `electron-app/src/renderer/components/ai/ai-sidebar.tsx`

```tsx
/**
 * Main AI chat sidebar component.
 * Uses Blair Sidebar (via CopilotSidebar) with custom styling to match PM Desktop design system.
 *
 * Features:
 * - Collapsible right panel
 * - Resizable width (drag handle on left edge)
 * - Width persisted to localStorage
 * - Chat input with markdown support
 * - Image paste (Ctrl+V) and upload (click attachment icon) in chat input
 * - Image preview thumbnails before sending
 * - Streaming message display
 * - "New Chat" button to reset conversation
 * - Source citations linking to documents (clickable)
 * - Tool execution visibility (shows what the agent did)
 *
 * Layout:
 * ┌──────────────────────────────────┐
 * │ Blair            [New] [X]  │  ← Header
 * ├──────────────────────────────────┤
 * │                                  │
 * │  User: What tasks are overdue?   │  ← Messages area
 * │                                  │
 * │  AI: Found 3 overdue tasks:      │
 * │  ┌─────────────────────────┐     │
 * │  │ 🔧 Searched tasks       │     │  ← Tool execution card
 * │  └─────────────────────────┘     │
 * │  1. PROJ-12: Fix login...        │
 * │  2. PROJ-15: Update API...       │
 * │                                  │
 * │  📄 Source: API Documentation    │  ← Clickable citation
 * │                                  │
 * ├──────────────────────────────────┤
 * │ ┌──────┐ ┌──────┐               │  ← Image previews (if attached)
 * │ │ img1 │ │ img2 │  ✕            │
 * │ └──────┘ └──────┘               │
 * ├──────────────────────────────────┤
 * │ Ask Blair anything...  [📎] [Send]  │  ← Input area (📎 = attach image)
 * └──────────────────────────────────┘
 *
 * Width: Default 400px, min 300px, max 600px
 * Persisted: localStorage key "ai-sidebar-width"
 */
```

### Implementation Details

- Uses `Blair Sidebar (via CopilotSidebar)` from `@copilotkit/react-ui` as base
- Custom header with "Blair" title, "New Chat" button, close button
- Message area uses custom renderer (see Task 5.7)
- Resize handle on left edge using pointer events (similar to existing panel resizers)
- Width stored in `localStorage` (NOT IndexedDB — lightweight preference)
- Sidebar visibility controlled by `useAiSidebar` store (Task 5.5)
- Renders conditionally based on `isOpen` state

### Time Travel / Conversation Rollback UI

Users can rewind the conversation to any previous Blair response and branch from there. This leverages LangGraph's checkpoint system (see Phase 4, Task 4.5b).

**Interaction flow:**

1. **Hover over any Blair message** → a small rewind icon (`RotateCcw` from lucide-react) appears in the top-right corner of the message bubble
2. **Click the rewind icon** → the conversation enters "rewind mode":
   - All messages **after** the selected message are visually dimmed (opacity 0.3) and marked with a strikethrough
   - A rewind banner appears above the chat input
   - The chat input is active and focused, ready for a new message

3. **Rewind banner:**
   ```
   ┌────────────────────────────────────────────────────┐
   │ ⟲ Rewound to: "Found 3 overdue tasks..."         │
   │   Type a new message to branch from this point.    │
   │                                        [Cancel]   │
   └────────────────────────────────────────────────────┘
   ```

4. **User types a new message** → sends `POST /api/ai/chat/replay` with the checkpoint_id corresponding to the selected message + the new message. Blair responds from the rewound state. The dimmed messages are removed and the new branch continues.

5. **User clicks Cancel** → exits rewind mode, restores the full conversation to its latest state.

**State management:**
```typescript
// Add to useAiSidebar store:
interface AiSidebarState {
  // ... existing fields ...
  rewindCheckpointId: string | null   // Active rewind target (null = not rewinding)
  rewindMessageIndex: number | null   // Which message to rewind to
  enterRewindMode: (checkpointId: string, messageIndex: number) => void
  exitRewindMode: () => void
}
```

**Key UX decisions:**
- Rewind icon only appears on **Blair's messages** (not user messages) — you rewind to a specific Blair response
- The dimmed messages are non-interactive (no rewind icons, no clickable links)
- If the user has a pending HITL confirmation (approve/reject), rewinding past that point cancels it
- "New Chat" always starts fresh (clears all history + checkpoints)

### Image Input in Chat

Users can attach images to their chat messages in two ways:

1. **Paste from clipboard** (`Ctrl+V` / `Cmd+V`):
   - Listen for `paste` event on the chat input area
   - Extract image files from `clipboardData.items` (filter by `image/*` MIME types)
   - Convert to base64 via `FileReader.readAsDataURL()`
   - Add to pending attachments state

2. **Upload via attachment button** (paperclip icon):
   - Hidden `<input type="file" accept="image/*" multiple />` triggered by button click
   - Convert selected files to base64
   - Add to pending attachments state

**Pending attachments state** (local component state, not Zustand):
```typescript
interface PendingImage {
  id: string          // Unique ID for removal
  data: string        // Base64-encoded image data (without data URI prefix)
  mediaType: string   // "image/png", "image/jpeg", etc.
  filename: string    // Original filename or "pasted-image.png"
  previewUrl: string  // Object URL for thumbnail preview (revoke on unmount)
}

const [pendingImages, setPendingImages] = useState<PendingImage[]>([])
```

**Image preview area** (above input, only visible when images attached):
- Row of thumbnail previews (64x64, object-fit: cover)
- Each thumbnail has a remove button (X)
- Shows count if > 3 images: "2 more..."
- Max 5 images per message (additional pastes/uploads rejected with toast)
- Max 10MB per image (oversized files rejected with toast)

**On send**:
- Include `images` array in the ChatRequest payload alongside the message text
- Clear pending images after successful send
- Revoke object URLs to prevent memory leaks

### Acceptance Criteria
- [ ] Sidebar appears on right side of dashboard
- [ ] Resizable via drag handle
- [ ] Width persisted across sessions
- [ ] "New Chat" clears conversation
- [ ] Close button hides sidebar
- [ ] Messages stream in real-time
- [ ] Matches PM Desktop design system (colors, fonts, spacing)
- [ ] Scrolls to bottom on new messages
- [ ] Input supports Enter to send, Shift+Enter for newline
- [ ] Ctrl+V pastes images from clipboard into chat
- [ ] Attachment button opens file picker for image upload
- [ ] Image thumbnails preview before sending
- [ ] Remove button on each thumbnail
- [ ] Max 5 images per message enforced
- [ ] Max 10MB per image enforced
- [ ] Images sent as base64 in ChatRequest.images
- [ ] AI responds with understanding of the image content
- [ ] Object URLs cleaned up on unmount (no memory leaks)

---

## Task 5.4: Sidebar Toggle Button

### New File: `electron-app/src/renderer/components/ai/ai-toggle-button.tsx`

```tsx
import { Sparkles } from "lucide-react"

/**
 * Toggle button for the AI sidebar.
 * Placed in the dashboard header/toolbar area.
 *
 * - Uses Sparkles icon from lucide-react
 * - Radix UI Button with ghost variant
 * - Tooltip: "Blair"
 * - Active state (highlighted) when sidebar is open
 * - Keyboard shortcut: Ctrl+Shift+A (shown in tooltip)
 */

export function AiToggleButton() {
  const { isOpen, toggle } = useAiSidebar()

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      className={cn(
        "relative",
        isOpen && "bg-accent text-accent-foreground"
      )}
      title="Blair (Ctrl+Shift+A)"
    >
      <Sparkles className="h-4 w-4" />
    </Button>
  )
}
```

### Modify: Dashboard Header

Add `<AiToggleButton />` to the dashboard header component, alongside existing toolbar buttons.

### Acceptance Criteria
- [ ] Button visible in dashboard header
- [ ] Clicking toggles sidebar open/closed
- [ ] Visual active state when sidebar is open
- [ ] Keyboard shortcut Ctrl+Shift+A works
- [ ] Tooltip shows shortcut hint

---

## Task 5.5: Sidebar State Store

### New File: `electron-app/src/renderer/components/ai/use-ai-sidebar.ts`

```typescript
import { create } from "zustand"

/**
 * Zustand store for AI sidebar state.
 *
 * IMPORTANT: NOT persisted to IndexedDB.
 * Chat state is session-only — clears on:
 * - App close
 * - Logout
 * - User clicks "New Chat"
 *
 * Sidebar open/close state IS persisted to localStorage
 * (lightweight, not part of chat history).
 */

interface AiSidebarState {
  isOpen: boolean
  toggle: () => void
  open: () => void
  close: () => void
  resetChat: () => void  // Clears conversation, keeps sidebar open
}

export const useAiSidebar = create<AiSidebarState>((set) => ({
  isOpen: localStorage.getItem("ai-sidebar-open") === "true",

  toggle: () =>
    set((state) => {
      const newState = !state.isOpen
      localStorage.setItem("ai-sidebar-open", String(newState))
      return { isOpen: newState }
    }),

  open: () => {
    localStorage.setItem("ai-sidebar-open", "true")
    set({ isOpen: true })
  },

  close: () => {
    localStorage.setItem("ai-sidebar-open", "false")
    set({ isOpen: false })
  },

  resetChat: () => {
    // Signal to CopilotKit to clear conversation
    // Implementation depends on CopilotKit API
    // May need to increment a key to force remount
  },
}))
```

### Acceptance Criteria
- [ ] `isOpen` toggle works correctly
- [ ] Open/close state persisted to localStorage
- [ ] `resetChat` clears conversation but keeps sidebar open
- [ ] NOT persisted to IndexedDB (session-only for chat content)
- [ ] Store accessible from any component via `useAiSidebar()`

---

## Task 5.6: Inline Tool Confirmation Cards

### New File: `electron-app/src/renderer/components/ai/tool-confirmation.tsx`

```tsx
/**
 * INLINE confirmation card for Blair's write actions.
 *
 * IMPORTANT: This is NOT a modal dialog. It renders directly in the chat
 * message stream as a special message type, keeping the conversation
 * flow natural and agentic.
 *
 * Triggered when Blair invokes a WRITE tool (create_task, update_status, etc.).
 * The AG-UI INTERRUPT event from the backend triggers this card to appear
 * inline in the chat, between Blair's reasoning and the final response.
 *
 * Layout (rendered inline in the chat stream):
 *
 * ┌──────────────────────────────────────────────────────┐
 * │ Blair's message stream...                            │
 * │                                                      │
 * │ ┌─────────────────────────────────────────────────┐  │
 * │ │ ✏️ Blair wants to create a task                 │  │  ← Inline card
 * │ │                                                 │  │     (not a modal)
 * │ │   Title: Fix login bug                          │  │
 * │ │   Project: Project Alpha                        │  │
 * │ │   Priority: High                                │  │
 * │ │   Assignee: John Doe                            │  │
 * │ │                                                 │  │
 * │ │   [Approve ✓]  [Reject ✗]                      │  │
 * │ └─────────────────────────────────────────────────┘  │
 * │                                                      │
 * │ (After approval, Blair's response continues below)   │
 * └──────────────────────────────────────────────────────┘
 *
 * After user responds, the card updates:
 * - Approved: Card shows ✅ checkmark, buttons disabled, "Approved" label
 * - Rejected: Card shows ❌, buttons disabled, "Cancelled" label
 *
 * Action types and their display:
 * - create_task: Shows title, project, priority, assignee
 * - update_task_status: Shows task key, current → new status
 * - assign_task: Shows task key, assignee name
 * - create_document: Shows title, scope, folder
 */

interface ToolConfirmationProps {
  action: {
    type: string        // "create_task", "update_task_status", etc.
    summary: string     // Human-readable one-line summary
    details: Record<string, unknown>  // Action-specific details
  }
  status: "pending" | "approved" | "rejected"
  onApprove: () => void   // Sends Command(resume={approved: true}) to LangGraph
  onReject: () => void    // Sends Command(resume={approved: false}) to LangGraph
}
```

### CopilotKit INTERRUPT Handling

```tsx
// In the CopilotKit configuration, register a custom renderer for INTERRUPT events:
// CopilotKit's useCoAgent or useCopilotChat provides an onInterrupt callback

// When AG-UI INTERRUPT event arrives:
// 1. Parse the interrupt payload — check the "type" field
// 2. If type === "confirmation" → render ToolConfirmationCard
// 3. If type === "clarification" → render ClarificationCard
// 4. On user response, send Command(resume={...}) back to backend
// 5. LangGraph resumes from checkpoint with user's decision/answer
```

### Inline Clarification Cards

When Blair needs clarification (via `request_clarification` tool), a different card type renders in the chat stream. Unlike confirmation cards (binary approve/reject), clarification cards allow the user to select from suggested options OR type a free-text answer.

```tsx
/**
 * INLINE clarification card for Blair's follow-up questions.
 *
 * Triggered when Blair calls the request_clarification tool via interrupt().
 * Renders inline in the chat stream as a question with options.
 *
 * Layout (rendered inline in the chat stream):
 *
 * ┌──────────────────────────────────────────────────────┐
 * │ Blair's message stream...                            │
 * │                                                      │
 * │ ┌─────────────────────────────────────────────────┐  │
 * │ │ 💬 Blair needs more info:                       │  │  ← Inline card
 * │ │                                                 │  │
 * │ │   "Which project did you mean?"                 │  │  ← Question
 * │ │                                                 │  │
 * │ │   I found 3 projects matching your request      │  │  ← Context (optional)
 * │ │                                                 │  │
 * │ │   [Project Alpha]  [Project Beta]               │  │  ← Option buttons
 * │ │   [Project Gamma]  [All projects]               │  │
 * │ │                                                 │  │
 * │ │   Or type your answer:                          │  │
 * │ │   [_______________________________] [Send]      │  │  ← Free-text input
 * │ └─────────────────────────────────────────────────┘  │
 * │                                                      │
 * │ (After user responds, Blair continues below)         │
 * └──────────────────────────────────────────────────────┘
 *
 * After user responds, the card updates:
 * - Selected option highlighted, other options dimmed
 * - Or typed answer shown in place of input
 * - Card becomes non-interactive (read-only)
 */

interface ClarificationCardProps {
  question: string                  // The clarifying question
  options: string[] | null          // Suggested answers (shown as buttons, max 4)
  context: string | null            // Why Blair is asking (subtitle text)
  status: "pending" | "answered"
  selectedAnswer: string | null     // The answer the user gave
  onSelectOption: (option: string) => void   // Command(resume={answer: option})
  onSubmitText: (text: string) => void       // Command(resume={answer: text})
}
```

**Key UX details:**
- Options render as pill buttons (similar to chat quick-reply patterns)
- Free-text input always available below options (users aren't limited to provided options)
- Pressing Enter in the text input submits the answer
- Clicking an option immediately submits (no additional confirmation needed)
- After answering, the card becomes read-only showing what the user chose
- If no options are provided (options is null), only the free-text input is shown

### Acceptance Criteria
- [ ] Confirmation renders INLINE in the chat stream (NOT as a modal dialog)
- [ ] Card appears as part of the conversation flow
- [ ] "Approve" resumes LangGraph via `Command(resume={approved: true})`
- [ ] "Reject" resumes LangGraph via `Command(resume={approved: false})`
- [ ] Card status updates after user response (visual feedback: approved/rejected)
- [ ] Details formatted nicely for each action type
- [ ] Buttons disabled after user responds (prevent double-submit)
- [ ] Keyboard: Enter approves, Escape rejects (for confirmation cards)
- [ ] Pending confirmation persists across sidebar close/reopen (checkpoint in LangGraph)
- [ ] No modal or popup — purely inline UX
- [ ] Clarification card renders with question, context, and option buttons
- [ ] Clarification options render as pill buttons (clickable, immediate submit)
- [ ] Free-text input always available below options
- [ ] Clicking an option sends `Command(resume={answer: "..."})`
- [ ] Typing an answer and pressing Enter/Send sends `Command(resume={answer: "..."})`
- [ ] After answering, clarification card becomes read-only (shows selected answer)
- [ ] Blair continues reasoning after receiving clarification (no dead-end)
- [ ] Clarification card without options shows only free-text input

---

## Task 5.7: Custom Message Renderer

### New File: `electron-app/src/renderer/components/ai/ai-message-renderer.tsx`

```tsx
/**
 * Custom renderer for AI chat messages.
 *
 * Handles:
 * 1. Markdown rendering (code blocks, tables, lists, bold, italic)
 *    - Use existing markdown rendering patterns if available
 *    - Or use a lightweight markdown-to-JSX library
 *
 * 2. Clickable entity references:
 *    - Task keys (e.g., "PROJ-12") → Open task detail panel
 *    - Document titles → Navigate to document in knowledge base
 *    - Project names → Open project board
 *    - Uses state-based navigation (not react-router)
 *
 * 3. Tool execution cards:
 *    Shows what the agent did during reasoning:
 *    ┌─────────────────────────────┐
 *    │ 🔍 Searched knowledge base  │
 *    │    Found 5 results          │
 *    └─────────────────────────────┘
 *    ┌─────────────────────────────┐
 *    │ 📊 Checked project status   │
 *    │    Project Alpha: 72% done  │
 *    └─────────────────────────────┘
 *
 * 4. Source citations:
 *    At the bottom of messages that cite documents:
 *    📄 Sources:
 *    - API Documentation (click to open)
 *    - Sprint 12 Notes (click to open)
 *
 * 5. Error messages:
 *    Styled differently (red/warning) for rate limits, auth errors, etc.
 */

interface AiMessageProps {
  message: {
    role: "user" | "assistant"
    content: string
    images?: { data: string; mediaType: string }[]  // User-sent images
    tool_calls?: ToolCallInfo[]
    sources?: SourceCitation[]
  }
  onNavigate: (target: NavigationTarget) => void  // State-based navigation
}

/**
 * User messages with images:
 * - Display image thumbnails inline above the text
 * - Clickable to open full-size in a lightbox/modal
 * - Alt text: filename or "Attached image"
 *
 * Assistant messages referencing images:
 * - AI response text describes what it sees in the images
 * - No special rendering needed — just standard markdown
 */
```

### Navigation Pattern

Since PM Desktop uses state-based routing (not react-router), clickable references must use the existing navigation callbacks:

```tsx
// Navigate to task detail
onNavigate({ type: "task", taskId: "...", projectId: "..." })

// Navigate to document and highlight cited text
onNavigate({
  type: "document",
  documentId: "...",
  highlight: {
    headingContext: "Payment Flow",       // Scroll to this heading
    chunkText: "The payment service...",  // Highlight this text
    chunkIndex: 3                         // Fallback position
  }
})

// Navigate to canvas and highlight specific element
onNavigate({
  type: "document",  // Canvas is a document type
  documentId: "...",
  highlight: {
    elementId: "elem-1",                  // Canvas element to highlight
    chunkText: "Payment flow needs..."    // Text to flash
  }
})

// Navigate to project board
onNavigate({ type: "project", projectId: "...", applicationId: "..." })
```

### Source Reference Click → Navigate + Highlight

When the user clicks a source reference link in Blair's response, the system:

1. **Navigates to the document** using state-based routing
2. **Scrolls to the heading** specified in `heading_context` (for regular documents)
3. **Highlights the cited text** with a temporary visual indicator

**Implementation for regular documents (TipTap editor):**
```tsx
// In the document editor, check for incoming highlight params:
useEffect(() => {
  if (highlight && editor) {
    // 1. Find the heading node matching headingContext
    const headingPos = findHeadingPosition(editor, highlight.headingContext)
    if (headingPos) {
      // Scroll the heading into view
      const domNode = editor.view.nodeDOM(headingPos)
      domNode?.scrollIntoView({ behavior: "smooth", block: "center" })
    }

    // 2. Find and highlight the cited text
    const textPos = findTextInDocument(editor, highlight.chunkText)
    if (textPos) {
      // Apply temporary highlight decoration
      editor.chain()
        .setTextSelection({ from: textPos.from, to: textPos.to })
        .run()

      // Add a temporary yellow highlight mark
      applyTemporaryHighlight(editor, textPos.from, textPos.to, {
        className: "blair-citation-highlight",
        duration: 4000  // Fade after 4 seconds
      })
    }
  }
}, [highlight, editor])
```

**CSS for citation highlight:**
```css
.blair-citation-highlight {
  background-color: rgba(250, 204, 21, 0.4); /* yellow-400/40% */
  border-radius: 2px;
  transition: background-color 1s ease-out;
}

.blair-citation-highlight.fading {
  background-color: transparent;
}
```

**Implementation for canvas documents:**
```tsx
// In the canvas viewer, check for incoming highlight params:
useEffect(() => {
  if (highlight?.elementId && canvasRef.current) {
    // 1. Find the canvas element by ID
    const element = canvasRef.current.getElement(highlight.elementId)
    if (element) {
      // 2. Pan canvas to center the element
      canvasRef.current.centerOnElement(element.id, { animate: true })

      // 3. Apply temporary highlight ring around the element
      canvasRef.current.highlightElement(element.id, {
        color: "rgba(250, 204, 21, 0.6)",
        duration: 4000
      })
    }
  }
}, [highlight, canvasRef])
```

### Tool Execution Cards (Progressive Disclosure)

Blair's reasoning steps are shown as collapsible cards in the message stream:

```tsx
/**
 * Tool execution card — shows what Blair did during reasoning.
 *
 * States:
 * - Executing: Animated spinner + tool name
 *   ┌─────────────────────────────┐
 *   │ 🔄 Searching knowledge...   │
 *   └─────────────────────────────┘
 *
 * - Completed: Collapsible result summary
 *   ┌─────────────────────────────┐
 *   │ ✅ Searched knowledge base  │ ← Click to expand
 *   │    Found 5 results          │
 *   ├─────────────────────────────┤ ← Expanded section
 *   │  1. API Architecture [0.92] │
 *   │  2. Sprint 12 Notes [0.85]  │
 *   │  3. ...                     │
 *   └─────────────────────────────┘
 *
 * - Error: Red indicator
 *   ┌─────────────────────────────┐
 *   │ ❌ Knowledge search failed  │
 *   │    Rate limit exceeded      │
 *   └─────────────────────────────┘
 */
```

### Acceptance Criteria
- [ ] Markdown renders correctly (code blocks, tables, lists)
- [ ] Task keys are clickable and navigate to task detail
- [ ] Document titles are clickable and open the document
- [ ] Source citation clicks navigate to document AND highlight cited text
- [ ] Heading scroll-to works (smooth scroll to the section)
- [ ] Text highlight applies temporary yellow background (fades after 4s)
- [ ] Canvas citations navigate to canvas AND highlight the specific element
- [ ] Tool execution cards show Blair's reasoning steps with progressive disclosure
- [ ] Tool cards are collapsible (summary always visible, details expandable)
- [ ] Source citations link to original documents with relevance scores
- [ ] Error messages styled distinctly
- [ ] Navigation uses state-based routing (not URL changes)
- [ ] User-sent images displayed as inline thumbnails in messages

---

## Task 5.8: Context Injection

### Modify: Key page components to inject context via `useCopilotReadable`

This lets the AI know what the user is currently viewing for contextual responses.

**In project board view** (e.g., `pages/projects/[id].tsx`):
```tsx
import { useCopilotReadable } from "@copilotkit/react-core"

// Inside component:
useCopilotReadable({
  description: "Currently viewed project",
  value: {
    projectName: project.name,
    projectId: project.id,
    applicationName: application.name,
    taskCount: tasks.length,
    statusDistribution: statusCounts,  // { todo: 5, in_progress: 3, done: 12 }
  }
})
```

**In document editor** (e.g., `components/knowledge/document-editor.tsx`):
```tsx
useCopilotReadable({
  description: "Currently viewed document",
  value: {
    documentId: document.id,
    documentTitle: document.title,
    documentType: document.type,  // "document" or "canvas"
    scope: document.scope,
    folderPath: document.folder_path,
    // Content summary (first 500 chars of text, not full content)
    contentPreview: extractTextPreview(content, 500),
  }
})
```

**In canvas viewer** (when viewing a CANVAS document):
```tsx
useCopilotReadable({
  description: "Currently viewed canvas",
  value: {
    documentId: canvas.id,
    documentTitle: canvas.title,
    documentType: "canvas",
    scope: canvas.scope,
    elementCount: canvas.elements.length,
    // Summary of element types and key text content
    elementSummary: summarizeCanvasElements(canvas.elements, 500),
  }
})
```

**In application overview** (e.g., `pages/applications/[id].tsx`):
```tsx
useCopilotReadable({
  description: "Currently viewed application",
  value: {
    applicationName: application.name,
    applicationId: application.id,
    projectCount: projects.length,
    memberCount: members.length,
  }
})
```

### Acceptance Criteria
- [ ] AI knows which project/document/application the user is viewing
- [ ] Context updates when user navigates between screens
- [ ] Context removed when component unmounts (state-based routing)
- [ ] Content preview is truncated (not full document in context)
- [ ] No performance impact (useCopilotReadable is lightweight)

---

## Task 5.9: Styles

### New File: `electron-app/src/renderer/components/ai/ai-styles.css`

```css
/**
 * Override CopilotKit defaults to match PM Desktop theme.
 *
 * PM Desktop uses:
 * - TailwindCSS with custom theme
 * - Radix UI colors (--accent, --muted, etc.)
 * - Inter font family
 * - Consistent border-radius, spacing, shadows
 *
 * Overrides needed:
 * - CopilotKit sidebar background → match app background
 * - Message bubbles → match app card style
 * - Input field → match existing input components
 * - Send button → match existing button style
 * - Scrollbar → match existing scroll areas
 * - Font → Inter (match app)
 * - Colors → use CSS variables from theme
 *
 * Import this file in ai-sidebar.tsx or in the main app styles.
 */
```

### Acceptance Criteria
- [ ] CopilotKit sidebar visually matches PM Desktop design
- [ ] Colors use existing CSS variables (theme-aware)
- [ ] Font matches app (Inter)
- [ ] Dark mode compatible (if app supports it)
- [ ] No visual jarring between AI sidebar and rest of app

---

## Task 5.10: Query Keys

### Modify: `electron-app/src/renderer/lib/query-client.ts`

Add AI-related query keys following existing patterns (lines 64-150):

```typescript
// AI Configuration
aiConfig: ['ai', 'config'] as const,
aiProviders: ['ai', 'providers'] as const,
aiModels: ['ai', 'models'] as const,

// AI Import
importJob: (jobId: string) => ['ai', 'import', jobId] as const,
importJobs: ['ai', 'import', 'jobs'] as const,

// AI Indexing
documentIndexStatus: (docId: string) => ['ai', 'index-status', docId] as const,
applicationIndexStatus: (appId: string) => ['ai', 'index-status', 'application', appId] as const,
indexProgress: ['ai', 'index-progress'] as const,
```

### Acceptance Criteria
- [ ] Query keys follow existing naming pattern
- [ ] Keys are properly typed (as const)
- [ ] Parameterized keys use factory functions
- [ ] No collisions with existing keys

---

## Verification Checklist

```
1. Open app, click Blair toggle button in header
   → Blair sidebar opens on the right side

2. Type "What projects do I have?"
   → Streaming response appears with project list
   → Tool execution card shows "Searched projects" with result count

3. Type "Tell me about the payment system"
   → Blair searches knowledge base (tool card: "Searching knowledge...")
   → Response includes source reference links at bottom
   → Source links show: document title, section, score, source type (semantic/keyword/fuzzy/graph)
   → Click a source link → navigates to that document, scrolls to heading, highlights cited text with yellow flash

4. Type "Create a task called 'Test Blair' in Project X"
   → Inline confirmation card appears IN the chat stream (not a modal)
   → Card shows: action type, title, project details
   → Click "Approve" → card updates to "Approved ✅", Blair confirms task creation

5. Navigate to a project board, then ask "What's the status of this project?"
   → Blair uses context injection to know which project (no need to specify)

6. Navigate to a document, ask "Summarize this document"
   → Blair uses context injection, returns summary with source references
   → Click source link → scrolls within same document to cited section, highlights text

7. Navigate to a canvas document, ask "What's on this canvas?"
   → Blair summarizes canvas elements
   → Source references include canvas element IDs
   → Click source → pans canvas to element, highlights it

8. Close sidebar, navigate to different screen, reopen
   → Chat history preserved (session-only Zustand)
   → Any pending HITL confirmation still shows (LangGraph checkpoint)

9. Click "New Chat"
   → Conversation cleared, sidebar stays open

10. Resize sidebar by dragging left edge
    → Width changes, persisted on next open

11. Close app, reopen
    → Chat history gone (session-only), sidebar open/close state preserved

12. Keyboard: Ctrl+Shift+A
    → Toggles Blair sidebar

12. Copy an image to clipboard, paste in chat input (Ctrl+V)
    → Image thumbnail appears above input area

13. Click attachment (paperclip) button, select image file
    → Image thumbnail appears above input area

14. Send message with attached image: "What does this diagram show?"
    → AI describes the image content accurately

15. Send message with 2+ images: "Compare these two screenshots"
    → AI analyzes and compares both images

16. Try pasting a 6th image (when 5 already attached)
    → Toast notification: "Maximum 5 images per message"

17. Type a vague request: "Show me the project status"  (when user has multiple projects)
    → Blair shows inline clarification card with project options as buttons
    → Click a project button → Blair continues and shows that project's status

18. Type "Tell me about the auth flow"  (ambiguous topic)
    → If Blair finds limited results, clarification card appears with options
    → Type a custom answer in the free-text input → Blair uses that to refine search

19. After answering a clarification, verify the card becomes read-only
    → Selected option is highlighted, other options dimmed, input disabled

20. Hover over a Blair response → rewind icon appears in top-right corner

21. Click rewind icon on an earlier Blair message
    → Messages after that point become dimmed with strikethrough
    → Rewind banner appears above the input: "Rewound to: ..."
    → Chat input is active and focused

22. Type a new message in rewind mode
    → Blair responds from the rewound state (old branch replaced)
    → Dimmed messages disappear, conversation continues from the new branch

23. Enter rewind mode, then click Cancel
    → Full conversation restores to latest state, rewind mode exits
```
