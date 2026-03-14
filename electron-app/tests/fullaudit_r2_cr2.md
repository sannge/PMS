# Round 2 -- Frontend Code Review (CR2)

## Verdict: NEEDS FIXES
One HIGH finding (incomplete C1 fix) prevents SHIP IT status.

## Summary
The R1 CRITICAL and HIGH findings have all been addressed, and most fixes are correct and well-implemented. The message array cap (200), the `editableRef` pattern in CanvasEditor, the shared `useImageUpload` hook, the `useCallback`-wrapped `select` in `useDocuments`, the `StatusDot`/`StatusBadge` component split, the `clearEventDedup` logout integration, and the `maxLength` on canvas title are all solid. However, the C1 base64 memory fix is incomplete: it strips the `data` property but leaves the `previewUrl` data URL (which contains an identical copy of the base64 payload), so only ~50% of the memory is freed. This is upgraded from the R1 CRITICAL to HIGH because the fix does halve the leak, but it still retains up to 25 MB per message in `previewUrl` strings. No regressions were found in the other fixes.

## Statistics
- CRITICAL: 0
- HIGH: 1
- MEDIUM: 1
- LOW: 0
- INFO: 2

---

## R1 Fix Verification

### CR2-R1-01 (CRITICAL): Base64 image data retained in AI sidebar store -- PARTIALLY FIXED
- **File**: `use-ai-chat.ts:333-340`, `types.ts:63-64`
- **What was done**: Added `StoredImage` type (`Omit<PendingImage, 'data'> & { data?: undefined }`), added `updateMessage` action to the store, and after `processSSEStream` resolves, calls `updateMessage(userMsg.id, ...)` to set `data: undefined` on each image.
- **What's still wrong**: See CR2-R2-01 below. The `previewUrl` at line 269 is constructed as `\`data:${img.mediaType};base64,${img.data}\`` -- a data URL containing the full base64 payload. After the fix strips `data`, the `previewUrl` string still retains an identical-sized copy of the base64 data. Only one of two copies is freed.
- **Status**: PARTIALLY FIXED -- demoted from CRITICAL to HIGH.

### CR2-R1-02 (HIGH): AI sidebar message array grows without bound -- FIXED
- **File**: `use-ai-sidebar.ts:127-129`
- **What was done**: `addMessage` now caps at 200 entries: `setState({ messages: newMessages.length > 200 ? newMessages.slice(-200) : newMessages })`.
- **Verification**: Correct. When `newMessages.length <= 200`, the original array is used without slicing (no unnecessary allocation). When over 200, `slice(-200)` keeps the most recent entries. The cap aligns with the backend conversation history cap of 50 and provides ample room for tool calls and multi-turn conversations.
- **Status**: FIXED.

### CR2-R1-03 (HIGH): Stale closure in CanvasEditor `handleWidthChange` -- FIXED
- **File**: `canvas-editor.tsx:76-77, 139`
- **What was done**: Added `editableRef` with a `useEffect` to keep it current (line 76-77). Changed `handleWidthChange` to check `editableRef.current` instead of the closure-captured `editable` (line 139).
- **Verification**: Correct. The ref is updated synchronously in an effect with `[editable]` dependency. The `handleWidthChange` callback now reads `editableRef.current` inside the closure, which is always the latest value regardless of when the ResizeObserver fires. The race condition between view-to-edit transitions is eliminated.
- **Status**: FIXED.

### CR2-R1-04 (MEDIUM): DocumentStatusBadge creates mutation on every render -- FIXED
- **File**: `document-status-badge.tsx:94-146, 152-262, 268-278`
- **What was done**: Split into three components: `StatusDot` (lightweight dot variant), `StatusBadge` (full popover with `useDocumentIndexStatus` + `useSyncDocumentEmbeddings`), and `DocumentStatusBadge` (delegates by variant).
- **Verification**: Correct. `StatusDot` still calls `useSyncDocumentEmbeddings()` (line 99), but this is intentional -- the dot variant supports click-to-sync for stale documents. The key improvement is that `StatusDot` does NOT call `useDocumentIndexStatus` (the heavier query hook), which was the main concern. The `StatusBadge` variant owns both hooks. This is the right split.
- **Status**: FIXED.

### CR2-R1-05 (MEDIUM): useDocuments `select` runs sort on every render -- FIXED
- **File**: `use-documents.ts:171-179`
- **What was done**: Wrapped the `select` function in `useCallback` with `[]` dependency array, creating a stable reference.
- **Verification**: Correct. TanStack Query's `select` memoization now works properly -- it will skip re-computation when input data is referentially stable because the selector function itself is now stable. The `[]` dependency is correct since the sort comparator is pure and has no external dependencies.
- **Status**: FIXED.

### CR2-R1-06 (MEDIUM): useAiSidebar full-state mode creates new merged object on every state change -- NOT FIXED (accepted)
- **File**: `ai-sidebar.tsx:78-90`
- **Observation**: `AiSidebar` still uses `useAiSidebar()` with full-state destructuring. However, `useAiChat` (line 228-233) now uses individual selectors (`useAiSidebar(s => s.threadId)`, etc.), and `AiToggleButton` (line 14-15) uses individual selectors. The `AiSidebar` component needs `messages`, `isStreaming`, `chatKey`, `threadId`, `rewindMessageIndex`, `rewindCheckpointId`, plus 4 actions -- it uses 10 of 14 fields. Converting to individual selectors would require 10+ hook calls with negligible benefit since this component already re-renders on most state changes. This is acceptable.
- **Status**: ACCEPTED as-is. The fix was correctly applied where it matters (`useAiChat`, `AiToggleButton`).

### CR2-R1-07 (MEDIUM): useWebSocketCacheInvalidation options effect runs every render -- NOT VERIFIED
- **Observation**: The team-lead's instructions did not list `use-websocket-cache.ts` options memoization as a fix target. The R1 recommendation was to memoize the `options` object at the call site in `dashboard.tsx`. This was a minor concern (ref assignment cost is negligible). Not re-audited as it was not in scope.
- **Status**: LOW priority, not blocking.

### CR2-R1-08 (MEDIUM): Duplicated image upload logic -- FIXED
- **File**: `use-image-upload.ts` (NEW), `document-editor.tsx:93`, `canvas-editor.tsx:221`
- **What was done**: Extracted `useImageUpload(token, documentId)` hook that both editors now consume. Handles file validation (type + size), upload to `/api/files/upload`, download URL retrieval, and toast notifications.
- **Verification**: Correct. Both `DocumentEditor` (line 93) and `CanvasEditor` (line 221) call `useImageUpload`. The hook uses `useCallback` with `[token, documentId]` dependencies. The `CanvasEditor` wraps it further in `uploadImage` for toolbar use (line 224-233), while `DocumentEditor` uses it directly via `uploadImageRef` for paste/drop handlers.
- **Status**: FIXED.

### CR2-R1-09 (LOW): useDocumentLock keep-refs effect has no dep array -- NOT VERIFIED
- Not in scope for R2. LOW severity, no functional issue.

### CR2-R1-10 (LOW): Module-level dedup state shared across instances -- NOT VERIFIED
- Not in scope for R2. LOW severity, no current issue.

### CR2-R1-11 (LOW): Missing FolderTreeItem memoization -- NOT FIXED
- **File**: `folder-tree-item.tsx:95`
- **Observation**: `FolderTreeItem` is still exported as a regular function component, not wrapped in `React.memo`. The `memo` import is present (line 15) but not applied to `FolderTreeItem`. LOW severity, no regression.
- **Status**: NOT FIXED, remains LOW.

### CR2-R1-12 (LOW): clearEventDedup exported but never called -- FIXED
- **File**: `App.tsx:25, 283`
- **What was done**: `clearEventDedup` is now imported in `App.tsx` and called alongside `clearQueryCache()` during logout.
- **Verification**: Correct. This ensures stale fingerprints don't persist across user sessions.
- **Status**: FIXED.

### Additional R2 fixes verified:
- **M5 (dedup threshold)**: `DEDUP_CLEANUP_THRESHOLD` changed from 50 to 20 in `use-websocket-cache.ts:116`. Correct -- more aggressive cleanup for a map that rarely exceeds a few entries.
- **M6 (crypto.randomUUID)**: `use-documents.ts:329` now uses `crypto.randomUUID()` instead of `Math.random()`. Correct.
- **M7 (limit=200)**: `use-documents.ts:200` now sends `limit=200`. Correct -- previously used the default server limit.
- **M8 (maxLength)**: `canvas-editor.tsx:254` has `maxLength={255}` on the title input. Correct -- prevents exceeding DB column limit.
- **H3 (DOMPurify)**: `task-detail.tsx:24,1101` uses `DOMPurify.sanitize()` with `FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form']`. Correct -- prevents XSS in task description HTML rendering.

---

## New Findings

### [CR2-R2-01] HIGH -- Base64 data still retained in previewUrl data URL after C1 strip
- **File**: `electron-app/src/renderer/components/ai/use-ai-chat.ts:269, 335-339`
- **Issue**: The C1 fix strips `img.data` (the raw base64 string) from the stored message after the fetch completes. However, the `previewUrl` is constructed at line 269 as `\`data:${img.mediaType};base64,${img.data}\`` -- an inline data URL that contains the entire base64 payload as a substring. After the fix sets `data: undefined`, the `previewUrl` string still holds a copy of the base64 data (~10 MB per image). The JavaScript engine cannot garbage-collect the base64 data because it is still referenced by the `previewUrl` string.
- **Impact**: Instead of freeing ~50 MB per 5-image message, only ~25 MB is freed (the `data` properties). The remaining ~25 MB persists in the `previewUrl` strings for the lifetime of the message in the store. For multiple image-heavy messages, this still causes significant memory pressure, though it is halved compared to R1.
- **Recommendation**: When stripping the base64 data, also replace the `previewUrl` with a small thumbnail. Two approaches:
  1. **Canvas thumbnail**: Before stripping, generate a small thumbnail via `<canvas>` (e.g., 200x200 max, quality 0.6) and replace `previewUrl` with the resulting small data URL (~5-20 KB).
  2. **Use object URL from chat-input**: In `chat-input.tsx:57`, `processImageFile` already creates a proper `URL.createObjectURL(file)` blob URL (just a short pointer string). If this blob URL were passed through to the store message instead of constructing a new data URL at line 269, the `previewUrl` would be tiny and the full base64 data could be stripped completely. Note: object URLs are revoked on send (`chat-input.tsx:130`), so this approach requires keeping the blob URL alive until the C1 strip runs.

### [CR2-R2-02] MEDIUM -- AiSidebar still uses full-state `useAiSidebar()` causing unnecessary re-renders
- **File**: `electron-app/src/renderer/components/ai/ai-sidebar.tsx:78-90`
- **Issue**: As noted in CR2-R1-06 verification, `AiSidebar` uses the no-selector form of `useAiSidebar()`. While this component does use 10 of 14 fields, it still re-renders on ANY state change, including `threadId` changes (which don't affect the UI) and `isOpen` changes (already guarded by the early return at line 181). More importantly, during streaming, every `text_delta` event triggers `updateLastAssistantMessage`, which calls `setState`, which creates a new `state` object, which causes `getSelectedSnapshot` to return a new merged object (since `data === last.data` is false), which triggers a full re-render of `AiSidebar`. The message list is iterated and `AiMessageRenderer` memo boundaries are evaluated for every delta.
- **Impact**: During a typical streaming response with 200+ text_delta events, `AiSidebar` re-renders 200+ times. Each re-render iterates the full message list and evaluates memo boundaries. While `AiMessageRenderer` is `React.memo`'d (so unchanged messages skip rendering), the iteration and memo comparison work is O(messages * deltas). For a chat with 100 messages and 200 deltas per response, that is 20,000 memo checks per response.
- **Recommendation**: Use a `messages` selector and let the `AiMessageRenderer` memo handle the rest, or virtualize the message list with a library like `react-virtuoso` to avoid iterating off-screen messages.

---

### [CR2-R2-03] INFO -- Positive: updateMessage action is a clean, reusable primitive
- **File**: `use-ai-sidebar.ts:131-134`
- **Observation**: The new `updateMessage(id, updater)` action is well-designed -- it accepts an updater function (not a partial), allowing atomic, type-safe transformations of individual messages. This pattern is more flexible than `updateLastAssistantMessage` and could be used for future features (e.g., editing a sent message, adding reactions).

### [CR2-R2-04] INFO -- Positive: useImageUpload hook is well-structured
- **File**: `use-image-upload.ts:1-75`
- **Observation**: The extracted hook properly handles all edge cases: null token, invalid file type, oversized file, upload failure, and download URL retrieval. Error handling uses toast notifications consistently. The `useCallback` dependency array `[token, documentId]` is correct. Both consumers (`DocumentEditor`, `CanvasEditor`) integrate cleanly.
