# Phase 5: CopilotKit Frontend (Chat Sidebar) — Task Breakdown

**Created**: 2026-02-24
**Last updated**: 2026-02-24
**Status**: NOT STARTED
**Spec**: [phase-5-copilotkit-frontend.md](../phase-5-copilotkit-frontend.md)

> **Depends on**: Phase 4 (LangGraph Agent Backend)
> **Blocks**: Phase 7 (Admin UI builds on these patterns)

## Team

| Role | Abbreviation |
|------|-------------|
| Frontend Engineer | **FE** |
| Backend Engineer | **BE** |
| Database Engineer | **DBE** |
| Code Reviewer 1 | **CR1** |
| Code Reviewer 2 | **CR2** |
| Security Analyst | **SA** |
| Quality Engineer | **QE** |
| Test Engineer | **TE** |
| Devil's Advocate | **DA** |

## Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed
- `[!]` Blocked
- `[-]` Skipped / N/A

## Task Count Summary

| Section | Count |
|---------|-------|
| 5.1 Frontend Dependencies | 6 |
| 5.2 CopilotKit Provider Component | 8 |
| 5.3 Sidebar State Store (Zustand) | 14 |
| 5.4 AI Sidebar — Shell & Layout | 8 |
| 5.5 AI Sidebar — Resize & Persistence | 7 |
| 5.6 AI Sidebar — Header & Actions | 8 |
| 5.7 AI Toggle Button | 8 |
| 5.8 Chat Input — Text | 7 |
| 5.9 Chat Input — Image Paste (Ctrl+V) | 7 |
| 5.10 Chat Input — Image Upload (Paperclip) | 6 |
| 5.11 Chat Input — Image Preview & Limits | 9 |
| 5.12 Inline Tool Confirmation Cards | 12 |
| 5.13 Inline Clarification Cards | 11 |
| 5.14 Message Renderer — Markdown | 7 |
| 5.15 Message Renderer — Entity References & Navigation | 9 |
| 5.16 Message Renderer — Tool Execution Cards | 8 |
| 5.17 Message Renderer — Source Citations | 7 |
| 5.18 Citation Click — Navigate & Highlight (Documents) | 8 |
| 5.19 Citation Click — Navigate & Highlight (Canvas) | 7 |
| 5.20 Context Injection (useCopilotReadable) | 9 |
| 5.21 Time Travel / Rewind UI | 11 |
| 5.22 Styles (ai-styles.css) | 9 |
| 5.23 Query Keys | 6 |
| 5.24 Code Reviews & Security Analysis | 8 |
| 5.25 Accessibility Review | 10 |
| 5.26 Manual E2E Verification Scenarios | 23 |
| 5.27 Phase 5 Sign-Off | 5 |
| **TOTAL** | **238** |

---

### 5.1 Frontend Dependencies

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.1.1 | Add `@copilotkit/react-core` (`^1.x`) to `dependencies` in `electron-app/package.json` | FE | [ ] | |
| 5.1.2 | Add `@copilotkit/react-ui` (`^1.x`) to `dependencies` in `electron-app/package.json` | FE | [ ] | |
| 5.1.3 | Run `cd electron-app && npm install` — verify clean install with no peer dependency conflicts | FE | [ ] | |
| 5.1.4 | Verify TypeScript types are available for both `@copilotkit/react-core` and `@copilotkit/react-ui` — check that IDE autocompletion works for `CopilotKit`, `useCopilotReadable`, `CopilotSidebar` | FE | [ ] | |
| 5.1.5 | Run `npm run typecheck` — confirm zero new type errors introduced by CopilotKit packages | FE | [ ] | |
| 5.1.6 | Run `npm run lint` — confirm zero new lint warnings from CopilotKit imports | FE | [ ] | |

---

### 5.2 CopilotKit Provider Component

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.2.1 | Create file `electron-app/src/renderer/components/ai/copilot-provider.tsx` with `CopilotProvider` component shell — accepts `children: React.ReactNode` prop | FE | [ ] | |
| 5.2.2 | Import `CopilotKit` from `@copilotkit/react-core` and render as wrapper around `{children}` | FE | [ ] | |
| 5.2.3 | Configure `runtimeUrl` to point to `/api/copilotkit` endpoint | FE | [ ] | |
| 5.2.4 | Inject auth token from existing `useAuthStore().token` — pass as `Authorization: Bearer <token>` header in CopilotKit's HTTP config | FE | [ ] | |
| 5.2.5 | Configure agent name as `"blair"` in CopilotKit props | FE | [ ] | |
| 5.2.6 | Modify `electron-app/src/renderer/pages/dashboard.tsx` — wrap existing dashboard content in `<CopilotProvider>` | FE | [ ] | |
| 5.2.7 | Verify `CopilotProvider` renders no visible DOM of its own (pure context wrapper) | FE | [ ] | |
| 5.2.8 | Verify auth token refresh and logout flows still work correctly with CopilotKit wrapping — token changes propagate to CopilotKit requests | FE | [ ] | |

---

### 5.3 Sidebar State Store (Zustand)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.3.1 | Create file `electron-app/src/renderer/components/ai/use-ai-sidebar.ts` — define `AiSidebarState` interface with `isOpen: boolean` | FE | [ ] | |
| 5.3.2 | Implement `isOpen` initializer — read from `localStorage.getItem("ai-sidebar-open") === "true"`, default `false` | FE | [ ] | |
| 5.3.3 | Implement `toggle()` method — flip `isOpen`, persist new value to `localStorage` key `"ai-sidebar-open"` | FE | [ ] | |
| 5.3.4 | Implement `open()` method — set `isOpen: true`, persist `"true"` to localStorage | FE | [ ] | |
| 5.3.5 | Implement `close()` method — set `isOpen: false`, persist `"false"` to localStorage | FE | [ ] | |
| 5.3.6 | Implement `resetChat()` method — signal CopilotKit to clear conversation (increment remount key or call CopilotKit reset API), keep sidebar open | FE | [ ] | |
| 5.3.7 | Add `rewindCheckpointId: string | null` field — defaults to `null`, represents active rewind target | FE | [ ] | |
| 5.3.8 | Add `rewindMessageIndex: number | null` field — defaults to `null`, represents which message index to rewind to | FE | [ ] | |
| 5.3.9 | Implement `enterRewindMode(checkpointId: string, messageIndex: number)` method — sets both rewind fields | FE | [ ] | |
| 5.3.10 | Implement `exitRewindMode()` method — clears `rewindCheckpointId` and `rewindMessageIndex` back to `null` | FE | [ ] | |
| 5.3.11 | Verify store is NOT persisted to IndexedDB — chat state is session-only, clears on app close / logout | FE | [ ] | |
| 5.3.12 | Verify only `isOpen` is persisted to localStorage (lightweight preference), not chat content or rewind state | FE | [ ] | |
| 5.3.13 | Export `useAiSidebar` hook for use across components | FE | [ ] | |
| 5.3.14 | **CR1 Review**: Store design — separation of persistent (localStorage) vs. ephemeral (session) state, naming conventions, method signatures | CR1 | [ ] | |

---

### 5.4 AI Sidebar — Shell & Layout

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.4.1 | Create file `electron-app/src/renderer/components/ai/ai-sidebar.tsx` — export `AiSidebar` component | FE | [ ] | |
| 5.4.2 | Conditionally render sidebar based on `useAiSidebar().isOpen` — return `null` when closed | FE | [ ] | |
| 5.4.3 | Position sidebar as a right-side panel within the dashboard layout — use CSS `position: fixed` or flex layout alongside existing content, with `z-index` above main content but below modals | FE | [ ] | |
| 5.4.4 | Set default width to `400px` — apply as inline style or CSS variable | FE | [ ] | |
| 5.4.5 | Integrate CopilotKit's `CopilotSidebar` (or equivalent) as the base — apply custom className for style overrides | FE | [ ] | |
| 5.4.6 | Implement message area with auto-scroll to bottom on new messages — use `scrollIntoView` on a sentinel element at the bottom of the message list | FE | [ ] | |
| 5.4.7 | Implement streaming message display — messages appear token-by-token as they arrive from the AG-UI protocol | FE | [ ] | |
| 5.4.8 | Add `<AiSidebar />` to `dashboard.tsx` inside the `<CopilotProvider>` wrapper (adjacent to existing dashboard content) | FE | [ ] | |

---

### 5.5 AI Sidebar — Resize & Persistence

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.5.1 | Add a drag handle on the left edge of the sidebar — styled as a thin vertical bar (4px wide) with cursor `col-resize` | FE | [ ] | |
| 5.5.2 | Implement pointer-event-based resize logic — `onPointerDown` captures initial X, `onPointerMove` calculates delta, `onPointerUp` finalizes | FE | [ ] | |
| 5.5.3 | Enforce minimum width of `300px` — clamp during drag | FE | [ ] | |
| 5.5.4 | Enforce maximum width of `600px` — clamp during drag | FE | [ ] | |
| 5.5.5 | Persist width to `localStorage` key `"ai-sidebar-width"` — write on drag end (not during drag, to avoid excessive writes) | FE | [ ] | |
| 5.5.6 | Read persisted width from `localStorage` on mount — fall back to `400px` default if no saved value | FE | [ ] | |
| 5.5.7 | Verify main content area adjusts (shrinks) when sidebar width changes — no overlapping or clipping | FE | [ ] | |

---

### 5.6 AI Sidebar — Header & Actions

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.6.1 | Implement sidebar header bar — fixed at top of sidebar, contains title and action buttons | FE | [ ] | |
| 5.6.2 | Add "Blair" title text in the header — use Inter font, `font-semibold`, size matching existing panel headers | FE | [ ] | |
| 5.6.3 | Add "New Chat" button in header — icon + text, ghost variant, calls `useAiSidebar().resetChat()` on click | FE | [ ] | |
| 5.6.4 | Implement `resetChat` behavior — clears conversation history, resets CopilotKit state (force remount via key increment or API), keeps sidebar open | FE | [ ] | |
| 5.6.5 | Add "Close" button (X icon) in header — calls `useAiSidebar().close()` on click | FE | [ ] | |
| 5.6.6 | Layout header as flex row: `[Blair title]` left-aligned, `[New Chat] [Close]` right-aligned | FE | [ ] | |
| 5.6.7 | Add bottom border to header to visually separate from message area | FE | [ ] | |
| 5.6.8 | Verify "New Chat" clears all messages including tool execution cards, confirmation cards, and source citations | FE | [ ] | |

---

### 5.7 AI Toggle Button

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.7.1 | Create file `electron-app/src/renderer/components/ai/ai-toggle-button.tsx` — export `AiToggleButton` component | FE | [ ] | |
| 5.7.2 | Render Radix UI `Button` with `variant="ghost"` and `size="icon"` — contains `Sparkles` icon from `lucide-react` (16x16 / `h-4 w-4`) | FE | [ ] | |
| 5.7.3 | Wire `onClick` to `useAiSidebar().toggle()` | FE | [ ] | |
| 5.7.4 | Apply active state styling when sidebar is open — `bg-accent text-accent-foreground` class via `cn()` utility | FE | [ ] | |
| 5.7.5 | Add tooltip text: `"Blair (Ctrl+Shift+A)"` — use existing Radix Tooltip component or `title` attribute | FE | [ ] | |
| 5.7.6 | Implement global keyboard shortcut `Ctrl+Shift+A` — register `keydown` listener on `window`, call `toggle()`, prevent default | FE | [ ] | |
| 5.7.7 | Place `<AiToggleButton />` in the dashboard header/toolbar area alongside existing toolbar buttons — modify dashboard header component | FE | [ ] | |
| 5.7.8 | Clean up keyboard shortcut listener on component unmount — remove event listener in `useEffect` cleanup | FE | [ ] | |

---

### 5.8 Chat Input — Text

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.8.1 | Implement chat input area at the bottom of the sidebar — `<textarea>` or CopilotKit's built-in input with custom styling | FE | [ ] | |
| 5.8.2 | Add placeholder text: `"Ask Blair anything..."` | FE | [ ] | |
| 5.8.3 | Implement `Enter` key to send message — call CopilotKit's send/submit handler | FE | [ ] | |
| 5.8.4 | Implement `Shift+Enter` for newline — insert newline character without sending | FE | [ ] | |
| 5.8.5 | Auto-resize textarea height based on content — grow up to max 4 lines, then scroll internally | FE | [ ] | |
| 5.8.6 | Add "Send" button (arrow icon) to the right of the input — disabled when input is empty, calls send on click | FE | [ ] | |
| 5.8.7 | Clear input text after successful message send | FE | [ ] | |

---

### 5.9 Chat Input — Image Paste (Ctrl+V)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.9.1 | Listen for `paste` event on the chat input area — attach handler via `onPaste` or `addEventListener` | FE | [ ] | |
| 5.9.2 | Extract image files from `clipboardData.items` — filter items where `type.startsWith("image/")` | FE | [ ] | |
| 5.9.3 | Convert each pasted image `Blob` to base64 string via `FileReader.readAsDataURL()` — strip the `data:image/...;base64,` prefix, store raw base64 | FE | [ ] | |
| 5.9.4 | Extract MIME type from the clipboard item (e.g., `"image/png"`, `"image/jpeg"`) and store as `mediaType` | FE | [ ] | |
| 5.9.5 | Generate a default filename for pasted images: `"pasted-image.png"` (or derive from MIME type) | FE | [ ] | |
| 5.9.6 | Create `PendingImage` object with unique `id` (UUID), `data`, `mediaType`, `filename`, and `previewUrl` (via `URL.createObjectURL()`) | FE | [ ] | |
| 5.9.7 | Append to `pendingImages` state array — check max count before adding (see 5.11) | FE | [ ] | |

---

### 5.10 Chat Input — Image Upload (Paperclip)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.10.1 | Add paperclip icon button (`Paperclip` from lucide-react) to the left of the Send button in the input area | FE | [ ] | |
| 5.10.2 | Render a hidden `<input type="file" accept="image/*" multiple />` element — trigger via `ref.click()` when paperclip button is clicked | FE | [ ] | |
| 5.10.3 | Handle `onChange` event on the file input — iterate over `event.target.files` to process selected images | FE | [ ] | |
| 5.10.4 | Convert each selected `File` to base64 via `FileReader.readAsDataURL()` — strip prefix, store raw base64 | FE | [ ] | |
| 5.10.5 | Create `PendingImage` objects for each file — use `file.name` as `filename`, `file.type` as `mediaType`, generate `previewUrl` via `URL.createObjectURL()` | FE | [ ] | |
| 5.10.6 | Reset the file input `value` to `""` after processing — allows re-selecting the same file | FE | [ ] | |

---

### 5.11 Chat Input — Image Preview & Limits

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.11.1 | Define `PendingImage` interface in component or shared types file — fields: `id: string`, `data: string`, `mediaType: string`, `filename: string`, `previewUrl: string` | FE | [ ] | |
| 5.11.2 | Render image preview area above the input — only visible when `pendingImages.length > 0` | FE | [ ] | |
| 5.11.3 | Display thumbnails as a horizontal row — each 64x64px, `object-fit: cover`, rounded corners | FE | [ ] | |
| 5.11.4 | Add a remove button (X icon) on each thumbnail — clicking removes that image from `pendingImages` by `id`, also revokes its `previewUrl` via `URL.revokeObjectURL()` | FE | [ ] | |
| 5.11.5 | Show overflow indicator when more than 3 images — e.g., `"+2 more..."` text after the 3rd thumbnail | FE | [ ] | |
| 5.11.6 | Enforce maximum 5 images per message — if user pastes/uploads when already at 5, show toast notification: `"Maximum 5 images per message"`, reject the new images | FE | [ ] | |
| 5.11.7 | Enforce maximum 10MB per image — check `file.size` or base64 string length (base64 is ~33% larger than binary), show toast: `"Image exceeds 10MB limit"`, reject oversized files | FE | [ ] | |
| 5.11.8 | On message send — include `images` array (with `data` and `mediaType` per image) in the ChatRequest payload, clear `pendingImages` state, revoke all `previewUrl` object URLs | FE | [ ] | |
| 5.11.9 | On component unmount — revoke all remaining object URLs via `URL.revokeObjectURL()` to prevent memory leaks (useEffect cleanup) | FE | [ ] | |

---

### 5.12 Inline Tool Confirmation Cards

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.12.1 | Create file `electron-app/src/renderer/components/ai/tool-confirmation.tsx` — export `ToolConfirmation` component | FE | [ ] | |
| 5.12.2 | Define `ToolConfirmationProps` interface — `action: { type: string, summary: string, details: Record<string, unknown> }`, `status: "pending" | "approved" | "rejected"`, `onApprove: () => void`, `onReject: () => void` | FE | [ ] | |
| 5.12.3 | Implement card layout — bordered card with icon, action summary heading, detail fields below, and action buttons at the bottom. Render INLINE in chat stream (not a modal) | FE | [ ] | |
| 5.12.4 | Implement detail display for `create_task` action type — show Title, Project, Priority, Assignee fields | FE | [ ] | |
| 5.12.5 | Implement detail display for `update_task_status` action type — show Task Key, current status arrow new status | FE | [ ] | |
| 5.12.6 | Implement detail display for `assign_task` action type — show Task Key, Assignee Name | FE | [ ] | |
| 5.12.7 | Implement detail display for `create_document` action type — show Title, Scope, Folder | FE | [ ] | |
| 5.12.8 | Implement "Approve" button — green/primary style, checkmark icon, calls `onApprove()` which sends `Command(resume={approved: true})` to LangGraph | FE | [ ] | |
| 5.12.9 | Implement "Reject" button — red/destructive style, X icon, calls `onReject()` which sends `Command(resume={approved: false})` to LangGraph | FE | [ ] | |
| 5.12.10 | After user responds, update card visual state — Approved: show green checkmark + "Approved" label; Rejected: show red X + "Cancelled" label; disable both buttons (prevent double-submit) | FE | [ ] | |
| 5.12.11 | Implement keyboard shortcuts for pending confirmation cards — `Enter` key approves, `Escape` key rejects (only when card is focused or most recent pending action) | FE | [ ] | |
| 5.12.12 | Verify pending confirmation persists across sidebar close/reopen — LangGraph checkpoint preserves state, card re-renders in pending state when sidebar reopens | FE | [ ] | |

---

### 5.13 Inline Clarification Cards

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.13.1 | Create file `electron-app/src/renderer/components/ai/clarification-card.tsx` — export `ClarificationCard` component | FE | [ ] | |
| 5.13.2 | Define `ClarificationCardProps` interface — `question: string`, `options: string[] | null`, `context: string | null`, `status: "pending" | "answered"`, `selectedAnswer: string | null`, `onSelectOption: (option: string) => void`, `onSubmitText: (text: string) => void` | FE | [ ] | |
| 5.13.3 | Implement card layout — bordered card with question icon, question text prominently displayed, optional context subtitle below | FE | [ ] | |
| 5.13.4 | Render option buttons as pill-style buttons (rounded, outlined) — display up to max 4 options in a flex-wrap row | FE | [ ] | |
| 5.13.5 | Implement option click behavior — clicking an option immediately calls `onSelectOption(option)` which sends `Command(resume={answer: option})` to LangGraph, no additional confirmation step needed | FE | [ ] | |
| 5.13.6 | Render free-text input below options — always visible (even when options are provided), with placeholder: `"Or type your answer..."` and a "Send" button | FE | [ ] | |
| 5.13.7 | Implement free-text submit — pressing `Enter` in the text input or clicking "Send" calls `onSubmitText(text)` which sends `Command(resume={answer: text})` | FE | [ ] | |
| 5.13.8 | When `options` is `null`, render only the free-text input (no option buttons) | FE | [ ] | |
| 5.13.9 | After answering, update card to read-only state — selected option highlighted with accent background, other options dimmed (opacity 0.4), text input disabled, "Send" button hidden | FE | [ ] | |
| 5.13.10 | Implement INTERRUPT routing logic — in CopilotKit's interrupt handler, check `type` field: `"confirmation"` renders `ToolConfirmation`, `"clarification"` renders `ClarificationCard` | FE | [ ] | |
| 5.13.11 | Verify Blair continues reasoning after receiving clarification response — no dead-end, conversation flow resumes | FE | [ ] | |

---

### 5.14 Message Renderer — Markdown

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.14.1 | Create file `electron-app/src/renderer/components/ai/ai-message-renderer.tsx` — export `AiMessageRenderer` component | FE | [ ] | |
| 5.14.2 | Define `AiMessageProps` interface — `message: { role, content, images?, tool_calls?, sources? }`, `onNavigate: (target: NavigationTarget) => void` | FE | [ ] | |
| 5.14.3 | Implement Markdown rendering for assistant messages — use a lightweight markdown-to-JSX library (e.g., `react-markdown`) or existing pattern. Support: **bold**, *italic*, `inline code`, headings | FE | [ ] | |
| 5.14.4 | Implement code block rendering — syntax-highlighted fenced code blocks with language label and copy-to-clipboard button | FE | [ ] | |
| 5.14.5 | Implement table rendering — Markdown tables render as styled `<table>` elements matching PM Desktop design | FE | [ ] | |
| 5.14.6 | Implement list rendering — ordered and unordered lists with proper nesting and indentation | FE | [ ] | |
| 5.14.7 | Render user messages with simpler styling — right-aligned bubble, no markdown processing needed (or minimal), display attached image thumbnails inline above text | FE | [ ] | |

---

### 5.15 Message Renderer — Entity References & Navigation

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.15.1 | Define `NavigationTarget` type — union of `{ type: "task", taskId: string, projectId: string }`, `{ type: "document", documentId: string, highlight?: HighlightParams }`, `{ type: "project", projectId: string, applicationId: string }` | FE | [ ] | |
| 5.15.2 | Implement task key detection in message content — regex pattern for `[A-Z]+-\d+` (e.g., `PROJ-12`), wrap matches in clickable `<span>` elements | FE | [ ] | |
| 5.15.3 | Implement task key click handler — call `onNavigate({ type: "task", taskId, projectId })` using state-based routing (NOT URL navigation) | FE | [ ] | |
| 5.15.4 | Implement document title detection — match document titles from source citations or structured references in message content, render as clickable links | FE | [ ] | |
| 5.15.5 | Implement document title click handler — call `onNavigate({ type: "document", documentId })` to open document in knowledge base | FE | [ ] | |
| 5.15.6 | Implement project name detection — match project names from context or structured references, render as clickable links | FE | [ ] | |
| 5.15.7 | Implement project name click handler — call `onNavigate({ type: "project", projectId, applicationId })` to open project board | FE | [ ] | |
| 5.15.8 | Style clickable entity references — underline, accent color, hover cursor pointer, distinguish from regular markdown links | FE | [ ] | |
| 5.15.9 | Verify all navigation uses state-based routing callbacks (not URL changes or react-router) — consistent with PM Desktop architecture | FE | [ ] | |

---

### 5.16 Message Renderer — Tool Execution Cards

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.16.1 | Create file `electron-app/src/renderer/components/ai/tool-execution-card.tsx` — export `ToolExecutionCard` component | FE | [ ] | |
| 5.16.2 | Define `ToolCallInfo` interface — `name: string`, `status: "executing" | "completed" | "error"`, `summary: string`, `details?: Record<string, unknown>`, `error?: string` | FE | [ ] | |
| 5.16.3 | Implement "Executing" state — animated spinner icon + tool name text (e.g., "Searching knowledge..."), subtle background | FE | [ ] | |
| 5.16.4 | Implement "Completed" state — green checkmark icon + tool name + one-line result summary (e.g., "Found 5 results"). Card is collapsed by default | FE | [ ] | |
| 5.16.5 | Implement collapsible expanded section for completed state — click to expand/collapse, shows detailed results (e.g., list of found documents with scores) | FE | [ ] | |
| 5.16.6 | Implement "Error" state — red X icon + tool name + error message (e.g., "Rate limit exceeded"), styled distinctly with red/warning colors | FE | [ ] | |
| 5.16.7 | Render tool execution cards inline in the message stream — between Blair's reasoning text, positioned as part of the conversation flow | FE | [ ] | |
| 5.16.8 | Map tool names to human-readable labels and icons — e.g., `search_knowledge` -> "Searched knowledge base" with search icon, `get_project_status` -> "Checked project status" with chart icon | FE | [ ] | |

---

### 5.17 Message Renderer — Source Citations

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.17.1 | Define `SourceCitation` interface — `documentId: string`, `documentTitle: string`, `section: string`, `score: number`, `sourceType: "semantic" | "keyword" | "fuzzy" | "graph"`, `headingContext?: string`, `chunkText?: string`, `chunkIndex?: number`, `elementId?: string` | FE | [ ] | |
| 5.17.2 | Render source citations at the bottom of assistant messages that include sources — section header "Sources:" with document icon | FE | [ ] | |
| 5.17.3 | Display each citation as a clickable row — document title, section name, relevance score (formatted as percentage or decimal), source type badge | FE | [ ] | |
| 5.17.4 | Style source type badges — color-coded pills: semantic (blue), keyword (green), fuzzy (yellow), graph (purple) | FE | [ ] | |
| 5.17.5 | Implement citation click handler — call `onNavigate({ type: "document", documentId, highlight: { headingContext, chunkText, chunkIndex, elementId } })` | FE | [ ] | |
| 5.17.6 | Display user-sent image thumbnails in user messages — small inline thumbnails (48x48) with rounded corners, clickable to open full-size in a lightbox/modal | FE | [ ] | |
| 5.17.7 | Render alt text for image thumbnails — use `filename` or `"Attached image"` as alt attribute for accessibility | FE | [ ] | |

---

### 5.18 Citation Click — Navigate & Highlight (Documents)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.18.1 | Define `HighlightParams` interface — `headingContext?: string`, `chunkText?: string`, `chunkIndex?: number`, `elementId?: string` | FE | [ ] | |
| 5.18.2 | Implement `findHeadingPosition(editor, headingContext)` utility — traverse TipTap editor document tree, find heading node whose text matches `headingContext`, return its position | FE | [ ] | |
| 5.18.3 | Implement heading scroll — when heading is found, get its DOM node via `editor.view.nodeDOM(pos)`, call `scrollIntoView({ behavior: "smooth", block: "center" })` | FE | [ ] | |
| 5.18.4 | Implement `findTextInDocument(editor, chunkText)` utility — search editor content for the cited text, return `{ from, to }` position range | FE | [ ] | |
| 5.18.5 | Implement `applyTemporaryHighlight(editor, from, to, options)` — apply a TipTap decoration with class `"blair-citation-highlight"`, set a `setTimeout` to add `"fading"` class after 3s, remove decoration after 4s total | FE | [ ] | |
| 5.18.6 | Add CSS for `.blair-citation-highlight` — `background-color: rgba(250, 204, 21, 0.4)` (yellow-400/40%), `border-radius: 2px`, `transition: background-color 1s ease-out` | FE | [ ] | |
| 5.18.7 | Add CSS for `.blair-citation-highlight.fading` — `background-color: transparent` (triggers the fade-out transition) | FE | [ ] | |
| 5.18.8 | Integrate highlight logic in document editor — `useEffect` watches for incoming highlight params from navigation, triggers scroll + highlight sequence | FE | [ ] | |

---

### 5.19 Citation Click — Navigate & Highlight (Canvas)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.19.1 | Implement canvas element lookup — when `highlight.elementId` is present, call `canvasRef.current.getElement(elementId)` to find the canvas element | FE | [ ] | |
| 5.19.2 | Implement canvas pan-to-element — call `canvasRef.current.centerOnElement(elementId, { animate: true })` to smoothly pan the viewport to center on the element | FE | [ ] | |
| 5.19.3 | Implement canvas element highlight ring — call `canvasRef.current.highlightElement(elementId, { color: "rgba(250, 204, 21, 0.6)", duration: 4000 })` to apply a temporary yellow glow/ring | FE | [ ] | |
| 5.19.4 | If `highlight.chunkText` is also present for a canvas element, flash the text content within the element temporarily | FE | [ ] | |
| 5.19.5 | Implement fallback for missing elements — if `elementId` is not found in the canvas (element was deleted), show a toast: `"Referenced element no longer exists"` | FE | [ ] | |
| 5.19.6 | Integrate canvas highlight logic — `useEffect` in canvas viewer watches for incoming highlight params, triggers pan + highlight sequence | FE | [ ] | |
| 5.19.7 | Verify canvas highlight works for different element types — text boxes, shapes, containers, draw.io diagrams | FE | [ ] | |

---

### 5.20 Context Injection (useCopilotReadable)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.20.1 | Add `useCopilotReadable` in `pages/projects/[id].tsx` — inject currently viewed project context: `projectName`, `projectId`, `applicationName`, `taskCount`, `statusDistribution` | FE | [ ] | |
| 5.20.2 | Add `useCopilotReadable` in `components/knowledge/document-editor.tsx` — inject currently viewed document context: `documentId`, `documentTitle`, `documentType`, `scope`, `folderPath`, `contentPreview` (first 500 chars of text) | FE | [ ] | |
| 5.20.3 | Implement `extractTextPreview(content, maxLength)` utility — extract plain text from TipTap JSON, truncate to `maxLength` characters | FE | [ ] | |
| 5.20.4 | Add `useCopilotReadable` in canvas viewer component — inject canvas context: `documentId`, `documentTitle`, `documentType: "canvas"`, `scope`, `elementCount`, `elementSummary` (summary of element types and key text, max 500 chars) | FE | [ ] | |
| 5.20.5 | Implement `summarizeCanvasElements(elements, maxLength)` utility — produce a text summary of canvas element types and key content | FE | [ ] | |
| 5.20.6 | Add `useCopilotReadable` in `pages/applications/[id].tsx` — inject currently viewed application context: `applicationName`, `applicationId`, `projectCount`, `memberCount` | FE | [ ] | |
| 5.20.7 | Verify context updates when user navigates between screens — `useCopilotReadable` re-evaluates on prop changes | FE | [ ] | |
| 5.20.8 | Verify context is removed when component unmounts (state-based routing causes unmount on screen switch) — no stale context lingers in CopilotKit | FE | [ ] | |
| 5.20.9 | Verify no performance impact — `useCopilotReadable` is lightweight, content preview is truncated (not full document in context) | FE | [ ] | |

---

### 5.21 Time Travel / Rewind UI

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.21.1 | Add rewind icon (`RotateCcw` from lucide-react) to Blair's message bubbles — appears on hover in the top-right corner of the message, hidden by default | FE | [ ] | |
| 5.21.2 | Rewind icon appears ONLY on Blair's messages (not user messages) — conditional render based on `message.role === "assistant"` | FE | [ ] | |
| 5.21.3 | Implement rewind icon click handler — calls `useAiSidebar().enterRewindMode(checkpointId, messageIndex)` where `checkpointId` is the LangGraph checkpoint associated with that message | FE | [ ] | |
| 5.21.4 | Implement visual dimming of messages after the rewind point — all messages with index > `rewindMessageIndex` get `opacity: 0.3` and `text-decoration: line-through` styling | FE | [ ] | |
| 5.21.5 | Dimmed messages become non-interactive — no rewind icons, no clickable links, no expandable tool cards, pointer-events disabled | FE | [ ] | |
| 5.21.6 | Render rewind banner above the chat input — text: `"Rewound to: \"<truncated message>...\""`, subtext: `"Type a new message to branch from this point."`, and a `[Cancel]` button | FE | [ ] | |
| 5.21.7 | Focus the chat input when entering rewind mode — user can immediately start typing a new message | FE | [ ] | |
| 5.21.8 | On new message send in rewind mode — `POST /api/ai/chat/replay` with `{ checkpoint_id: rewindCheckpointId, message: newMessage }`, remove dimmed messages from UI, exit rewind mode, continue conversation from the new branch | FE | [ ] | |
| 5.21.9 | Implement Cancel button in rewind banner — calls `useAiSidebar().exitRewindMode()`, restores full conversation to its latest state (un-dim all messages), removes rewind banner | FE | [ ] | |
| 5.21.10 | If user has a pending HITL confirmation (approve/reject card) and rewinds past that point — cancel the pending confirmation, remove the card from the dimmed section | FE | [ ] | |
| 5.21.11 | "New Chat" always overrides rewind mode — if user clicks "New Chat" while in rewind mode, exit rewind mode and clear all history (full reset) | FE | [ ] | |

---

### 5.22 Styles (ai-styles.css)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.22.1 | Create file `electron-app/src/renderer/components/ai/ai-styles.css` | FE | [ ] | |
| 5.22.2 | Override CopilotKit sidebar background color — match PM Desktop app background using CSS variables (`--background`, `--card`, etc.) | FE | [ ] | |
| 5.22.3 | Override CopilotKit message bubble styles — match PM Desktop card style (border-radius, padding, shadow) | FE | [ ] | |
| 5.22.4 | Override CopilotKit input field styles — match existing `<Input>` component (border, focus ring, padding) | FE | [ ] | |
| 5.22.5 | Override CopilotKit send button styles — match existing Radix UI button (colors, hover states) | FE | [ ] | |
| 5.22.6 | Override CopilotKit scrollbar styles — match existing `<ScrollArea>` component appearance | FE | [ ] | |
| 5.22.7 | Set font family to Inter (match app font) — apply to all CopilotKit elements | FE | [ ] | |
| 5.22.8 | Ensure all color overrides use CSS variables from the theme — dark mode compatible (if app supports dark mode, sidebar inherits) | FE | [ ] | |
| 5.22.9 | Import `ai-styles.css` in `ai-sidebar.tsx` (or in the main app styles entry point) | FE | [ ] | |

---

### 5.23 Query Keys

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.23.1 | Add `aiConfig: ['ai', 'config'] as const` query key to `electron-app/src/renderer/lib/query-client.ts` | FE | [ ] | |
| 5.23.2 | Add `aiProviders: ['ai', 'providers'] as const` query key | FE | [ ] | |
| 5.23.3 | Add `aiModels: ['ai', 'models'] as const` query key | FE | [ ] | |
| 5.23.4 | Add `importJob: (jobId: string) => ['ai', 'import', jobId] as const` parameterized query key | FE | [ ] | |
| 5.23.5 | Add `importJobs: ['ai', 'import', 'jobs'] as const` query key | FE | [ ] | |
| 5.23.6 | Add `documentIndexStatus: (docId: string) => ['ai', 'index-status', docId] as const` and `applicationIndexStatus: (appId: string) => ['ai', 'index-status', 'application', appId] as const` and `indexProgress: ['ai', 'index-progress'] as const` query keys | FE | [ ] | |

---

### 5.24 Code Reviews & Security Analysis

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.24.1 | **CR1 Review**: `copilot-provider.tsx` — auth token injection, runtimeUrl config, CopilotKit wrapper correctness | CR1 | [ ] | |
| 5.24.2 | **CR1 Review**: `ai-sidebar.tsx` — layout, resize logic, scroll behavior, conditional rendering | CR1 | [ ] | |
| 5.24.3 | **CR2 Review**: `tool-confirmation.tsx` and `clarification-card.tsx` — INTERRUPT handling, Command resume payloads, state transitions (pending -> approved/rejected/answered) | CR2 | [ ] | |
| 5.24.4 | **CR2 Review**: `ai-message-renderer.tsx` — markdown rendering, entity reference detection, navigation handler correctness | CR2 | [ ] | |
| 5.24.5 | **SA Review**: Auth token handling — token not leaked in logs, not stored in component state beyond CopilotKit needs, no XSS vectors in message rendering | SA | [ ] | |
| 5.24.6 | **SA Review**: Image handling — base64 data not persisted beyond session, object URLs properly revoked, no exfiltration vectors, file size limits enforced client-side AND server-side | SA | [ ] | |
| 5.24.7 | **SA Review**: Markdown rendering — sanitized against XSS (no raw `dangerouslySetInnerHTML` with user-controlled content), script injection in code blocks prevented | SA | [ ] | |
| 5.24.8 | **DA Challenge**: What happens if the CopilotKit connection drops mid-stream? What if the agent hangs on a tool call? What if a user sends 100 messages rapidly? Rate limiting? Graceful degradation? | DA | [ ] | |

---

### 5.25 Accessibility Review

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.25.1 | **AI Sidebar**: Verify sidebar has `role="complementary"` and `aria-label="AI Assistant"`, close button has `aria-label="Close AI sidebar"` | QE | [ ] | |
| 5.25.2 | **AI Toggle Button**: Verify button has `aria-label="Toggle AI assistant"`, `aria-pressed` attribute reflects open/close state, tooltip accessible via `aria-describedby` | QE | [ ] | |
| 5.25.3 | **Chat Input**: Verify textarea has `aria-label="Chat message"`, Send button has `aria-label="Send message"`, paperclip button has `aria-label="Attach image"` | QE | [ ] | |
| 5.25.4 | **Tool Confirmation Cards**: Verify card has `role="alert"` or `role="region"` with `aria-label`, Approve/Reject buttons have descriptive `aria-label` (e.g., `"Approve creating task Fix login bug"`), focus trap when card is pending | QE | [ ] | |
| 5.25.5 | **Clarification Cards**: Verify question is announced by screen reader, option buttons have `role="option"` or `role="button"` with labels, free-text input has `aria-label` | QE | [ ] | |
| 5.25.6 | **Message Renderer**: Verify messages use `role="log"` or `aria-live="polite"` for streaming updates, code blocks have `role="code"`, source citations have descriptive link text (not "click here") | QE | [ ] | |
| 5.25.7 | **Keyboard Navigation**: Verify full keyboard navigation — Tab through sidebar elements (header buttons, messages, input), Enter/Escape for confirmation cards, Ctrl+Shift+A toggle | QE | [ ] | |
| 5.25.8 | **Focus Management**: Verify focus moves to input when sidebar opens, focus returns to toggle button when sidebar closes, focus moves to rewind banner when entering rewind mode | QE | [ ] | |
| 5.25.9 | **Image Previews**: Verify thumbnails have `alt` text (filename or "Attached image"), remove buttons have `aria-label="Remove image <filename>"` | QE | [ ] | |
| 5.25.10 | **Rewind UI**: Verify rewind banner is announced by screen reader, dimmed messages have `aria-hidden="true"`, Cancel button is keyboard accessible | QE | [ ] | |

---

### 5.26 Manual E2E Verification Scenarios

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.26.1 | **V1**: Open app, click Blair toggle button in header — verify sidebar opens on the right side | QE | [ ] | |
| 5.26.2 | **V2**: Type "What projects do I have?" — verify streaming response with project list, tool execution card shows "Searched projects" with result count | QE | [ ] | |
| 5.26.3 | **V3**: Type "Tell me about the payment system" — verify knowledge base search (tool card: "Searching knowledge..."), response includes source reference links with document title, section, score, and source type badge (semantic/keyword/fuzzy/graph). Click a source link — verify navigation to document, scroll to heading, yellow text highlight that fades after 4s | QE | [ ] | |
| 5.26.4 | **V4**: Type "Create a task called 'Test Blair' in Project X" — verify inline confirmation card appears IN the chat stream (NOT a modal), shows action type, title, project details. Click "Approve" — verify card updates to "Approved", Blair confirms task creation | QE | [ ] | |
| 5.26.5 | **V5**: Navigate to a project board, then ask "What's the status of this project?" — verify Blair uses context injection (knows which project without being told) | QE | [ ] | |
| 5.26.6 | **V6**: Navigate to a document, ask "Summarize this document" — verify Blair uses context injection, returns summary with source references. Click source link — verify scroll within same document to cited section with text highlight | QE | [ ] | |
| 5.26.7 | **V7**: Navigate to a canvas document, ask "What's on this canvas?" — verify Blair summarizes canvas elements, source references include canvas element IDs. Click source — verify canvas pans to element and highlights it | QE | [ ] | |
| 5.26.8 | **V8**: Close sidebar, navigate to different screen, reopen — verify chat history preserved (session-only Zustand), any pending HITL confirmation still shows (LangGraph checkpoint) | QE | [ ] | |
| 5.26.9 | **V9**: Click "New Chat" — verify conversation cleared, sidebar stays open | QE | [ ] | |
| 5.26.10 | **V10**: Resize sidebar by dragging left edge — verify width changes smoothly, respects min/max bounds (300px-600px), width persisted on next open | QE | [ ] | |
| 5.26.11 | **V11**: Close app, reopen — verify chat history is gone (session-only), sidebar open/close state is preserved (localStorage) | QE | [ ] | |
| 5.26.12 | **V12**: Press Ctrl+Shift+A — verify Blair sidebar toggles open/closed | QE | [ ] | |
| 5.26.13 | **V13**: Copy an image to clipboard, paste in chat input (Ctrl+V) — verify image thumbnail appears above input area | QE | [ ] | |
| 5.26.14 | **V14**: Click attachment (paperclip) button, select image file — verify image thumbnail appears above input area | QE | [ ] | |
| 5.26.15 | **V15**: Send message with attached image: "What does this diagram show?" — verify AI describes the image content accurately | QE | [ ] | |
| 5.26.16 | **V16**: Send message with 2+ images: "Compare these two screenshots" — verify AI analyzes and compares both images | QE | [ ] | |
| 5.26.17 | **V17**: Try pasting a 6th image (when 5 already attached) — verify toast notification: "Maximum 5 images per message" | QE | [ ] | |
| 5.26.18 | **V18**: Type a vague request: "Show me the project status" (when user has multiple projects) — verify Blair shows inline clarification card with project options as buttons. Click a project button — verify Blair continues with that project's status | QE | [ ] | |
| 5.26.19 | **V19**: Type "Tell me about the auth flow" (ambiguous topic) — if Blair finds limited results, verify clarification card with options. Type a custom answer in free-text input — verify Blair uses it to refine search | QE | [ ] | |
| 5.26.20 | **V20**: After answering a clarification, verify the card becomes read-only — selected option highlighted, other options dimmed, input disabled | QE | [ ] | |
| 5.26.21 | **V21**: Hover over a Blair response — verify rewind icon appears in top-right corner. Click rewind icon on an earlier message — verify messages after that point become dimmed with strikethrough, rewind banner appears above input with "Rewound to: ...", chat input is active and focused | QE | [ ] | |
| 5.26.22 | **V22**: Type a new message in rewind mode — verify Blair responds from the rewound state (old branch removed), dimmed messages disappear, conversation continues from new branch | QE | [ ] | |
| 5.26.23 | **V23**: Enter rewind mode, then click Cancel — verify full conversation restores to latest state, rewind mode exits cleanly | QE | [ ] | |

---

### 5.27 Phase 5 Sign-Off

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 5.27.1 | All new components pass `npm run typecheck` with zero errors | QE | [ ] | |
| 5.27.2 | All new components pass `npm run lint` with zero warnings (ESLint zero warnings policy) | QE | [ ] | |
| 5.27.3 | All 23 manual E2E verification scenarios pass (section 5.26) | QE | [ ] | |
| 5.27.4 | **DA Final Challenge**: What is the sidebar's impact on dashboard render performance? What happens with 500+ messages in a single conversation? Memory leak audit for object URLs and event listeners. What if CopilotKit releases a breaking v2 — how coupled are we? | DA | [ ] | |
| 5.27.5 | Phase 5 APPROVED — all reviewers (CR1, CR2, SA, QE, DA) sign off | ALL | [ ] | |
