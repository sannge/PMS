---
phase: 04-auto-save-content-pipeline
plan: 03
subsystem: editor-lifecycle
tags: [electron, ipc, auto-save, save-status, before-quit]
depends_on: ["04-01", "04-02"]
provides: ["save-on-navigate", "save-on-quit", "save-status-indicator"]
affects: ["05"]
tech-stack:
  added: []
  patterns: ["electron-before-quit-ipc", "callback-set-pattern", "ref-based-cleanup-hook"]
key-files:
  created:
    - electron-app/src/renderer/components/knowledge/SaveStatus.tsx
  modified:
    - electron-app/src/main/index.ts
    - electron-app/src/preload/index.ts
    - electron-app/src/preload/index.d.ts
    - electron-app/src/renderer/hooks/use-auto-save.ts
decisions:
  - id: "04-03-01"
    description: "useSaveOnUnmount uses ref to capture latest saveNow -- avoids stale closure and unnecessary effect re-runs"
  - id: "04-03-02"
    description: "useSaveOnQuit calls confirmQuitSave in .finally() -- ensures quit proceeds even if save throws"
  - id: "04-03-03"
    description: "SaveStatus uses setTick counter state to force re-render every second for live time display"
metrics:
  duration: "~4 min"
  completed: "2026-02-01"
---

# Phase 4 Plan 3: Save Triggers & Status Indicator Summary

Electron before-quit IPC with 3s timeout, save-on-navigate cleanup hook, save-on-quit IPC hook, and SaveStatus component with live relative time display.

## What Was Built

### Task 1: Electron before-quit IPC and save-on-navigate cleanup

**Main process (`index.ts`):**
- Added `isQuitting` flag at module scope to track quit state
- Added `close` event handler on mainWindow that intercepts close, sends `before-quit-save` IPC to renderer, and sets a 3-second timeout fallback
- Added `ipcMain.on('quit-save-complete')` listener that sets `isQuitting = true` and closes the window

**Preload (`index.ts` + `index.d.ts`):**
- Added `beforeQuitCallbacks` Set following the existing callback Set pattern (matching `notificationCallbacks`, `webSocketCallbacks`, `maximizedCallbacks`)
- Added `ipcRenderer.on('before-quit-save')` listener that iterates the Set
- Exposed `onBeforeQuit(callback)` returning cleanup function and `confirmQuitSave()` sending `quit-save-complete`
- Updated `ElectronAPI` interface in both `.ts` and `.d.ts` files

**Renderer hooks (`use-auto-save.ts`):**
- `useSaveOnUnmount(saveNow)` -- calls saveNow() via ref on component unmount (navigate away)
- `useSaveOnQuit(saveNow)` -- registers for Electron before-quit IPC, calls saveNow() then confirmQuitSave()

### Task 2: SaveStatus indicator component

- Handles all four states: `idle` (renders nothing), `saving` (pulse animation), `saved` (live-updating "Saved Xs ago"), `error` (red "Save failed")
- Uses `setInterval(1000)` tick to re-render the relative time display every second
- Formats: "Saved just now" (<5s), "Saved Xs ago" (5-59s), "Saved Xm ago" (60s+)
- Styled with `text-xs text-muted-foreground` matching existing status bar (EditorStatusBar)

## Deviations from Plan

None -- plan executed exactly as written.

## Commits

| Hash | Description |
|------|-------------|
| 5a3b1b5 | feat(04-03): add before-quit IPC save coordination and save-on-unmount hooks |
| ae8c311 | feat(04-03): add SaveStatus indicator component for editor status bar |

## Next Phase Readiness

Phase 4 is now complete (all 4 plans done). The auto-save pipeline provides:
- Debounced auto-save with optimistic concurrency (04-01)
- IndexedDB draft persistence and crash recovery (04-02)
- Save-on-navigate, save-on-quit with 3s timeout, and save status UI (04-03)
- TipTap JSON to Markdown/plain text conversion (04-04)

Phase 5 (Integration) can wire these hooks into the document editor component.
