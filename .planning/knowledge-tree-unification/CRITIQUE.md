# Knowledge Tree Unification - Plan Critique

## Issue List

---

### CRITICAL-1: KnowledgeTree DnD prefix is wrong for project scope

**Severity: Critical**

The plan proposes replacing FolderTree with KnowledgeTree (no `applicationId`) for project scope in KnowledgePanel. However, KnowledgeTree hardcodes its DnD prefix:

```ts
// knowledge-tree.tsx:486
const dndPrefix = isApplicationScope ? 'app' : 'personal'
```

When `applicationId` is not provided (project scope), `isApplicationScope` is `false`, so `dndPrefix = 'personal'`. This means:
- Sortable IDs would be `personal-folder-{id}` instead of `project-folder-{id}`
- `parsePrefixToScope('personal')` returns `{ scope: 'personal', scopeId: '' }` -- all mutations (move, create, rename, delete) would use scope `'personal'` instead of `'project'`
- This corrupts the scope on every DnD move and context menu CRUD operation

FolderTree uses `scope` from context directly as its prefix (line 227: `items.push(\`${scope}-folder-${node.id}\`)`), which works correctly for any scope.

**Fix:** Replace the hardcoded prefix with context-aware logic:
```ts
const dndPrefix = isApplicationScope ? 'app' : scope
```

And update `getScopeFromPrefix` fallback accordingly:
```ts
// Current (wrong for project scope):
if (!parsed) return { scope, scopeId: effectiveScopeId ?? '' }
// This is actually fine already -- it falls back to context scope/scopeId.
// But parsePrefixToScope('project') returns null (no colon, not 'app' or 'personal'),
// so the fallback fires. This actually works!
```

Wait -- let me re-examine. `parsePrefixToScope('project')` in `dnd-utils.ts:29-34`:
- `'project'` is not `'app'`, not `'personal'`, and has no colon, so it returns `null`.
- `getScopeFromPrefix` falls back to `{ scope, scopeId: effectiveScopeId ?? '' }`, which IS the correct project scope from context.

So actually the mutation scope would be correct via the fallback! But the sortable ID prefix `'project'` would not match `validPrefixes = ['project']` because... wait, it would. `parseSortableId('project-folder-{id}', ['project'])` would match the `project` prefix. BUT then `parsePrefixToScope('project')` returns null, and the fallback to `getScopeFromPrefix` would return the correct scope.

Let me re-examine more carefully. If we change `dndPrefix` to `scope`:
- For project scope: `dndPrefix = 'project'`, sortable IDs = `project-folder-{id}`. BUT `parseSortableId` would also match the project UUID regex `project-{uuid}-folder-{id}` first, which would FAIL because the folder ID after `project-` is not a UUID.

Actually wait, re-reading the regex in dnd-utils.ts:58-59:
```
/^project-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-(folder|doc)-(.+)$/i
```

The sortable ID `project-folder-{uuid}` would NOT match this regex because `folder` is not a UUID pattern. The `parseSortableId` function first tries valid prefixes (`['project']`), finds `project-folder-` match, and returns `{ prefix: 'project', type: 'folder', itemId: '{uuid}' }`. This is correct.

So actually using `scope` as prefix IS correct for project scope. The issue is that `'personal'` is wrong. Let me think about whether the current KT prefix of `'personal'` causes issues beyond the naming mismatch...

If `dndPrefix = 'personal'` in project scope:
- `sortableItems` uses `personal-folder-{id}`, `personal-doc-{id}`
- `validPrefixes = ['personal']`
- `parse('personal-folder-{id}')` returns `{ prefix: 'personal', type: 'folder', itemId: '{id}' }`
- `getScopeFromPrefix('personal')` calls `parsePrefixToScope('personal')` which returns `{ scope: 'personal', scopeId: '' }`
- Then `getScopeFromPrefix` returns `{ scope: 'personal', scopeId: '' }` -- NOT the project scope!

Wait, looking again at `getScopeFromPrefix` (line 373-377):
```ts
const getScopeFromPrefix = useCallback((prefix: string): ScopeInfo => {
    const parsed = parsePrefixToScope(prefix)
    if (!parsed) return { scope, scopeId: effectiveScopeId ?? '' }
    return { scope: parsed.scope, scopeId: parsed.scopeId || (effectiveScopeId ?? '') }
}, [scope, effectiveScopeId])
```

For `prefix = 'personal'`, `parsePrefixToScope('personal')` returns `{ scope: 'personal', scopeId: '' }` (NOT null). Then `getScopeFromPrefix` returns `{ scope: 'personal', scopeId: '' || (effectiveScopeId ?? '') }` = `{ scope: 'personal', scopeId: effectiveScopeId }`.

So the scope would be `'personal'` instead of `'project'`. And `effectiveScopeId` in project scope would be the project ID (since `scope !== 'personal'`, `effectiveScopeId = scopeId = projectId`).

The mutation would send `scope: 'personal', scopeId: projectId` to the backend, which is WRONG. The backend would try to create/move/rename in personal scope with a project ID as scope_id.

**This confirms the bug is Critical.** The fix is:
```ts
// Change line 486 from:
const dndPrefix = isApplicationScope ? 'app' : 'personal'
// To:
const dndPrefix = isApplicationScope ? 'app' : scope
```

But wait, `scope` could be `'application'` (from context) when there's no applicationId, which would give prefix `'application'`, and `parsePrefixToScope('application')` returns `null` (not 'app'), so it falls back correctly. But the sortable IDs would be `application-folder-{id}`, and `parseSortableId('application-folder-{id}', ['application'])` would match. So this works.

Actually, there's another scenario: KnowledgePanel with `scope='application'` and `showProjectFolders=false`. This currently uses FolderTree with prefix `'application'`. After the swap to KnowledgeTree (no applicationId), `isApplicationScope = false`, `scope = 'application'` from context. So `dndPrefix = 'application'` (with the fix). This is correct and matches FolderTree behavior.

**Final fix:** Change `dndPrefix` to use `scope` when not in application mode, and ensure all downstream DnD code handles the new prefix values correctly.

---

### CRITICAL-2: `handleRenameSubmit` and `handleDeleteConfirm` in FolderTree use scope directly -- KT uses scope tracking state

**Severity: Major (not Critical, since the plan already addresses scope tracking)**

FolderTree's `handleRenameSubmit` (line 490-518) uses `scope` and `scopeId` directly from context, without scope tracking state (`renamingItemScope`, `renamingItemScopeId`). This is correct for FolderTree because it's always single-scope.

KnowledgeTree has scope tracking state, so when KT replaces FT, the scope tracking state will be `null` (default), and KT falls back to `scope`/`effectiveScopeId` from context. This fallback is correct for single-scope scenarios.

**Verdict:** No issue -- KT's fallback handles this correctly.

---

### MAJOR-1: Phase 2 Step 2.1 -- KnowledgePanel FolderTree replacement logic is wrong for `application` scope without `showProjectFolders`

**Severity: Major**

The plan (Step 2.1) simplifies the tree selection to:
```tsx
<KnowledgeTree
  applicationId={scope === 'application' && showProjectFolders ? scopeId : undefined}
/>
```

This means when `scope === 'application'` but `showProjectFolders` is false (not a current use case, but possible), KnowledgeTree receives no `applicationId`, so `isApplicationScope = false`, and `scope` comes from context (`'application'`). In this case, KT would operate in "non-application" mode but with application scope data. This is actually correct behavior -- it shows a flat tree without project sections, which is what FolderTree does.

However, this scenario is currently theoretical since no consumer uses `scope='application'` without `showProjectFolders`. The plan notes in Step 2.1 verification point 5: "If there were an application detail page without showProjectFolders, it should show a flat application-scope tree." This is correct.

**Verdict:** Not a bug, but the plan should explicitly call out this edge case as a design decision and add a test scenario.

---

### MAJOR-2: FolderTree `handleDeleteConfirm` missing `scope`/`scopeId` in dependency array

**Severity: Major (pre-existing bug, not introduced by plan)**

FolderTree `handleDeleteConfirm` (line 539-547) uses `scope` and `scopeId` from context but they're NOT in the `useCallback` dependency array:
```ts
const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return
    if (deleteTarget.type === 'folder') {
      await deleteFolder.mutateAsync({ folderId: deleteTarget.id, scope, scopeId: scopeId ?? '' })
    } else {
      ...
    }
}, [deleteTarget, deleteFolder, deleteDocument, selectedDocumentId, selectDocument])
// Missing: scope, scopeId
```

KnowledgeTree has the same pattern (line 796-806) with `scope` and `effectiveScopeId` in the dependency array. So KT correctly includes them.

**Verdict:** The plan's unification actually fixes this pre-existing bug. Worth noting in the plan as a bonus fix.

---

### MAJOR-3: Phase 3 EditorPanel component is missing the `cn` import

**Severity: Major**

The EditorPanel code snippet in Step 3.1 uses `cn()` for className merging (line 609, 619, 632) but the import list doesn't include it. The plan mentions `cn` import at line 734 ("Note: The component needs a `cn` import from `@/lib/utils`") but this is a footnote, not in the code snippet.

**Fix:** Add `import { cn } from '@/lib/utils'` to the EditorPanel code snippet.

---

### MAJOR-4: Phase 3 Step 3.3 -- `selectedDocumentId` removal from InnerPanel destructuring is premature

**Severity: Major**

Step 3.3 says: "Remove `selectedDocumentId` from `useKnowledgeBase()` destructuring (line 94) since it's only needed if we use it in the JSX ternary."

But looking at the current InnerPanel code (line 94):
```ts
const { selectedDocumentId, selectDocument } = useKnowledgeBase()
```

`selectedDocumentId` is used in:
1. `useEditMode({ documentId: selectedDocumentId, ... })` -- line 102-105 (being removed in Step 3.3)
2. The JSX ternary for showing editor vs empty state -- lines 233-347 (being replaced by `<EditorPanel />`)

After Step 3.3, `selectedDocumentId` is no longer used in InnerPanel, so removing it is correct. However, the plan says to "keep `selectDocument`" -- this needs to be verified. Let me check:

`selectDocument` is used in `handleCreateDoc` onSuccess callback (line 133). Yes, it's still needed.

**Verdict:** The plan is correct, but the instruction is confusing. It says "remove `selectedDocumentId` from destructuring" and then separately "keep `selectDocument`". Should be clarified as: "Update destructuring to: `const { selectDocument } = useKnowledgeBase()`"

---

### MINOR-1: Step 1.2 says to change return type on line 137 but line 137 is the function body

**Severity: Minor**

Step 1.2 says "Change return type to `JSX.Element | null` (line 137)". But line 137 is the function destructuring body, not the function signature. The function signature is on line 137 with the colon after the closing brace:
```ts
}: ProjectSectionProps): JSX.Element {
```

The line reference is correct (137 is where the return type appears), but the instruction could be clearer.

**Fix:** Specify: "On line 137, change `}: ProjectSectionProps): JSX.Element {` to `}: ProjectSectionProps): JSX.Element | null {`"

---

### MINOR-2: Step 1.3 line reference for spinner placement may be off

**Severity: Minor**

Step 1.3 says "After line 959 (`<div className="py-1" role="tree">`), add the spinner". Line 959 is indeed `<div className="py-1" role="tree">`, so adding the spinner JSX immediately after the opening tag is correct.

However, the comment says `{/* Subtle background refresh indicator */}` which matches AT's convention. This is fine.

---

### MINOR-3: Steps 2.3-2.4 (hook extraction) are scope creep

**Severity: Minor (borderline Scope Creep)**

Steps 2.3 and 2.4 extract `useTreeDnd` and `useTreeCrud` hooks from KnowledgeTree. While this is nice for maintainability, it's not part of the core goal (eliminating duplicate components). It adds complexity to the PR and increases risk.

The plan already removes ~1700 lines net. Hook extraction adds ~100 lines of interface definitions and re-imports. The benefit (shorter KnowledgeTree file) is real but not essential.

**Recommendation:** Move Steps 2.3-2.4 to a separate follow-up PR. The main PR should focus on elimination of duplicates. Include a "Future Improvements" note in the plan.

---

### MINOR-4: Step 2.5 -- documentation update is trivial and doesn't need its own step

**Severity: Nitpick**

Step 2.5 is a one-line comment change. It should be folded into Step 2.2 (delete FolderTree) rather than being a separate step.

---

### MINOR-5: Phase 3 EditorPanel has `useEffect`-dependent import not listed

**Severity: Minor**

The Notes page `NotesPageContent` imports `useEffect` (line 17). After removing the inline `EditorPanel`, the plan says to check if `useMemo` is still needed. It doesn't mention checking `useEffect`. Looking at the code, `useEffect` is used in `NotesPageContent` for WebSocket room management (lines 207-269), so it's still needed. This is fine, but the plan should explicitly note that `useEffect` import stays.

---

### MINOR-6: Missing `DocumentHeader` component check

**Severity: Minor**

The git status shows an untracked file `document-header.tsx`. The plan doesn't mention this file. If it imports from `ApplicationTree` or `FolderTree`, it would break after deletion.

I checked the grep results -- `ApplicationTree` and `FolderTree` are only imported in `knowledge-panel.tsx`. So this is not an issue.

---

### NITPICK-1: AT passes `hideIfEmpty={false}` to ProjectSection explicitly

**Severity: Nitpick**

AT line 1194: `hideIfEmpty={false}`. This is the default value, so it's redundant. KT doesn't pass `hideIfEmpty` at all, which means it uses the default `false`. Functionally identical, but the plan should note that the explicit `hideIfEmpty={false}` will be dropped (since KT doesn't pass it).

---

### NITPICK-2: Plan uses wrong line numbers for KnowledgePanel after Phase 1 changes

**Severity: Nitpick**

Phase 2 Step 2.1 references "currently after Step 1.5" for the conditional, but doesn't give line numbers. This is fine for readability but the plan could be more precise.

---

## Questions for the User

1. **Hook extraction (Steps 2.3-2.4):** Should these be included in the main PR or deferred to a follow-up? They add refactoring risk without eliminating duplication.

2. **DnD prefix for project scope:** The fix changes sortable IDs from `personal-folder-{id}` to `project-folder-{id}` (matching FolderTree's current behavior). Is there any external system that persists sortable IDs (e.g., localStorage, backend)? If so, migrating existing stored IDs would be needed.

3. **Application scope without `showProjectFolders`:** Is this a supported use case? Currently no consumer uses it, but the unified component would handle it. Should we add explicit test coverage for this?

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 1 (DnD prefix bug) |
| Major | 4 |
| Minor | 6 |
| Nitpick | 2 |

The most important finding is CRITICAL-1: the DnD prefix logic in KnowledgeTree would break project-scope operations when used without `applicationId`. This must be fixed before FolderTree can be deleted.
