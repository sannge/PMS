# Round 1 -- Frontend Code Review (CR2)

## Verdict: NEEDS FIXES
One CRITICAL and two HIGH findings prevent SHIP IT status.

## Summary
The frontend codebase is well-structured with strong TanStack Query patterns, comprehensive WebSocket integration, and disciplined cache invalidation. The knowledge base feature demonstrates solid architecture: per-query IndexedDB persistence with LRU eviction, progressive hydration, batch lock queries (eliminating N+1), and a well-designed edit-mode state machine. However, there is a critical memory leak in the AI chat's base64 image handling, a high-severity issue with unbounded message array growth in the AI sidebar store, and a high-severity stale closure in the CanvasEditor that can cause state loss. The remaining findings are medium and low severity -- mostly missed memoization opportunities, minor cleanup omissions, and one dead-code path.

## Statistics
- CRITICAL: 1
- HIGH: 2
- MEDIUM: 5
- LOW: 4
- INFO: 3

---

## Findings

### [CR2-R1-01] CRITICAL -- Base64 image data retained in AI sidebar store indefinitely
- **File**: `electron-app/src/renderer/components/ai/use-ai-chat.ts:261-272`
- **Issue**: When a user sends a message with images, the full base64 `data` field (up to 10 MB per image, 5 images max = 50 MB per message) is embedded into the `ChatMessage` object and stored in the `useAiSidebar` external store's `messages` array. These base64 strings are never stripped after the HTTP request completes. The `previewUrl` (created via `URL.createObjectURL` in `chat-input.tsx:57`) is an object URL pointing to a Blob that is properly revoked after send (`chat-input.tsx:130`), but the `PendingImage.data` base64 string persists in the store for the entire session lifetime.
- **Impact**: Each image-bearing message retains up to 50 MB of base64 string data in the JavaScript heap. After a handful of image-heavy messages, the Electron renderer process can consume hundreds of MB of RAM, causing GC pauses, UI jank, and potential OOM crashes -- particularly problematic on devices with limited memory.
- **Recommendation**: After the `sendMessage` fetch call resolves (or immediately after constructing the request body), strip the `images[].data` field from the user message in the store. The `previewUrl` (object URL or a small thumbnail) is sufficient for rendering the chat history. Alternatively, generate a small preview data URL on the client (e.g., canvas-based thumbnail at 200px) and store only that.

### [CR2-R1-02] HIGH -- AI sidebar message array grows without bound
- **File**: `electron-app/src/renderer/components/ai/use-ai-sidebar.ts:126-128`
- **Issue**: The `addMessage` action appends to the `messages` array indefinitely. The `resetChat` action clears it, but within a single conversation thread the array has no cap. Combined with CR2-R1-01 (base64 images in messages), the `updateLastAssistantMessage` action creates a new array copy on every SSE text_delta event (`use-ai-chat.ts:119-120`), each containing all prior messages. For a long conversation with streaming responses, this means hundreds of shallow copies of a large array during a single response.
- **Impact**: Performance degradation during streaming as the message array grows. Each `text_delta` event triggers `setState` which creates a new state object and notifies all subscribers. With a large `messages` array, the shallow copy + re-render cycle becomes measurably slow. Over an extended session, memory pressure increases linearly.
- **Recommendation**: (1) Cap the `messages` array at a reasonable limit (e.g., 200 entries), trimming the oldest when exceeded. (2) For `updateLastAssistantMessage`, consider mutating the last message in-place and incrementing a counter to trigger re-renders, rather than copying the entire array. (3) The `conversationHistory` sent to the backend is already capped at 50 entries (`use-ai-chat.ts:255-258`), so capping the UI array is safe.

### [CR2-R1-03] HIGH -- Stale closure in CanvasEditor `handleWidthChange` captures outdated `editable`
- **File**: `electron-app/src/renderer/components/knowledge/canvas-editor.tsx:130-178`
- **Issue**: The `handleWidthChange` callback uses `editable` directly from the component scope via `useCallback`. However, the dependency array is `[measuredWidths, measuredHeights, editable]`. The `measuredWidths` and `measuredHeights` are `useRef().current` values (Maps), which are referentially stable -- they never trigger a re-creation of the callback. The real issue is that `containersRef.current` and `moveContainersBatchRef.current` are accessed inside the callback (correctly via refs), but the `editable` check at line 137 uses the closure value. If `editable` transitions from `true` to `false` while a ResizeObserver callback is in-flight, the auto-push logic may still execute with stale `editable = true`, pushing containers in view mode.
- **Impact**: In a race condition during view-to-edit transitions, containers could be repositioned when the user is in view mode, causing unexpected layout changes. The window is small (ResizeObserver fires asynchronously), but it violates the invariant that view mode is read-only.
- **Recommendation**: Use an `editableRef` pattern (similar to what `DocumentEditor` does at line 77) and check `editableRef.current` inside the callback instead of the closure-captured `editable`.

### [CR2-R1-04] MEDIUM -- DocumentStatusBadge creates a useSyncDocumentEmbeddings mutation on every render
- **File**: `electron-app/src/renderer/components/knowledge/document-status-badge.tsx:103`
- **Issue**: `useSyncDocumentEmbeddings()` is called unconditionally in every `DocumentStatusBadge` render, even for the `dot` variant. The mutation hook itself is lightweight, but in tree views with hundreds of documents, this creates hundreds of mutation instances. While TanStack Query handles this gracefully (mutations are garbage collected), it is unnecessary overhead.
- **Impact**: Minor memory overhead proportional to the number of visible documents in the tree. Each mutation hook allocates a MutationObserver and registers with the mutation cache. For large trees (hundreds of documents), this adds up.
- **Recommendation**: Move the `useSyncDocumentEmbeddings()` call inside the `variant === 'badge'` branch, or conditionally call it only when sync is possible (i.e., `state === 'stale' || state === 'not-indexed'`). Since hooks can't be conditionally called, extract the badge popover into a separate component that owns the mutation.

### [CR2-R1-05] MEDIUM -- `useDocuments` sort in `select` runs on every render, not just on data change
- **File**: `electron-app/src/renderer/hooks/use-documents.ts:214-219`
- **Issue**: The `select` transform in `useDocuments` creates a new sorted array on every render call. While TanStack Query memoizes the result of `select` when the input data is referentially stable, the `sort` operation allocates a new array via the spread `[...data.items]` each time `select` is invoked. The `select` function itself is recreated on every render because it is an inline function.
- **Impact**: Minor performance concern. For small document lists this is negligible, but for scopes with many documents (e.g., an application with hundreds of docs), the repeated sort + allocation could contribute to frame drops during rapid invalidation sequences.
- **Recommendation**: Wrap the `select` function in `useCallback` or extract it as a stable reference outside the hook, so TanStack Query's memoization can properly skip re-computation when data hasn't changed.

### [CR2-R1-06] MEDIUM -- `useAiSidebar` full-state mode creates a new merged object on every state change
- **File**: `electron-app/src/renderer/components/ai/use-ai-sidebar.ts:183-186`
- **Issue**: When `useAiSidebar()` is called without a selector, `getSelectedSnapshot` returns `{ ...data, ...actions }` -- a new object on every state change. The memoization check at line 184 (`last.data === data`) prevents re-computation only when the underlying `state` object hasn't changed, but since `setState` always creates a new state object (line 93), `data === last.data` is always `false` after any state mutation. This means every state change triggers a new merged object allocation, even if the consuming component doesn't use the changed field.
- **Impact**: Components using `useAiSidebar()` (e.g., `AiSidebar`) will re-render on every state change, including every `text_delta` event during streaming (which changes `messages`). The `AiSidebar` component is already rendering a message list, so the re-render is somewhat expected, but any component calling `useAiSidebar()` for a single field (e.g., just `isOpen`) will also re-render unnecessarily.
- **Impact mitigation**: The `useAiSidebar((s) => s.isOpen)` selector overload is available and correctly skips re-renders when the selected value is unchanged. `AiToggleButton` and `ChatInput` use this form.
- **Recommendation**: In `AiSidebar`, consider using individual selectors instead of destructuring the full state. This avoids unnecessary re-renders for changes to fields the component doesn't use (e.g., `threadId` changes shouldn't re-render the layout).

### [CR2-R1-07] MEDIUM -- `useWebSocketCacheInvalidation` effect dependency array omits `currentUser`
- **File**: `electron-app/src/renderer/hooks/use-websocket-cache.ts:192-198, 200-927`
- **Issue**: The main `useEffect` (line 200) has `[queryClient]` as its dependency array. The `currentUser` value is correctly accessed via `currentUserRef` inside callbacks, and a separate effect (line 196-198) keeps the ref current. This is a deliberate and correct pattern. However, the `options` ref update effect (line 192-194) depends on `options`, which is an object literal in the caller (dashboard.tsx). Since object literals create new references on every render, this effect runs on every render of the dashboard.
- **Impact**: The effect at line 192-194 runs on every render, but it only assigns a ref -- the cost is negligible. No functional issue, but it indicates that the `options` parameter could benefit from being memoized at the call site.
- **Recommendation**: At the call site in dashboard.tsx, memoize the `options` object with `useMemo` to prevent the ref-update effect from running on every render. Alternatively, accept callbacks individually instead of as an object.

### [CR2-R1-08] MEDIUM -- Duplicated image upload logic between DocumentEditor and CanvasEditor
- **File**: `electron-app/src/renderer/components/knowledge/document-editor.tsx:95-153` and `canvas-editor.tsx:220-277`
- **Issue**: The `uploadImage` / `uploadImageFile` functions in `DocumentEditor` and `CanvasEditor` are near-identical copies (file type validation, size check, upload to `/api/files/upload`, fetch download URL). This violates DRY and means any fix to the upload flow (e.g., adding retry logic, changing validation rules) must be applied in two places.
- **Impact**: Maintenance burden. A bug fix applied to one editor but not the other will create inconsistent behavior. No runtime impact.
- **Recommendation**: Extract a shared `useImageUpload(token, documentId)` hook or utility function that both editors can call.

### [CR2-R1-09] LOW -- `useDocumentLock` keep-refs-current effect has no dependency array
- **File**: `electron-app/src/renderer/hooks/use-document-lock.ts:114-118`
- **Issue**: The effect that keeps `documentIdRef`, `tokenRef`, and `userIdRef` current has no dependency array: `useEffect(() => { ... })`. This means it runs after every render, which is the intended behavior (keep refs always current). However, this pattern is unusual and a lint rule (`react-hooks/exhaustive-deps`) would flag it. The comment-less nature of this effect makes it easy to mistake for a bug.
- **Impact**: No functional issue. The effect is very cheap (three ref assignments). Minor code clarity concern.
- **Recommendation**: Add a comment explaining the intentional omission of the dependency array, or switch to the explicit pattern: `useEffect(() => { ... }, [documentId, token, userId])`.

### [CR2-R1-10] LOW -- `recentEvents` dedup map in use-websocket-cache.ts is module-level (shared across instances)
- **File**: `electron-app/src/renderer/hooks/use-websocket-cache.ts:120-122`
- **Issue**: The `recentEvents` Map and `lastCleanupTime` are module-level variables. In the current app architecture, `useWebSocketCacheInvalidation` is called once at the dashboard level, so this is fine. However, if the hook were ever called in multiple components, the dedup state would be shared, which could cause events to be incorrectly deduplicated across unrelated hook instances.
- **Impact**: No current issue (hook is called once). Fragile to future misuse.
- **Recommendation**: Document the singleton assumption with a comment, or move the dedup state into the hook's effect closure.

### [CR2-R1-11] LOW -- Missing `FolderTreeItem` memoization
- **File**: `electron-app/src/renderer/components/knowledge/folder-tree-item.tsx:95`
- **Issue**: `FolderTreeItem` is a regular function component, not wrapped in `React.memo`. It is rendered once per node in the knowledge tree, which can have hundreds of nodes. The `KnowledgeTree` parent re-renders on tree expansion, selection, and drag events, causing all tree items to re-render even when their props haven't changed.
- **Impact**: Unnecessary re-renders of tree items during tree operations. For a tree with 100+ nodes, this contributes to UI lag when expanding/collapsing folders or selecting documents. The `DocumentLockIndicator` subcomponent is already memoized, but the parent tree item is not.
- **Recommendation**: Wrap `FolderTreeItem` in `React.memo` with a shallow comparison. The component's props (node, type, depth, isExpanded, isSelected, etc.) are either primitives or stable references, making memo effective.

### [CR2-R1-12] LOW -- `clearEventDedup` is exported but never called
- **File**: `electron-app/src/renderer/hooks/use-websocket-cache.ts:127-130`
- **Issue**: `clearEventDedup` is exported with a comment saying "Call on logout to prevent stale fingerprints across sessions", but there is no call site in the codebase. The `clearQueryCache` function in `query-client.ts` clears the query cache on logout, but does not call `clearEventDedup`.
- **Impact**: After logout and re-login, stale fingerprints from the previous session could theoretically cause the first occurrence of an event to be incorrectly deduplicated if it arrives within the 1-second window. In practice, the 1-second dedup window makes this extremely unlikely.
- **Recommendation**: Call `clearEventDedup()` from the logout flow alongside `clearQueryCache()`, or remove the export if it's not needed.

### [CR2-R1-13] INFO -- Well-designed progressive hydration with priority tiers
- **File**: `electron-app/src/renderer/lib/per-query-persister.ts:276-298` and `cache-config.ts:44-54`
- **Observation**: The three-tier progressive hydration system (critical/blocking, deferred/2s delay, on-demand) is well-designed for the Electron use case. Critical queries (applications, projects) are loaded synchronously to provide instant shell rendering, while less important data hydrates in the background. This is a strong pattern that significantly improves perceived startup performance.

### [CR2-R1-14] INFO -- Excellent batch lock query pattern eliminates N+1
- **File**: `electron-app/src/renderer/hooks/use-document-lock.ts:515-685`
- **Observation**: The `useActiveLocks` hook fetches all active locks for a scope in a single request with O(1) Map lookups, replacing per-document lock queries. Combined with WebSocket in-place cache updates (DOCUMENT_LOCKED/UNLOCKED/FORCE_TAKEN), this eliminates the N+1 pattern that would otherwise degrade tree view performance. The WebSocket reconnect invalidation (line 584-592) is a nice touch for catching events missed during disconnects.

### [CR2-R1-15] INFO -- Edit mode state machine is thorough and well-guarded
- **File**: `electron-app/src/renderer/hooks/use-edit-mode.ts`
- **Observation**: The edit mode hook handles an impressive number of edge cases: lock acquire/release, inactivity timeout with auto-save, navigation guards (both in-page and screen-level), app quit confirmation, force-take detection, permission revocation during editing, and keyboard shortcuts. The use of `useRef` for synchronous state access in guards is correct and avoids the common React pitfall of stale closure values in async guards.
