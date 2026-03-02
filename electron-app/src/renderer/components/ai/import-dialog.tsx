/**
 * Document Import Dialog
 *
 * Allows users to upload PDF/DOCX/PPTX files for import into the
 * knowledge base. Features drag-and-drop upload, progress tracking,
 * and step-by-step status indicators.
 *
 * Two states:
 * 1. Upload: File drop zone, title input, scope/folder selectors
 * 2. Progress: Step indicators with polling progress bar
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Upload, FileText, CheckCircle2, Loader2, XCircle, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import {
  useImportDocument,
  useImportJobStatus,
  type ImportJobResponse,
} from '@/hooks/use-document-import'

// ============================================================================
// Constants
// ============================================================================

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.pptx']
const ACCEPTED_MIME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
]
const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50MB
const AUTO_CLOSE_DELAY = 3000

// ============================================================================
// Types
// ============================================================================

interface ImportDialogProps {
  /** Currently active scope for pre-filling */
  defaultScope?: 'application' | 'project' | 'personal'
  defaultScopeId?: string
  defaultFolderId?: string
  /** Trigger element (button to open dialog) */
  trigger?: React.ReactNode
  /** Called when import completes successfully */
  onImportComplete?: (documentId: string) => void
}

type ImportStep = {
  label: string
  threshold: number
}

const IMPORT_STEPS: ImportStep[] = [
  { label: 'File uploaded', threshold: 10 },
  { label: 'Converting to markdown', threshold: 40 },
  { label: 'Processing images', threshold: 60 },
  { label: 'Creating document', threshold: 80 },
  { label: 'Generating embeddings', threshold: 100 },
]

// ============================================================================
// Helpers
// ============================================================================

/**
 * Strip extension from filename and replace hyphens/underscores with spaces.
 */
function titleFromFilename(filename: string): string {
  const withoutExtension = filename.replace(/\.[^.]+$/, '')
  return withoutExtension.replace(/[-_]/g, ' ')
}

/**
 * Validate that the file has an accepted extension and is within size limits.
 */
function validateFile(file: File): string | null {
  const extension = '.' + file.name.split('.').pop()?.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.includes(extension)) {
    return `Unsupported file type. Supported: ${ACCEPTED_EXTENSIONS.join(', ')}`
  }
  if (file.size > MAX_FILE_SIZE) {
    return `File too large. Maximum size is ${MAX_FILE_SIZE / (1024 * 1024)}MB.`
  }
  return null
}

/**
 * Determine the current step index based on progress percentage.
 */
function getCurrentStepIndex(progressPct: number): number {
  for (let i = IMPORT_STEPS.length - 1; i >= 0; i--) {
    if (progressPct >= IMPORT_STEPS[i].threshold) {
      return i
    }
  }
  return -1
}

// ============================================================================
// Step Indicator Component
// ============================================================================

function StepIndicator({
  label,
  status,
}: {
  label: string
  status: 'done' | 'active' | 'pending'
}) {
  return (
    <div className="flex items-center gap-2 py-1">
      {status === 'done' && (
        <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
      )}
      {status === 'active' && (
        <Loader2 className="h-4 w-4 text-primary shrink-0 animate-spin" />
      )}
      {status === 'pending' && (
        <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/30 shrink-0" />
      )}
      <span
        className={cn(
          'text-sm',
          status === 'done' && 'text-muted-foreground',
          status === 'active' && 'text-foreground font-medium',
          status === 'pending' && 'text-muted-foreground/50'
        )}
      >
        {label}
      </span>
    </div>
  )
}

// ============================================================================
// Progress View Component
// ============================================================================

function ProgressView({
  jobStatus,
  onOpenDocument,
  onRetry,
}: {
  jobStatus: ImportJobResponse
  onOpenDocument: () => void
  onRetry: () => void
}) {
  const currentStepIndex = getCurrentStepIndex(jobStatus.progress_pct)
  const isCompleted = jobStatus.status === 'completed'
  const isFailed = jobStatus.status === 'failed'

  return (
    <div className="space-y-4">
      {/* Progress bar */}
      {!isFailed && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {isCompleted ? 'Import complete' : 'Importing...'}
            </span>
            <span className="text-muted-foreground font-mono">
              {Math.round(jobStatus.progress_pct)}%
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500 ease-out',
                isCompleted ? 'bg-green-500' : 'bg-primary'
              )}
              style={{ width: `${jobStatus.progress_pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Error message */}
      {isFailed && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3">
          <XCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="text-sm font-medium text-destructive">Import failed</p>
            <p className="text-sm text-destructive/80">
              {jobStatus.error_message || 'An unexpected error occurred during import.'}
            </p>
          </div>
        </div>
      )}

      {/* Steps */}
      <div className="space-y-0.5">
        <p className="text-sm font-medium mb-2">Steps:</p>
        {IMPORT_STEPS.map((step, index) => {
          let status: 'done' | 'active' | 'pending' = 'pending'
          if (isFailed) {
            // On failure, mark completed steps as done, current as failed
            if (index < currentStepIndex) {
              status = 'done'
            } else if (index === currentStepIndex) {
              status = 'active'
            }
          } else if (isCompleted) {
            status = 'done'
          } else if (index < currentStepIndex) {
            status = 'done'
          } else if (index === currentStepIndex) {
            status = 'active'
          }
          return (
            <StepIndicator key={step.label} label={step.label} status={status} />
          )
        })}
      </div>

      {/* Action buttons */}
      {isCompleted && (
        <div className="flex justify-end">
          <Button onClick={onOpenDocument} size="sm">
            Open Document
          </Button>
        </div>
      )}
      {isFailed && (
        <div className="flex justify-end">
          <Button onClick={onRetry} variant="outline" size="sm">
            Try Again
          </Button>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Drop Zone Component
// ============================================================================

function DropZone({
  file,
  onFileSelect,
  onFileClear,
  validationError,
}: {
  file: File | null
  onFileSelect: (file: File) => void
  onFileClear: () => void
  validationError: string | null
}) {
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragOver(false)

      const droppedFile = e.dataTransfer.files[0]
      if (droppedFile) {
        onFileSelect(droppedFile)
      }
    },
    [onFileSelect]
  )

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFile = e.target.files?.[0]
      if (selectedFile) {
        onFileSelect(selectedFile)
      }
      // Reset input value so the same file can be re-selected
      e.target.value = ''
    },
    [onFileSelect]
  )

  const handleClick = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  return (
    <div className="space-y-2">
      <div
        role="button"
        tabIndex={0}
        onClick={handleClick}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            handleClick()
          }
        }}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          'flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 transition-colors cursor-pointer',
          isDragOver
            ? 'border-primary bg-primary/5'
            : 'border-muted-foreground/25 hover:border-muted-foreground/50',
          validationError && 'border-destructive/50'
        )}
      >
        {file ? (
          <>
            <FileText className="h-10 w-10 text-primary" />
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{file.name}</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onFileClear()
                }}
                className="rounded-full p-0.5 hover:bg-muted"
                aria-label="Remove file"
              >
                <X className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            </div>
            <span className="text-xs text-muted-foreground">
              {(file.size / (1024 * 1024)).toFixed(1)} MB
            </span>
          </>
        ) : (
          <>
            <Upload className="h-10 w-10 text-muted-foreground" />
            <p className="text-sm font-medium">Drop file here or click to browse</p>
            <p className="text-xs text-muted-foreground">
              Supports: PDF, DOCX, PPTX &mdash; Max size: 50MB
            </p>
          </>
        )}
      </div>

      {validationError && (
        <p className="text-sm text-destructive">{validationError}</p>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_MIME_TYPES.join(',')}
        onChange={handleInputChange}
        className="hidden"
        aria-hidden="true"
      />
    </div>
  )
}

// ============================================================================
// Import Dialog Component
// ============================================================================

export function ImportDialog({
  defaultScope = 'application',
  defaultScopeId = '',
  defaultFolderId,
  trigger,
  onImportComplete,
}: ImportDialogProps) {
  // Dialog state
  const [open, setOpen] = useState(false)

  // Upload form state
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [scope, setScope] = useState<string>(defaultScope)
  const [scopeId] = useState(defaultScopeId)
  const [folderId] = useState(defaultFolderId ?? '')
  const [validationError, setValidationError] = useState<string | null>(null)

  // Import job state
  const [activeJobId, setActiveJobId] = useState<string | null>(null)

  // Auto-close timer ref
  const autoCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Hooks
  const importMutation = useImportDocument()
  const { data: jobStatus } = useImportJobStatus(activeJobId)

  // ---- Reset state when dialog closes ----
  const resetState = useCallback(() => {
    setFile(null)
    setTitle('')
    setScope(defaultScope)
    setValidationError(null)
    setActiveJobId(null)
    importMutation.reset()
    if (autoCloseTimerRef.current) {
      clearTimeout(autoCloseTimerRef.current)
      autoCloseTimerRef.current = null
    }
  }, [defaultScope, importMutation])

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      setOpen(nextOpen)
      if (!nextOpen) {
        resetState()
      }
    },
    [resetState]
  )

  // ---- File selection ----
  const handleFileSelect = useCallback((selectedFile: File) => {
    const error = validateFile(selectedFile)
    if (error) {
      setValidationError(error)
      setFile(null)
      return
    }
    setValidationError(null)
    setFile(selectedFile)
    setTitle(titleFromFilename(selectedFile.name))
  }, [])

  const handleFileClear = useCallback(() => {
    setFile(null)
    setTitle('')
    setValidationError(null)
  }, [])

  // ---- Import submission ----
  const handleImport = useCallback(() => {
    if (!file || !title.trim() || !scope || !scopeId) return

    importMutation.mutate(
      {
        file,
        title: title.trim(),
        scope,
        scope_id: scopeId,
        folder_id: folderId || null,
      },
      {
        onSuccess: (data) => {
          setActiveJobId(data.job_id)
        },
        onError: (error) => {
          toast.error(error.message || 'Failed to start import')
        },
      }
    )
  }, [file, title, scope, scopeId, folderId, importMutation])

  // ---- Auto-close on success ----
  useEffect(() => {
    if (jobStatus?.status === 'completed' && jobStatus.document_id) {
      autoCloseTimerRef.current = setTimeout(() => {
        onImportComplete?.(jobStatus.document_id as string)
        handleOpenChange(false)
      }, AUTO_CLOSE_DELAY)
    }

    return () => {
      if (autoCloseTimerRef.current) {
        clearTimeout(autoCloseTimerRef.current)
      }
    }
  }, [jobStatus?.status, jobStatus?.document_id, onImportComplete, handleOpenChange])

  // ---- Retry after failure ----
  const handleRetry = useCallback(() => {
    setActiveJobId(null)
    importMutation.reset()
  }, [importMutation])

  // ---- Open document ----
  const handleOpenDocument = useCallback(() => {
    if (jobStatus?.document_id) {
      onImportComplete?.(jobStatus.document_id)
      handleOpenChange(false)
    }
  }, [jobStatus?.document_id, onImportComplete, handleOpenChange])

  // ---- Derived state ----
  const isUploading = importMutation.isPending
  const showProgress = !!activeJobId
  const canImport = !!file && !!title.trim() && !!scope && !!scopeId && !isUploading

  // ---- Dialog title ----
  const dialogTitle = showProgress
    ? `Importing: ${file?.name ?? 'document'}`
    : 'Import Document'

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      {trigger ? (
        <DialogTrigger asChild>{trigger}</DialogTrigger>
      ) : (
        <DialogTrigger asChild>
          <Button variant="outline" size="sm">
            <Upload className="h-4 w-4 mr-2" />
            Import
          </Button>
        </DialogTrigger>
      )}

      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{dialogTitle}</DialogTitle>
        </DialogHeader>

        {showProgress && jobStatus ? (
          <ProgressView
            jobStatus={jobStatus}
            onOpenDocument={handleOpenDocument}
            onRetry={handleRetry}
          />
        ) : (
          <div className="space-y-4">
            {/* Drop zone */}
            <DropZone
              file={file}
              onFileSelect={handleFileSelect}
              onFileClear={handleFileClear}
              validationError={validationError}
            />

            {/* Title */}
            <div className="space-y-2">
              <Label htmlFor="import-title">Title</Label>
              <Input
                id="import-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Document title"
                disabled={isUploading}
              />
            </div>

            {/* Scope */}
            <div className="space-y-2">
              <Label htmlFor="import-scope">Scope</Label>
              <Select value={scope} onValueChange={setScope} disabled={isUploading}>
                <SelectTrigger id="import-scope">
                  <SelectValue placeholder="Select scope" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="application">Application</SelectItem>
                  <SelectItem value="project">Project</SelectItem>
                  <SelectItem value="personal">Personal</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Footer with actions */}
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => handleOpenChange(false)}
                disabled={isUploading}
              >
                Cancel
              </Button>
              <Button onClick={handleImport} disabled={!canImport}>
                {isUploading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  'Import'
                )}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
