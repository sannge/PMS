/**
 * Chat Session List
 *
 * Displays a filterable, date-grouped list of past chat sessions.
 * Supports rename, archive, and delete actions via dropdown menu.
 */

import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { MoreHorizontal, MessageSquare, Pencil, Archive, Trash2, Loader2 } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useChatSessions, useUpdateSession, useDeleteSession } from '@/hooks/use-chat-sessions'
import type { ChatSessionSummary } from './types'

// ============================================================================
// Date Grouping
// ============================================================================

type DateGroup = 'Today' | 'Yesterday' | 'Previous 7 Days' | 'Older'

function getDateGroup(dateStr: string): DateGroup {
  const date = new Date(dateStr)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const weekAgo = new Date(today)
  weekAgo.setDate(weekAgo.getDate() - 7)

  if (date >= today) return 'Today'
  if (date >= yesterday) return 'Yesterday'
  if (date >= weekAgo) return 'Previous 7 Days'
  return 'Older'
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = Date.now()
  const diff = now - date.getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return date.toLocaleDateString()
}

// ============================================================================
// Skeleton
// ============================================================================

function SessionListSkeleton(): JSX.Element {
  return (
    <div className="space-y-3 p-4">
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="space-y-1.5 py-2">
          <Skeleton className="h-3.5 w-3/4" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-2.5 w-1/4" />
        </div>
      ))}
    </div>
  )
}

// ============================================================================
// Busy Row (shared for deleting/archiving/renaming states)
// ============================================================================

function BusyRow({ label }: { label: string }): JSX.Element {
  return (
    <div className="w-full rounded-lg px-3 py-2.5 opacity-50 pointer-events-none">
      <div className="flex items-center gap-2">
        <Loader2 className="h-3.5 w-3.5 text-muted-foreground animate-spin shrink-0" />
        <p className="text-sm text-muted-foreground truncate">{label}</p>
      </div>
    </div>
  )
}

// ============================================================================
// Session Row
// ============================================================================

type BusyState = 'deleting' | 'archiving' | 'renaming' | null

interface SessionRowProps {
  session: ChatSessionSummary
  busyState: BusyState
  onSelect: (session: ChatSessionSummary) => void
  onRename: (id: string, title: string) => void
  onArchive: (id: string) => void
  onDelete: (id: string) => void
}

const SessionRow = React.memo(function SessionRow({ session, busyState, onSelect, onRename, onArchive, onDelete }: SessionRowProps): JSX.Element {
  const [isEditing, setIsEditing] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isEditing) inputRef.current?.focus()
  }, [isEditing])

  const handleRenameSubmit = useCallback(() => {
    const newTitle = inputRef.current?.value.trim()
    if (newTitle && newTitle !== session.title) {
      onRename(session.id, newTitle)
    }
    setIsEditing(false)
  }, [session.id, session.title, onRename])

  if (busyState) {
    const labels: Record<string, string> = {
      deleting: 'Deleting...',
      archiving: 'Archiving...',
      renaming: 'Renaming...',
    }
    return <BusyRow label={labels[busyState]} />
  }

  return (
    <button
      type="button"
      onClick={() => !isEditing && onSelect(session)}
      className={cn(
        'group w-full text-left rounded-lg px-3 py-2.5',
        'hover:bg-muted/60 transition-colors duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {isEditing ? (
            <input
              ref={inputRef}
              defaultValue={session.title}
              onBlur={handleRenameSubmit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRenameSubmit()
                if (e.key === 'Escape') setIsEditing(false)
              }}
              className="w-full bg-transparent text-sm font-medium border-b border-primary outline-none"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <p className="text-sm font-medium text-foreground truncate">{session.title}</p>
          )}
          {session.lastMessagePreview && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">
              {session.lastMessagePreview}
            </p>
          )}
          <p className="text-[10px] text-muted-foreground/60 mt-1">
            {formatRelativeTime(session.updatedAt)}
          </p>
        </div>

        <div className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="h-6 w-6 flex items-center justify-center rounded hover:bg-muted"
              >
                <MoreHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-36">
              <DropdownMenuItem onClick={() => setIsEditing(true)}>
                <Pencil className="h-3.5 w-3.5 mr-2" />
                Rename
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onArchive(session.id)}>
                <Archive className="h-3.5 w-3.5 mr-2" />
                Archive
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => onDelete(session.id)}
              >
                <Trash2 className="h-3.5 w-3.5 mr-2" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </button>
  )
})

// ============================================================================
// Chat Session List
// ============================================================================

interface ChatSessionListProps {
  onSelectSession: (session: ChatSessionSummary) => void
}

export function ChatSessionList({ onSelectSession }: ChatSessionListProps): JSX.Element {
  const [filter, setFilter] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [archiveTarget, setArchiveTarget] = useState<string | null>(null)
  // Track per-session busy state: id -> 'deleting' | 'archiving' | 'renaming'
  const [busyMap, setBusyMap] = useState<Map<string, BusyState>>(new Map())
  const { data, isLoading } = useChatSessions()
  const updateSession = useUpdateSession()
  const deleteSession = useDeleteSession()

  const sessions: ChatSessionSummary[] = data?.sessions ?? []

  const filtered = useMemo(() => {
    if (!filter.trim()) return sessions
    const lower = filter.toLowerCase()
    return sessions.filter(
      (s) => s.title.toLowerCase().includes(lower) || s.lastMessagePreview.toLowerCase().includes(lower)
    )
  }, [sessions, filter])

  const grouped = useMemo(() => {
    const groups: Record<DateGroup, ChatSessionSummary[]> = {
      Today: [],
      Yesterday: [],
      'Previous 7 Days': [],
      Older: [],
    }
    for (const s of filtered) {
      groups[getDateGroup(s.updatedAt)].push(s)
    }
    return groups
  }, [filtered])

  const setBusy = useCallback((id: string, state: BusyState) => {
    setBusyMap((prev) => {
      const next = new Map(prev)
      if (state) next.set(id, state)
      else next.delete(id)
      return next
    })
  }, [])

  const handleRename = useCallback(
    (id: string, title: string) => {
      setBusy(id, 'renaming')
      updateSession.mutate(
        { id, data: { title } },
        { onSettled: () => setBusy(id, null) },
      )
    },
    [updateSession, setBusy]
  )

  const handleArchive = useCallback(
    (id: string) => setArchiveTarget(id),
    []
  )

  const confirmArchive = useCallback(() => {
    if (archiveTarget) {
      const id = archiveTarget
      setBusy(id, 'archiving')
      updateSession.mutate(
        { id, data: { is_archived: true } },
        { onSettled: () => setBusy(id, null) },
      )
      setArchiveTarget(null)
    }
  }, [archiveTarget, updateSession, setBusy])

  const handleDelete = useCallback(
    (id: string) => setDeleteTarget(id),
    []
  )

  const confirmDelete = useCallback(() => {
    if (deleteTarget) {
      const id = deleteTarget
      setBusy(id, 'deleting')
      deleteSession.mutate(id, {
        onSettled: () => setBusy(id, null),
      })
      setDeleteTarget(null)
    }
  }, [deleteTarget, deleteSession, setBusy])

  if (isLoading) return <SessionListSkeleton />

  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
        <div className="h-12 w-12 rounded-xl bg-muted/50 flex items-center justify-center mb-3">
          <MessageSquare className="h-6 w-6 text-muted-foreground/50" />
        </div>
        <p className="text-sm font-medium text-muted-foreground">No conversations yet</p>
        <p className="text-xs text-muted-foreground/60 mt-1">Start chatting with Blair to see your history</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Filter */}
      <div className="px-4 pt-3 pb-2 shrink-0">
        <input
          type="text"
          placeholder="Search conversations..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className={cn(
            'w-full h-8 px-3 rounded-lg text-xs',
            'bg-muted/50 border border-border/40',
            'placeholder:text-muted-foreground/50',
            'focus:outline-none focus:ring-1 focus:ring-ring',
          )}
        />
      </div>

      {/* Session List */}
      <ScrollArea className="flex-1">
        <div className="px-2 pb-4">
          {(['Today', 'Yesterday', 'Previous 7 Days', 'Older'] as DateGroup[]).map((group) => {
            const items = grouped[group]
            if (items.length === 0) return null
            return (
              <div key={group} className="mt-2">
                <p className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/50 px-3 py-1">
                  {group}
                </p>
                {items.map((session) => (
                  <SessionRow
                    key={session.id}
                    session={session}
                    busyState={busyMap.get(session.id) ?? null}
                    onSelect={onSelectSession}
                    onRename={handleRename}
                    onArchive={handleArchive}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )
          })}
        </div>
      </ScrollArea>

      {/* Archive confirmation dialog */}
      <ConfirmDialog
        open={archiveTarget !== null}
        onOpenChange={(open) => { if (!open) setArchiveTarget(null) }}
        title="Archive conversation"
        description="This conversation will be archived and hidden from your list. You can find it later in archived conversations."
        confirmLabel="Archive"
        onConfirm={confirmArchive}
      />

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null) }}
        title="Delete conversation"
        description="This will permanently delete this conversation and all its messages."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={confirmDelete}
      />
    </div>
  )
}
