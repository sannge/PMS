# Frontend Guide

The frontend is built with Electron, React, and TypeScript, providing a desktop application experience with modern web technologies.

## Project Structure

```
electron-app/
├── src/
│   ├── main/                    # Electron main process
│   │   └── index.ts             # Application entry, window management
│   ├── preload/                 # Secure bridge between processes
│   │   └── index.ts             # Exposed APIs to renderer
│   └── renderer/                # React application
│       ├── main.tsx             # React entry point
│       ├── App.tsx              # Root component with providers
│       ├── components/          # React components
│       ├── pages/               # Page-level components
│       ├── stores/              # Zustand state stores
│       ├── hooks/               # Custom React hooks
│       ├── contexts/            # React context providers
│       └── lib/                 # Utilities and clients
├── tests/                       # Test files
├── package.json                 # Dependencies
├── tailwind.config.js           # Tailwind configuration
├── tsconfig.json                # TypeScript configuration
└── vite.config.ts               # Vite bundler configuration
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
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

### Root Component (App.tsx)

The App component sets up all providers and the router:

```typescript
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './lib/query-client';
import { AuthProvider } from './contexts/auth-context';
import { NotificationUIProvider } from './contexts/notification-ui-context';
import { ThemeProvider } from './contexts/theme-context';
import { Router } from './Router';

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <NotificationUIProvider>
            <ErrorBoundary>
              <Router />
            </ErrorBoundary>
          </NotificationUIProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
```

## State Management

PM Desktop uses a three-layer state management approach.

### Layer 1: TanStack Query (Server State)

For data that comes from the server (tasks, projects, users, etc.):

```typescript
// lib/query-client.ts
import { QueryClient } from '@tanstack/react-query';
import { createQueryPersister } from './per-query-persister';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,      // 5 minutes
      gcTime: 24 * 60 * 60 * 1000,   // 24 hours (garbage collection)
      refetchOnWindowFocus: true,
      retry: 3,
    },
  },
});

// Enable IndexedDB persistence
const persister = createQueryPersister();
persister.restoreQueries(queryClient);
```

#### Query Hooks

```typescript
// hooks/use-tasks.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query-keys';

export function useTasks(projectId: string) {
  return useQuery({
    queryKey: queryKeys.tasks(projectId),
    queryFn: () => api.getTasks(projectId),
    enabled: !!projectId,
  });
}

export function useCreateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.createTask,
    onSuccess: (newTask) => {
      // Invalidate tasks list to refetch
      queryClient.invalidateQueries({
        queryKey: queryKeys.tasks(newTask.project_id),
      });
    },
    // Optimistic update
    onMutate: async (newTaskData) => {
      await queryClient.cancelQueries({
        queryKey: queryKeys.tasks(newTaskData.project_id),
      });

      const previousTasks = queryClient.getQueryData(
        queryKeys.tasks(newTaskData.project_id)
      );

      queryClient.setQueryData(
        queryKeys.tasks(newTaskData.project_id),
        (old: Task[]) => [...old, { ...newTaskData, id: 'temp-id' }]
      );

      return { previousTasks };
    },
    onError: (err, newTask, context) => {
      // Rollback on error
      queryClient.setQueryData(
        queryKeys.tasks(newTask.project_id),
        context?.previousTasks
      );
    },
  });
}
```

#### Query Keys

Centralized query key management:

```typescript
// lib/query-keys.ts
export const queryKeys = {
  // Applications
  applications: ['applications'] as const,
  application: (id: string) => ['application', id] as const,

  // Projects
  projects: (appId: string) => ['projects', appId] as const,
  project: (id: string) => ['project', id] as const,

  // Tasks
  tasks: (projectId: string) => ['tasks', projectId] as const,
  task: (id: string) => ['task', id] as const,

  // Comments
  comments: (taskId: string) => ['comments', taskId] as const,

  // Checklists
  checklists: (taskId: string) => ['checklists', taskId] as const,

  // Members
  appMembers: (appId: string) => ['appMembers', appId] as const,
  projectMembers: (projectId: string) => ['projectMembers', projectId] as const,

  // Notifications
  notifications: ['notifications'] as const,

  // Attachments
  attachments: (taskId: string) => ['attachments', taskId] as const,

  // Invitations
  invitations: ['invitations'] as const,

  // Statuses
  statuses: (projectId: string) => ['statuses', projectId] as const,
};
```

### Layer 2: Zustand (Client State)

For UI state that doesn't need server persistence:

```typescript
// stores/auth-store.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  user: User | null;
  token: string | null;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setUser: (user) => set({ user }),
      setToken: (token) => set({ token }),
      logout: () => set({ user: null, token: null }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ token: state.token }),
    }
  )
);
```

```typescript
// stores/notes-store.ts
import { create } from 'zustand';

interface NotesState {
  activeNoteId: string | null;
  openTabs: string[];
  setActiveNote: (id: string | null) => void;
  openTab: (id: string) => void;
  closeTab: (id: string) => void;
}

export const useNotesStore = create<NotesState>((set) => ({
  activeNoteId: null,
  openTabs: [],
  setActiveNote: (id) => set({ activeNoteId: id }),
  openTab: (id) => set((state) => ({
    openTabs: state.openTabs.includes(id)
      ? state.openTabs
      : [...state.openTabs, id],
    activeNoteId: id,
  })),
  closeTab: (id) => set((state) => ({
    openTabs: state.openTabs.filter((tabId) => tabId !== id),
    activeNoteId: state.activeNoteId === id
      ? state.openTabs[0] || null
      : state.activeNoteId,
  })),
}));
```

### Layer 3: React Context (Cross-Cutting Concerns)

For app-wide functionality that needs to be accessible everywhere:

```typescript
// contexts/auth-context.tsx
import React, { createContext, useContext, useEffect, useState } from 'react';
import { useAuthStore } from '../stores/auth-store';
import { api } from '../lib/api';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { user, token, setUser, setToken, logout: storeLogout } = useAuthStore();
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Fetch user on mount if token exists
    if (token && !user) {
      api.getCurrentUser()
        .then(setUser)
        .catch(() => storeLogout())
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = async (email: string, password: string) => {
    const { access_token } = await api.login(email, password);
    setToken(access_token);
    const user = await api.getCurrentUser();
    setUser(user);
  };

  const register = async (data: RegisterData) => {
    await api.register(data);
    await login(data.email, data.password);
  };

  const logout = () => {
    storeLogout();
    // Clear all caches
    queryClient.clear();
    clearIndexedDB();
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
```

## Routing (State-Based)

PM Desktop uses state-based routing instead of react-router:

```typescript
// pages/dashboard.tsx
import { useState } from 'react';
import { Sidebar } from '../components/layout/sidebar';
import { Header } from '../components/layout/header';
import { ApplicationPage } from './applications/[id]';
import { ProjectPage } from './projects/[id]';
import { NotesPage } from './notes';

type View =
  | { type: 'home' }
  | { type: 'application'; id: string }
  | { type: 'project'; id: string }
  | { type: 'notes' };

export function DashboardPage() {
  const [currentView, setCurrentView] = useState<View>({ type: 'home' });

  const navigateToApplication = (id: string) => {
    setCurrentView({ type: 'application', id });
  };

  const navigateToProject = (id: string) => {
    setCurrentView({ type: 'project', id });
  };

  const navigateToNotes = () => {
    setCurrentView({ type: 'notes' });
  };

  const renderContent = () => {
    switch (currentView.type) {
      case 'application':
        return (
          <ApplicationPage
            id={currentView.id}
            onNavigateToProject={navigateToProject}
          />
        );
      case 'project':
        return <ProjectPage id={currentView.id} />;
      case 'notes':
        return <NotesPage />;
      default:
        return <HomePage onNavigateToApplication={navigateToApplication} />;
    }
  };

  return (
    <div className="flex h-screen">
      <Sidebar
        onNavigateToApplication={navigateToApplication}
        onNavigateToNotes={navigateToNotes}
      />
      <div className="flex-1 flex flex-col">
        <Header />
        <main className="flex-1 overflow-auto">
          {renderContent()}
        </main>
      </div>
    </div>
  );
}
```

## Component Patterns

### UI Components (shadcn/ui + Radix)

Base UI components are built on Radix UI primitives:

```typescript
// components/ui/button.tsx
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50',
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
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
```

### Feature Components

Feature components combine UI primitives with business logic:

```typescript
// components/tasks/TaskCard.tsx
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Card } from '../ui/card';
import { Badge } from '../ui/badge';
import { Avatar } from '../ui/avatar';
import { ChecklistProgress } from '../checklists/ChecklistProgress';

interface TaskCardProps {
  task: Task;
  onClick: () => void;
}

export function TaskCard({ task, onClick }: TaskCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <Card
      ref={setNodeRef}
      style={style}
      className="p-3 cursor-pointer hover:shadow-md transition-shadow"
      onClick={onClick}
      {...attributes}
      {...listeners}
    >
      <div className="space-y-2">
        {/* Task type badge */}
        <div className="flex items-center gap-2">
          <Badge variant={getTaskTypeVariant(task.task_type)}>
            {task.task_type}
          </Badge>
          <Badge variant={getPriorityVariant(task.priority)}>
            {task.priority}
          </Badge>
        </div>

        {/* Title */}
        <h4 className="font-medium text-sm line-clamp-2">
          {task.title}
        </h4>

        {/* Checklist progress */}
        {task.checklist_total > 0 && (
          <ChecklistProgress
            done={task.checklist_done}
            total={task.checklist_total}
          />
        )}

        {/* Assignee */}
        {task.assignee && (
          <div className="flex justify-end">
            <Avatar
              src={task.assignee.avatar_url}
              alt={task.assignee.display_name}
              size="sm"
            />
          </div>
        )}
      </div>
    </Card>
  );
}
```

### Kanban Board

The Kanban board uses @dnd-kit for drag-and-drop:

```typescript
// components/kanban/KanbanBoard.tsx
import {
  DndContext,
  DragOverlay,
  closestCorners,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { useTasks, useMoveTask } from '../../hooks/use-tasks';
import { useStatuses } from '../../hooks/use-statuses';
import { StatusColumn } from './StatusColumn';
import { TaskCard } from '../tasks/TaskCard';

interface KanbanBoardProps {
  projectId: string;
}

export function KanbanBoard({ projectId }: KanbanBoardProps) {
  const { data: tasks } = useTasks(projectId);
  const { data: statuses } = useStatuses(projectId);
  const moveTask = useMoveTask();
  const [activeTask, setActiveTask] = useState<Task | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
    useSensor(KeyboardSensor)
  );

  const handleDragStart = (event: DragStartEvent) => {
    const task = tasks?.find((t) => t.id === event.active.id);
    setActiveTask(task || null);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveTask(null);

    if (!over) return;

    const taskId = active.id as string;
    const newStatusId = over.id as string;

    // Calculate new rank based on position
    const newRank = calculateLexorank(tasks, newStatusId, over.data.current?.sortable?.index);

    moveTask.mutate({
      taskId,
      newStatusId,
      newRank,
    });
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-auto p-4">
        {statuses?.map((status) => (
          <StatusColumn
            key={status.id}
            status={status}
            tasks={tasks?.filter((t) => t.task_status_id === status.id) || []}
          />
        ))}
      </div>

      <DragOverlay>
        {activeTask && <TaskCard task={activeTask} onClick={() => {}} />}
      </DragOverlay>
    </DndContext>
  );
}
```

## Custom Hooks

### useWebSocket Hook

```typescript
// hooks/use-websocket.ts
import { useEffect, useRef, useCallback } from 'react';
import { WebSocketClient, MessageType } from '../lib/websocket';
import { useAuthStore } from '../stores/auth-store';

export function useWebSocket() {
  const { token } = useAuthStore();
  const clientRef = useRef<WebSocketClient | null>(null);

  useEffect(() => {
    if (!token) return;

    const client = new WebSocketClient(token);
    client.connect();
    clientRef.current = client;

    return () => {
      client.disconnect();
    };
  }, [token]);

  const joinRoom = useCallback((room: string) => {
    clientRef.current?.joinRoom(room);
  }, []);

  const leaveRoom = useCallback((room: string) => {
    clientRef.current?.leaveRoom(room);
  }, []);

  const on = useCallback((type: MessageType, callback: (data: any) => void) => {
    return clientRef.current?.on(type, callback);
  }, []);

  return { joinRoom, leaveRoom, on };
}
```

### useWebSocketCacheInvalidation Hook

```typescript
// hooks/use-websocket-cache.ts
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useWebSocket } from './use-websocket';
import { MessageType } from '../lib/websocket';
import { queryKeys } from '../lib/query-keys';

export function useWebSocketCacheInvalidation() {
  const queryClient = useQueryClient();
  const { on } = useWebSocket();

  useEffect(() => {
    // Task events
    const unsubTask = on(MessageType.TASK_UPDATED, (data) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.task(data.task_id),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.tasks(data.project_id),
      });
    });

    // Comment events
    const unsubComment = on(MessageType.COMMENT_ADDED, (data) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.comments(data.task_id),
      });
    });

    // Checklist events
    const unsubChecklist = on(MessageType.CHECKLIST_UPDATED, (data) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.checklists(data.task_id),
      });
      // Also update task for denormalized counts
      queryClient.invalidateQueries({
        queryKey: queryKeys.task(data.task_id),
      });
    });

    return () => {
      unsubTask?.();
      unsubComment?.();
      unsubChecklist?.();
    };
  }, [queryClient, on]);
}
```

### usePresence Hook

```typescript
// hooks/use-presence.ts
import { useEffect, useState } from 'react';
import { useWebSocket } from './use-websocket';
import { MessageType } from '../lib/websocket';

interface UserPresence {
  user_id: string;
  display_name: string;
  avatar_url?: string;
  status: 'online' | 'away' | 'offline';
  last_seen: string;
}

export function usePresence(roomId: string) {
  const [users, setUsers] = useState<Map<string, UserPresence>>(new Map());
  const { joinRoom, leaveRoom, on } = useWebSocket();

  useEffect(() => {
    joinRoom(roomId);

    const unsub = on(MessageType.USER_PRESENCE, (data) => {
      setUsers((prev) => {
        const next = new Map(prev);
        if (data.status === 'offline') {
          next.delete(data.user_id);
        } else {
          next.set(data.user_id, data);
        }
        return next;
      });
    });

    return () => {
      leaveRoom(roomId);
      unsub?.();
    };
  }, [roomId, joinRoom, leaveRoom, on]);

  return Array.from(users.values());
}
```

## IndexedDB Persistence

### Per-Query Persister

```typescript
// lib/per-query-persister.ts
import { QueryClient } from '@tanstack/react-query';
import LZString from 'lz-string';
import { openDB, IDBPDatabase } from 'idb';

const DB_NAME = 'pm-desktop-cache';
const STORE_NAME = 'queries';
const MAX_ENTRIES = 1000;
const MAX_SIZE_BYTES = 50 * 1024 * 1024; // 50MB

interface CacheEntry {
  queryKeyHash: string;
  queryKey: unknown[];
  data: string;
  timestamp: number;
  size: number;
  compressed: boolean;
}

export function createQueryPersister() {
  let db: IDBPDatabase | null = null;

  const initDB = async () => {
    if (db) return db;

    db = await openDB(DB_NAME, 1, {
      upgrade(database) {
        const store = database.createObjectStore(STORE_NAME, {
          keyPath: 'queryKeyHash',
        });
        store.createIndex('lastAccessed', 'timestamp');
      },
    });

    return db;
  };

  const hashQueryKey = (queryKey: unknown[]): string => {
    const str = JSON.stringify(queryKey);
    // Simple hash function
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    return hash.toString(36);
  };

  const persistQuery = async (queryKey: unknown[], data: unknown) => {
    const database = await initDB();

    const serialized = JSON.stringify(data);
    const compressed = LZString.compressToUTF16(serialized);

    const entry: CacheEntry = {
      queryKeyHash: hashQueryKey(queryKey),
      queryKey,
      data: compressed,
      timestamp: Date.now(),
      size: compressed.length * 2, // UTF-16 = 2 bytes per char
      compressed: true,
    };

    await database.put(STORE_NAME, entry);
    await enforceQuota(database);
  };

  const restoreQuery = async (queryKey: unknown[]): Promise<unknown | null> => {
    const database = await initDB();
    const hash = hashQueryKey(queryKey);

    const entry = await database.get(STORE_NAME, hash);
    if (!entry) return null;

    // Update access time
    entry.timestamp = Date.now();
    await database.put(STORE_NAME, entry);

    // Decompress and parse
    const decompressed = LZString.decompressFromUTF16(entry.data);
    return decompressed ? JSON.parse(decompressed) : null;
  };

  const enforceQuota = async (database: IDBPDatabase) => {
    const tx = database.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(tx.objectStoreNames[0]);
    const index = store.index('lastAccessed');

    let cursor = await index.openCursor();
    let totalSize = 0;
    let count = 0;
    const toDelete: string[] = [];

    while (cursor) {
      count++;
      totalSize += cursor.value.size;

      // Mark for deletion if over quota
      if (count > MAX_ENTRIES || totalSize > MAX_SIZE_BYTES) {
        toDelete.push(cursor.value.queryKeyHash);
      }

      cursor = await cursor.continue();
    }

    // Delete oldest entries
    for (const key of toDelete) {
      await store.delete(key);
    }

    await tx.done;
  };

  const clearAll = async () => {
    const database = await initDB();
    await database.clear(STORE_NAME);
  };

  const restoreQueries = async (queryClient: QueryClient) => {
    const database = await initDB();
    const entries = await database.getAll(STORE_NAME);

    for (const entry of entries) {
      try {
        const decompressed = LZString.decompressFromUTF16(entry.data);
        if (decompressed) {
          const data = JSON.parse(decompressed);
          queryClient.setQueryData(entry.queryKey, data);
        }
      } catch (e) {
        // Skip corrupted entries
        console.warn('Failed to restore query:', entry.queryKey);
      }
    }
  };

  return {
    persistQuery,
    restoreQuery,
    restoreQueries,
    clearAll,
  };
}
```

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
/* src/renderer/index.css */
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

## Testing

### Test Setup

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/renderer/__tests__/setup.ts'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src/renderer'),
    },
  },
});
```

```typescript
// src/renderer/__tests__/setup.ts
import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});
```

### Example Tests

```typescript
// src/renderer/__tests__/auth-context.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider, useAuth } from '../contexts/auth-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

function TestComponent() {
  const { user, login, logout } = useAuth();
  return (
    <div>
      {user ? (
        <>
          <span>Logged in as {user.display_name}</span>
          <button onClick={logout}>Logout</button>
        </>
      ) : (
        <button onClick={() => login('test@example.com', 'password')}>
          Login
        </button>
      )}
    </div>
  );
}

describe('AuthContext', () => {
  it('shows login button when not authenticated', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      </QueryClientProvider>
    );

    expect(screen.getByText('Login')).toBeInTheDocument();
  });

  it('shows user name after login', async () => {
    // Mock API responses
    vi.spyOn(api, 'login').mockResolvedValue({ access_token: 'token' });
    vi.spyOn(api, 'getCurrentUser').mockResolvedValue({
      id: '1',
      display_name: 'Test User',
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      </QueryClientProvider>
    );

    await userEvent.click(screen.getByText('Login'));

    await waitFor(() => {
      expect(screen.getByText('Logged in as Test User')).toBeInTheDocument();
    });
  });
});
```

### Running Tests

```bash
# Run all tests
npm test

# Run tests in watch mode
npm test -- --watch

# Run tests with coverage
npm test -- --coverage

# Run specific test file
npm test -- src/renderer/__tests__/auth-context.test.tsx
```
