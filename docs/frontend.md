# Frontend Guide

The frontend is built with Electron, React, and TypeScript, providing a desktop application experience with modern web technologies.

## Project Structure

```
electron-app/
├── src/
│   ├── main/                    # Electron main process
│   │   ├── index.ts             # Application entry, window management
│   │   ├── auto-updater.ts      # OTA auto-update via GitHub Releases
│   │   ├── notifications.ts     # Desktop notification handlers
│   │   ├── oauth-handler.ts     # OAuth flow handlers
│   │   └── ipc/handlers.ts      # IPC request handlers
│   ├── preload/                 # Secure bridge between processes
│   │   └── index.ts             # Exposed APIs to renderer
│   └── renderer/                # React application
│       ├── main.tsx             # Entry point (React 18 createRoot, StrictMode enabled)
│       ├── App.tsx              # Root: QueryClient > Auth > Notifications > Theme > ErrorBoundary > Router
│       ├── components/          # 145+ component files in 20 categories
│       ├── pages/               # 11 pages
│       ├── hooks/               # 28 custom hooks
│       ├── contexts/            # Auth, Knowledge Base, Notification UI
│       └── lib/                 # Query client, API, WebSocket, cache, utilities
├── e2e/                         # Playwright E2E tests
├── package.json                 # Dependencies
├── tailwind.config.js           # Tailwind configuration
├── tsconfig.json                # TypeScript configuration
└── electron.vite.config.ts      # Electron Vite bundler configuration
```

## Electron Architecture

### Main Process (main/index.ts)

The main process manages the application lifecycle and native functionality:

```typescript
import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'path';

let mainWindow: BrowserWindow | null = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // Load the app
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));
  }
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
```

### Preload Script (preload/index.ts)

The preload script exposes safe APIs to the renderer:

```typescript
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  // File system operations
  readFile: (path: string) => ipcRenderer.invoke('read-file', path),
  writeFile: (path: string, data: string) => ipcRenderer.invoke('write-file', path, data),

  // Window controls
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),

  // App info
  getVersion: () => ipcRenderer.invoke('get-version'),
});
```

## React Application Structure

### Entry Point (main.tsx)

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './globals.css';

const rootElement = document.getElementById('root')!;
const root = ReactDOM.createRoot(rootElement);

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

### Root Component (App.tsx)

The App component sets up all providers and the router. The actual provider nesting order is:

```typescript
function App(): JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <NotificationUIProvider>
          <ThemeProvider>
            <ErrorBoundary>
              <QueryClientInitializer>
                <AuthRouter />
              </QueryClientInitializer>
              <FindBar />
              <Toaster richColors />
            </ErrorBoundary>
          </ThemeProvider>
        </NotificationUIProvider>
      </AuthProvider>
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
```

The `AuthRouter` component uses an `AuthGate` pattern that renders:
- `LoadingScreen` during auth initialization
- `AuthPages` (login, register, verify-email, forgot-password, reset-password) when unauthenticated
- `AuthenticatedApp` (which renders `DashboardPage`) when authenticated

## Pages (11)

| Page | Path | Description |
|------|------|-------------|
| `dashboard.tsx` | Main UI | Sidebar, applications, projects, tasks, notes, AI sidebar |
| `applications/index.tsx` | Applications list | All applications view |
| `applications/[id].tsx` | Application detail | Single application with projects |
| `projects/index.tsx` | Projects list | All projects view |
| `projects/[id].tsx` | Project detail | Project with Kanban board, tasks |
| `notes/index.tsx` | Notes | Knowledge base unified view |
| `login.tsx` | Login | Email/password authentication |
| `register.tsx` | Register | New account creation |
| `verify-email.tsx` | Email verification | Post-registration verification |
| `forgot-password.tsx` | Forgot password | Password reset request |
| `reset-password.tsx` | Reset password | Password reset form |

## Components by Category (145+ files, 20 categories)

### Knowledge Base (40 files)

Core tree and navigation:
- `knowledge-tree.tsx`, `knowledge-sidebar.tsx`, `knowledge-panel.tsx`, `knowledge-tab-bar.tsx`
- `folder-tree-item.tsx`, `folder-documents.tsx`, `folder-context-menu.tsx`
- `root-drop-zone.tsx`, `tree-skeletons.tsx`, `tree-utils.ts`, `dnd-utils.ts`

Document editing:
- `document-editor.tsx`, `document-header.tsx`, `document-action-bar.tsx`, `document-status-badge.tsx`
- `editor-panel.tsx`, `editor-toolbar.tsx`, `editor-extensions.tsx`, `editor-types.ts`

Canvas (visual whiteboard):
- `canvas-editor.tsx`, `canvas-viewport.tsx`, `canvas-toolbar.tsx`, `canvas-container.tsx`
- `canvas-types.ts`, `canvas-utils.ts`, `use-canvas-state.ts`

File handling:
- `file-upload-zone.tsx`, `file-viewer-panel.tsx`, `file-conflict-dialog.tsx`
- `container-editor.tsx`, `content-utils.ts`, `use-image-upload.ts`

Dialogs and search:
- `create-dialog.tsx`, `delete-dialog.tsx`, `tag-filter-list.tsx`
- `search-bar.tsx`, `search-results-panel.tsx`, `search-highlight-extension.ts`

Draw.io integration:
- `drawio-modal.tsx`, `drawio-node.tsx`

### AI Agent / Blair Copilot (30 files)

Chat interface:
- `ai-sidebar.tsx`, `chat-input.tsx`, `chat-session-list.tsx`, `chat-skeleton.tsx`
- `ai-toggle-button.tsx`, `ai-context.tsx`, `copilot-provider.tsx`

Message rendering:
- `ai-message-renderer.tsx`, `markdown-renderer.tsx`, `source-citation.tsx`, `citation-highlight.ts`

Tool interaction:
- `tool-execution-card.tsx`, `tool-confirmation.tsx` (HITL approval)
- `activity-timeline.tsx`, `clarification-card.tsx`, `search-selection-card.tsx`

State management:
- `use-ai-chat.ts`, `use-ai-sidebar.ts` (useSyncExternalStore, no Zustand), `use-ai-sidebar-width.ts`
- `types.ts`, `interrupt-handler.tsx`, `rewind-ui.tsx` (time-travel)
- `context-summary-divider.tsx`, `user-chat-override.tsx`

Settings and configuration:
- `ai-settings-panel.tsx`, `personality-tab.tsx`, `providers-models-tab.tsx`, `indexing-tab.tsx`

Import:
- `import-dialog.tsx`

Metrics:
- `token-usage-bar.tsx`

### Dashboard (9 files)

- `DashboardTasksList.tsx`, `MyProjectsPanel.tsx`, `OverdueTasksList.tsx`
- `RecentlyCompletedList.tsx`, `SortFilterControls.tsx`, `DashboardSkeleton.tsx`
- `TaskDistributionChart.tsx` (Recharts), `CompletionTrendChart.tsx` (Recharts), `ProjectHealthChart.tsx` (Recharts)

### Tasks (9 files)

- `TaskList.tsx`, `task-card.tsx`, `task-detail.tsx`, `task-form.tsx`
- `task-kanban-board.tsx`, `kanban-column.tsx`, `task-status-badge.tsx`
- `TaskViewerDots.tsx`, `MyTasksPanel.tsx`

### Projects (7 files)

- `project-card.tsx`, `project-form.tsx`, `project-board.tsx`, `project-kanban-board.tsx`
- `ProjectMemberPanel.tsx`, `ProjectStatusOverride.tsx`, `MemberRoleBadge.tsx`

### Layout (5 files)

- `sidebar.tsx`, `header.tsx`, `window-title-bar.tsx`, `notification-panel.tsx`, `find-bar.tsx`

### Members (4 files)

- `member-list.tsx`, `member-management-modal.tsx`, `member-avatar-group.tsx`, `member-role-select.tsx`

### Kanban (3 files)

- `KanbanBoard.tsx`, `DraggableTaskCard.tsx`, `DroppableColumn.tsx`

### Comments (3 files)

- `CommentThread.tsx`, `CommentItem.tsx`, `CommentInput.tsx`

### Checklists (3 files)

- `ChecklistPanel.tsx`, `ChecklistCard.tsx`, `ChecklistItem.tsx`

### Files / Attachments (3 files)

- `attachment-list.tsx`, `file-upload.tsx`, `file-preview.tsx`

### Notifications (3 files)

- `notification-bell.tsx`, `notification-list.tsx`, `notification-item.tsx`

### Presence (2 files)

- `PresenceAvatars.tsx`, `TypingIndicator.tsx`

### Applications (2 files)

- `application-card.tsx`, `application-form.tsx`

### Invitations (2 files)

- `invitation-modal.tsx`, `invitation-response.tsx`

### Archive (2 files)

- `ArchivedProjectsList.tsx`, `ArchivedTasksList.tsx`

### Editor (1 file)

- `RichTextEditor.tsx` - Shared TipTap editor used outside the knowledge base

### Auth (1 file)

- `animated-background.tsx` - Animated background for login/register pages

### Protected Route (1 file)

- `protected-route.tsx` - `AuthGate` component for auth-based rendering

### UI / shadcn (15 files)

- `button.tsx`, `dialog.tsx`, `dropdown-menu.tsx`, `input.tsx`, `label.tsx`
- `popover.tsx`, `scroll-area.tsx`, `select.tsx`, `separator.tsx`, `skeleton.tsx`
- `tabs.tsx`, `tooltip.tsx`, `confirm-dialog.tsx`, `draggable-modal.tsx`, `image-viewer.tsx`

## Hooks (28 files)

### Data Fetching

| Hook | Description |
|------|-------------|
| `use-queries.ts` | Shared query hooks for applications, projects, tasks, statuses |
| `use-documents.ts` | Document CRUD queries and mutations |
| `use-document-folders.ts` | Folder tree queries and mutations |
| `use-document-search.ts` | Full-text search via Meilisearch backend |
| `use-document-tags.ts` | Document tag queries and mutations |
| `use-document-lock.ts` | Document lock acquisition, release, and real-time status |
| `use-document-import.ts` | Document import from external files |
| `use-folder-files.ts` | File listing within folders |
| `use-comments.ts` | Task comment queries and mutations |
| `use-checklists.ts` | Checklist queries and mutations |
| `use-attachments.ts` | File attachment queries and mutations |
| `use-members.ts` | Application and project member queries |
| `use-notifications.ts` | Notification queries and mutations |
| `use-chat-sessions.ts` | AI chat session queries and mutations |
| `use-ai-config.ts` | AI configuration queries (useAvailableModels) |
| `use-invitations.ts` | Invitation queries and mutations |

### Real-Time

| Hook | Description |
|------|-------------|
| `use-websocket.ts` | WebSocket client connection and room management |
| `use-websocket-cache.ts` | WebSocket-driven TanStack Query cache invalidation |
| `use-presence.ts` | User presence tracking in rooms |
| `use-dashboard-websocket.ts` | Dashboard-specific WebSocket events |

### UI State

| Hook | Description |
|------|-------------|
| `use-edit-mode.ts` | Edit mode toggling for documents |
| `use-draft.ts` | Draft persistence via IndexedDB |
| `use-file-search-highlight.ts` | In-page search highlighting |
| `use-task-viewers.ts` | Tracks who is viewing a task |
| `use-knowledge-permissions.ts` | Role-based permission checks for documents |
| `use-drag-and-drop.ts` | Shared drag-and-drop utilities |

### Auth

| Hook | Description |
|------|-------------|
| `use-auth.ts` | Authentication state and actions |
| `use-oauth-connect.ts` | OAuth provider connection |

## Libraries and Utilities

### lib/ Directory (15 files)

| File | Description |
|------|-------------|
| `query-client.ts` | TanStack Query client (staleTime: 30s, gcTime: 24h) + Electron focus manager + IndexedDB persistence init |
| `cache-config.ts` | IndexedDB persistence configuration with progressive hydration |
| `cache-migration.ts` | Cache migration between persistence versions |
| `per-query-persister.ts` | Per-query IndexedDB persistence with LZ-String compression (~80% reduction) |
| `query-cache-db.ts` | IndexedDB database wrapper for query cache |
| `api-client.ts` | HTTP client with auth headers and error handling |
| `websocket.ts` | WebSocket client with automatic reconnection |
| `ai-navigation.ts` | AI sidebar to screen navigation bridge (module-level, not React state) |
| `draft-db.ts` | Draft persistence via IndexedDB |
| `screen-navigation-guard.ts` | Unsaved changes guard for screen switches |
| `validation.ts` | Form validation utilities |
| `file-utils.ts` | File handling utilities |
| `file-icon.ts` | File type to icon mapping |
| `time-utils.ts` | Date/time formatting utilities |
| `notifications.ts` | Notification helper utilities |
| `utils.ts` | General utilities (cn class merge helper, etc.) |

## State Management (3 layers)

PM Desktop uses a three-layer state management approach. Notably, there is no Zustand despite it being listed as a project dependency -- the AI sidebar store uses `useSyncExternalStore` directly, and auth state lives in React Context.

### Layer 1: TanStack Query (Server State)

For all data that comes from the server (tasks, projects, documents, etc.):

```typescript
// lib/query-client.ts
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,           // 30 seconds
      gcTime: 24 * 60 * 60 * 1000,    // 24 hours (garbage collection)
      refetchOnWindowFocus: true,
      retry: 3,
    },
  },
});
```

Key patterns:
- `refetchOnMount: 'always'` for queries where WebSocket subscriptions are lost on unmount
- `refetchOnWindowFocus: false` for queries with WebSocket real-time sync
- IndexedDB persistence with LZ-String compression (50MB quota, 1000 entry cap)
- Electron focus manager overrides `refetchOnWindowFocus` behavior for app switching

### Layer 2: useSyncExternalStore (Client State)

The AI sidebar uses a lightweight external store pattern without any library dependency:

```typescript
// components/ai/use-ai-sidebar.ts
// Manages sidebar open/close state (persisted to localStorage),
// chat messages, thread tracking, streaming status, and rewind mode.
// Uses React's useSyncExternalStore for subscription.
```

### Layer 3: React Context (Cross-Cutting Concerns)

Three contexts provide app-wide functionality:

| Context | File | Purpose |
|---------|------|---------|
| `AuthProvider` | `contexts/auth-context.tsx` | Authentication state, login/register/logout, token management. Exports `useAuthStore` (compatibility alias), `useAuthState`, `useAuthActions`, `useAuthToken`, `useAuthUserId`, `useAuthUser`. |
| `KnowledgeBaseProvider` | `contexts/knowledge-base-context.tsx` | UI-only state for Notes screen: scope selection, sidebar collapse, folder expansion, document selection, search query, active tab, tag filters. Data fetching is NOT here -- it lives in TanStack Query hooks. Uses `useReducer` + localStorage persistence. |
| `NotificationUIProvider` | `contexts/notification-ui-context.tsx` | Notification panel open/close state. Exports `useNotificationUIStore`. |

### Knowledge Base Context

The knowledge base uses a dedicated React context (`KnowledgeBaseContext`) that manages:
- Active document selection and tab state
- Document tree expansion state
- Folder/document CRUD operations
- Scope selection (Application, Project, etc.)
- Search query and tag filter state
- Integration with TipTap editor and document locking

See `contexts/knowledge-base-context.tsx` for the full implementation.

## Routing (State-Based)

PM Desktop uses state-based routing instead of react-router. Navigation is managed via callbacks and `useState` in the `DashboardPage` component. Components fully unmount on screen switch -- design for mount/unmount lifecycle.

```typescript
// pages/dashboard.tsx
type View =
  | { type: 'home' }
  | { type: 'application'; id: string }
  | { type: 'project'; id: string }
  | { type: 'notes' };

export function DashboardPage() {
  const [currentView, setCurrentView] = useState<View>({ type: 'home' });

  const renderContent = () => {
    switch (currentView.type) {
      case 'application':
        return <ApplicationPage id={currentView.id} onNavigateToProject={...} />;
      case 'project':
        return <ProjectPage id={currentView.id} />;
      case 'notes':
        return <NotesPage />;
      default:
        return <HomePage onNavigateToApplication={...} />;
    }
  };

  return (
    <div className="flex h-screen">
      <Sidebar onNavigateToApplication={...} onNavigateToNotes={...} />
      <div className="flex-1 flex flex-col">
        <Header />
        <main className="flex-1 overflow-auto">{renderContent()}</main>
      </div>
    </div>
  );
}
```

The AI sidebar uses a separate navigation bridge (`lib/ai-navigation.ts`) to request screen switches from the sidebar context, since it cannot directly access the DashboardPage state.

## Component Patterns

### UI Components (shadcn/ui + Radix)

Base UI components are built on Radix UI primitives using the shadcn/ui pattern with `class-variance-authority` for variant styling and `tailwind-merge` for class composition:

```typescript
// components/ui/button.tsx
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium ...',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input bg-background hover:bg-accent',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        lg: 'h-11 rounded-md px-8',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  }
);
```

### Kanban Board

The Kanban board uses @dnd-kit for drag-and-drop:

```typescript
// components/kanban/KanbanBoard.tsx
import {
  DndContext, DragOverlay, closestCorners,
  KeyboardSensor, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';

export function KanbanBoard({ projectId }: { projectId: string }) {
  const { data: tasks } = useTasks(projectId);
  const { data: statuses } = useStatuses(projectId);
  const moveTask = useMoveTask();

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor)
  );

  // DnD handlers calculate new LexoRank position and call moveTask.mutate()
  return (
    <DndContext sensors={sensors} collisionDetection={closestCorners} ...>
      <div className="flex gap-4 overflow-x-auto p-4">
        {statuses?.map((status) => (
          <StatusColumn key={status.id} status={status} tasks={...} />
        ))}
      </div>
      <DragOverlay>{activeTask && <TaskCard task={activeTask} />}</DragOverlay>
    </DndContext>
  );
}
```

## Custom Hooks

### useWebSocket

Manages WebSocket client lifecycle tied to auth token:

```typescript
// hooks/use-websocket.ts
export function useWebSocket() {
  // Connects on mount when token exists, disconnects on unmount
  // Returns: { joinRoom, leaveRoom, on }
}
```

### useWebSocketCacheInvalidation

Invalidates TanStack Query caches in response to WebSocket events:

```typescript
// hooks/use-websocket-cache.ts
export function useWebSocketCacheInvalidation() {
  // Listens for: TASK_UPDATED, COMMENT_ADDED, CHECKLIST_UPDATED,
  // DOCUMENT_LOCKED, DOCUMENT_UNLOCKED, DOCUMENT_FORCE_TAKEN, etc.
  // Invalidates corresponding query keys on each event.
}
```

### usePresence

Tracks online users in a room via WebSocket presence events:

```typescript
// hooks/use-presence.ts
export function usePresence(roomId: string) {
  // Joins room on mount, leaves on unmount
  // Maintains Map<userId, UserPresence> from WebSocket events
  // Returns: UserPresence[]
}
```

### useDocumentLock

Manages document locking for edit coordination:

```typescript
// hooks/use-document-lock.ts
// - Acquires/releases locks when entering/exiting edit mode
// - WebSocket events push lock status changes in real-time
// - Prevents conflicts when multiple users try to edit
```

### useDocumentSearch

```typescript
// hooks/use-document-search.ts
// - Full-text search across knowledge base documents
// - Powered by Meilisearch backend
// - Debounced search input
// - Highlighted result snippets
```

## IndexedDB Persistence

### Per-Query Persister

Queries are persisted individually to IndexedDB with LZ-String compression for approximately 80% size reduction:

```typescript
// lib/per-query-persister.ts
const DB_NAME = 'pm-desktop-cache';
const MAX_ENTRIES = 1000;
const MAX_SIZE_BYTES = 50 * 1024 * 1024; // 50MB

// Each query is stored as a compressed entry with a hash key.
// LRU eviction removes oldest entries when quota is exceeded.
// Provides: persistQuery, restoreQuery, restoreQueries, clearAll
```

The `QueryClientInitializer` component in `App.tsx` initializes persistence on mount and shows a loading spinner until ready, preventing flash of stale UI on refresh. Cache is cleared on logout via the `useCacheClearOnLogout` hook.

## Styling with Tailwind

### Configuration

```javascript
// tailwind.config.js
module.exports = {
  darkMode: 'class',
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
};
```

### CSS Variables

```css
/* src/renderer/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --primary: 210 40% 98%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;
    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 212.7 26.8% 83.9%;
  }
}
```

## Key Dependencies

### UI and Framework

| Package | Version | Purpose |
|---------|---------|---------|
| `react` | 18.3.1 | UI framework |
| `react-dom` | 18.3.1 | DOM rendering |
| `electron` | 30.1.2 | Desktop runtime |
| `@radix-ui/*` | Various | 14 primitive packages (dialog, dropdown-menu, popover, etc.) |
| `tailwindcss` | 3.4.6 | Utility-first CSS |
| `tailwindcss-animate` | 1.0.7 | Animation utilities |
| `lucide-react` | 0.400.0 | Icon library |
| `class-variance-authority` | 0.7.0 | Component variant styling |
| `tailwind-merge` | 2.4.0 | Tailwind class merging |
| `clsx` | 2.1.1 | Conditional class names |
| `sonner` | 2.0.7 | Toast notifications |
| `recharts` | 3.7.0 | Dashboard charts |
| `react-virtuoso` | 4.10.0 | Virtualized lists |

### State and Data

| Package | Version | Purpose |
|---------|---------|---------|
| `@tanstack/react-query` | 5.90.20 | Server state management |
| `@tanstack/react-query-persist-client` | 5.90.22 | Query persistence plugin |
| `@tanstack/query-async-storage-persister` | 5.90.22 | Async storage adapter |
| `@tanstack/react-query-devtools` | 5.91.2 | Dev tools (dev only) |
| `idb` | 8.0.1 | IndexedDB wrapper |
| `idb-keyval` | 6.2.2 | Simple IndexedDB key-value |
| `lz-string` | 1.5.0 | Query cache compression |

### Rich Text Editor

| Package | Version | Purpose |
|---------|---------|---------|
| `@tiptap/react` | 2.6.0 | TipTap React integration |
| `@tiptap/starter-kit` | 2.6.0 | Base editor extensions |
| `@tiptap/html` | 2.27.2 | HTML serialization |
| `@tiptap/extension-*` | 2.6.0-2.27.2 | 18 extensions (tables, tasks, code blocks, mentions, etc.) |
| `lowlight` | 3.3.0 | Code syntax highlighting |

### Drag and Drop

| Package | Version | Purpose |
|---------|---------|---------|
| `@dnd-kit/core` | 6.1.0 | DnD framework |
| `@dnd-kit/sortable` | 8.0.0 | Sortable preset |
| `@dnd-kit/utilities` | 3.2.0 | DnD utilities |

### Document Handling

| Package | Version | Purpose |
|---------|---------|---------|
| `react-pdf` | 9.2.1 | PDF rendering |
| `docx-preview` | 0.3.7 | DOCX preview |
| `mammoth` | 1.12.0 | DOCX to HTML conversion |
| `react-drawio` | 1.0.7 | Draw.io diagram integration |
| `xlsx` | 0.18.5 | Excel file handling |
| `dompurify` | 3.2.4 | HTML sanitization |

### Desktop & Distribution

| Package | Version | Purpose |
|---------|---------|---------|
| `electron-updater` | latest | OTA auto-updates via GitHub Releases |
| `electron-log` | latest | Structured logging for main process |
| `electron-builder` | 24.13.3 | Packaging and publishing (devDependency) |

### Build and Testing (devDependencies)

| Package | Version | Purpose |
|---------|---------|---------|
| `vite` | 5.3.4 | Build tool |
| `electron-vite` | 2.3.0 | Electron + Vite integration |
| `typescript` | 5.5.3 | Type checking (strict mode) |
| `vitest` | 1.3.1 | Unit testing |
| `@playwright/test` | 1.58.2 | E2E testing |
| `@testing-library/react` | 14.2.1 | React component testing |
| `@testing-library/jest-dom` | 6.4.2 | DOM assertion matchers |

## Testing

### Test Setup

```typescript
// vitest.config.ts (conceptual - actual config in electron.vite.config.ts)
{
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/renderer/__tests__/setup.ts'],
  },
  resolve: {
    alias: { '@': './src/renderer' },
  },
}
```

### Test Scripts

```bash
# Unit tests
npm run test              # Vitest run (single pass)
npm run test:watch        # Vitest watch mode
npm run test:coverage     # Vitest with coverage

# E2E tests
npm run e2e               # All Playwright tests
npm run e2e:smoke         # Quick smoke tests
npm run e2e:two-client    # Multi-client collaboration tests
npm run e2e:knowledge     # Knowledge base tests

# Type checking and linting
npm run typecheck         # Strict TypeScript (node + web configs)
npm run lint              # ESLint with zero warnings policy
```

### Multi-Client Development

For testing multi-user collaboration scenarios:

```bash
npm run dev               # Primary client
npm run dev:client2       # Second client (separate user data)
npm run dev:client3       # Third client (separate user data)
```

## Auto-Updates (OTA via GitHub Releases)

PM Desktop uses `electron-updater` to deliver over-the-air updates via GitHub Releases.

### How It Works

1. **Main process** (`auto-updater.ts`) checks for updates on startup (5-second delay) and exposes IPC handlers
2. **Preload script** bridges the updater API to the renderer via `electronAPI`
3. **electron-builder** publishes installers + `latest.yml` manifest to GitHub Releases
4. On launch, the app compares its version against `latest.yml` and notifies the user if an update is available

### Architecture

```
GitHub Releases (latest.yml + installer)
         ↑ publish                    ↓ check
   electron-builder            electron-updater (main process)
                                      ↓ IPC
                               preload bridge
                                      ↓
                               renderer (UI)
```

### Renderer API

The preload script exposes these methods on `window.electronAPI`:

```typescript
// Check for updates
checkForUpdates(): Promise<{ success: boolean; version?: string; error?: string }>

// Download the update (manual trigger — not auto-downloaded)
downloadUpdate(): Promise<{ success: boolean; error?: string }>

// Quit and install the downloaded update
installUpdate(): void

// Subscribe to update status events
onUpdateStatus(callback: (status: UpdateStatus) => void): () => void
```

Update status events include: `checking`, `available`, `not-available`, `downloading` (with progress), `downloaded`, `error`.

### Publishing a Release

```bash
cd electron-app

# 1. Bump version
npm version patch   # or minor/major

# 2. Build
npx electron-vite build

# 3. Publish to GitHub Releases (requires GH_TOKEN env var)
npx electron-builder --publish always
```

### Configuration

The `publish` config in `package.json` points to GitHub:

```json
"publish": {
  "provider": "github",
  "owner": "sannge",
  "repo": "PMS"
}
```

See [Desktop Releases & OTA Updates](./desktop-releases.md) for the full release guide.

## Important Patterns and Gotchas

- **State-based routing (NOT react-router)**: Components fully unmount on screen switch. Design for mount/unmount lifecycle. Navigation via callbacks in `DashboardPage`.
- **React.StrictMode enabled** (main.tsx line 25): Causes double effects in development. Do not rely on effects running exactly once.
- **Electron focus manager**: The custom focus manager in `query-client.ts` fires window focus events on app switch, which can trigger unexpected refetches.
- **WebSocket cache invalidation**: Handled at the `DashboardPage` level (not in `App.tsx`) so it has access to navigation state for member removal redirect.
- **IndexedDB hydrates stale data**: Use `refetchOnMount: 'always'` for queries where WebSocket subscriptions are lost on unmount. Use `refetchOnWindowFocus: false` for queries with WebSocket real-time sync.
- **No Zustand stores**: Despite the dependency being referenced in project documentation, the codebase uses `useSyncExternalStore` for the AI sidebar and React Context for auth/notifications/knowledge base. The `useAuthStore` export is a compatibility alias for the auth context.
- **KnowledgeSidebar vs KnowledgePanel**: `KnowledgeSidebar` renders `KnowledgeTree` on the Notes page. `KnowledgePanel` renders `ApplicationTree` or `FolderTree` in embedded panels (e.g., within Application or Project views).
- **AI navigation bridge**: Since the AI sidebar cannot directly access DashboardPage routing state, `lib/ai-navigation.ts` provides a module-level bridge to store pending navigation targets and request screen switches.
