/**
 * Scope Picker Dialog
 *
 * Lets the user choose a scope (personal, application, or project) before
 * creating a document. Shown when creating from "All Documents" where no
 * real scope exists.
 */

import { useState } from 'react'
import { User, Building2, FolderKanban } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useApplications, useProjects, type Application } from '@/hooks/use-queries'
import { useAuthStore } from '@/contexts/auth-context'

// ============================================================================
// Types
// ============================================================================

interface ScopePickerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (scope: string, scopeId: string) => void
}

interface ScopeSelection {
  scope: string
  scopeId: string
}

// ============================================================================
// Project Items (lazy-loaded per application)
// ============================================================================

function ProjectItems({
  application,
  selected,
  onSelect,
}: {
  application: Application
  selected: ScopeSelection | null
  onSelect: (selection: ScopeSelection) => void
}): JSX.Element | null {
  const { data: projects } = useProjects(application.id)

  if (!projects || projects.length === 0) return null

  return (
    <>
      {projects.map((project) => {
        const isSelected =
          selected?.scope === 'project' && selected.scopeId === project.id
        return (
          <button
            key={project.id}
            type="button"
            onClick={() => onSelect({ scope: 'project', scopeId: project.id })}
            className={cn(
              'flex items-center gap-2 w-full text-left px-3 py-2 rounded-md cursor-pointer text-sm',
              'hover:bg-accent',
              isSelected && 'bg-accent text-accent-foreground'
            )}
          >
            <FolderKanban className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="truncate">
              {application.name} / {project.name}
            </span>
          </button>
        )
      })}
    </>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function ScopePickerDialog({
  open,
  onOpenChange,
  onConfirm,
}: ScopePickerDialogProps): JSX.Element {
  const user = useAuthStore((s) => s.user)
  const { data: applications } = useApplications()

  const [selected, setSelected] = useState<ScopeSelection | null>(null)

  const handleConfirm = (): void => {
    if (!selected) return
    onConfirm(selected.scope, selected.scopeId)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Choose scope</DialogTitle>
          <DialogDescription>
            Select where to create your document
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-0.5 max-h-64 overflow-y-auto py-1">
          {/* Personal notes */}
          {user && (
            <button
              type="button"
              onClick={() =>
                setSelected({ scope: 'personal', scopeId: user.id })
              }
              className={cn(
                'flex items-center gap-2 w-full text-left px-3 py-2 rounded-md cursor-pointer text-sm',
                'hover:bg-accent',
                selected?.scope === 'personal' &&
                  'bg-accent text-accent-foreground'
              )}
            >
              <User className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span>My Notes</span>
            </button>
          )}

          {/* Applications and their projects */}
          {applications?.map((app) => (
            <div key={app.id}>
              <button
                type="button"
                onClick={() =>
                  setSelected({ scope: 'application', scopeId: app.id })
                }
                className={cn(
                  'flex items-center gap-2 w-full text-left px-3 py-2 rounded-md cursor-pointer text-sm',
                  'hover:bg-accent',
                  selected?.scope === 'application' &&
                    selected.scopeId === app.id &&
                    'bg-accent text-accent-foreground'
                )}
              >
                <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{app.name}</span>
              </button>
              <ProjectItems
                application={app}
                selected={selected}
                onSelect={setSelected}
              />
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            disabled={!selected}
            onClick={handleConfirm}
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
