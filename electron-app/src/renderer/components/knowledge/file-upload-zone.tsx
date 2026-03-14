/**
 * File Upload Zone
 *
 * Drag-and-drop + button component for uploading files to a folder.
 * Uses HTML5 drag events and a hidden file input.
 * Sequentially uploads files with progress tracking.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { Upload, Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUploadFile, type UploadConflictError } from '@/hooks/use-folder-files'
import { toast } from 'sonner'

// ============================================================================
// Types
// ============================================================================

interface FileUploadZoneProps {
  folderId: string
  /** Called when a 409 conflict is returned for a file */
  onConflict?: (file: File, folderId: string, existingFileId?: string) => void
  /** Compact mode: just a button, no drop zone */
  compact?: boolean
}

interface UploadProgress {
  fileName: string
  status: 'uploading' | 'done' | 'error'
  error?: string
}

// ============================================================================
// Component
// ============================================================================

export function FileUploadZone({
  folderId,
  onConflict,
  compact = false,
}: FileUploadZoneProps): JSX.Element {
  const [isDragOver, setIsDragOver] = useState(false)
  const [uploads, setUploads] = useState<UploadProgress[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const uploadFile = useUploadFile()

  // MED-3: Track timer with useRef, clear in useEffect cleanup
  const clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (clearTimerRef.current !== null) {
        clearTimeout(clearTimerRef.current)
        clearTimerRef.current = null
      }
    }
  }, [])

  const processFiles = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files)
      if (fileArray.length === 0) return

      setIsUploading(true)
      const progressList: UploadProgress[] = fileArray.map((f) => ({
        fileName: f.name,
        status: 'uploading' as const,
      }))
      setUploads(progressList)

      // Sequential upload
      for (let i = 0; i < fileArray.length; i++) {
        const file = fileArray[i]
        try {
          await uploadFile.mutateAsync({ file, folderId })
          setUploads((prev) =>
            prev.map((p, idx) =>
              idx === i ? { ...p, status: 'done' as const } : p
            )
          )
        } catch (err) {
          const error = err as UploadConflictError
          if (error.status === 409 && onConflict) {
            onConflict(file, folderId, error.existingFileId)
            setUploads((prev) =>
              prev.map((p, idx) =>
                idx === i ? { ...p, status: 'error' as const, error: 'File exists' } : p
              )
            )
          } else {
            toast.error(`Failed to upload ${file.name}: ${error.message}`)
            setUploads((prev) =>
              prev.map((p, idx) =>
                idx === i ? { ...p, status: 'error' as const, error: error.message } : p
              )
            )
          }
        }
      }

      setIsUploading(false)
      // Clear progress after a delay (tracked for cleanup)
      if (clearTimerRef.current !== null) {
        clearTimeout(clearTimerRef.current)
      }
      clearTimerRef.current = setTimeout(() => {
        setUploads([])
        clearTimerRef.current = null
      }, 3000)
    },
    [folderId, uploadFile, onConflict]
  )

  // LOW-1: Consolidated drag handler for dragEnter and dragOver (identical logic)
  const handleDragActive = useCallback((e: React.DragEvent) => {
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

      const { files } = e.dataTransfer
      if (files.length > 0) {
        processFiles(files)
      }
    },
    [processFiles]
  )

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (files && files.length > 0) {
        processFiles(files)
      }
      // Reset input value so the same files can be re-selected
      e.target.value = ''
    },
    [processFiles]
  )

  const handleClick = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  if (compact) {
    return (
      <>
        <button
          onClick={handleClick}
          disabled={isUploading}
          className={cn(
            'inline-flex items-center gap-1.5 px-2 py-1 text-xs rounded-md',
            'text-muted-foreground hover:text-foreground hover:bg-accent',
            'transition-colors disabled:opacity-50'
          )}
        >
          {isUploading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Upload className="h-3.5 w-3.5" />
          )}
          Upload Files
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleInputChange}
          className="hidden"
          aria-hidden="true"
        />
      </>
    )
  }

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
        onDragEnter={handleDragActive}
        onDragOver={handleDragActive}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          'flex flex-col items-center justify-center gap-1.5 rounded-md border-2 border-dashed p-4 transition-colors cursor-pointer',
          isDragOver
            ? 'border-primary bg-primary/5'
            : 'border-muted-foreground/25 hover:border-muted-foreground/50',
          isUploading && 'pointer-events-none opacity-60'
        )}
      >
        {isUploading ? (
          <Loader2 className="h-6 w-6 text-primary animate-spin" />
        ) : (
          <Upload className="h-6 w-6 text-muted-foreground" />
        )}
        <p className="text-xs font-medium text-muted-foreground">
          {isUploading ? 'Uploading...' : 'Drop files here or click to upload'}
        </p>
      </div>

      {/* Upload progress list */}
      {uploads.length > 0 && (
        <div className="space-y-1">
          {uploads.map((upload, idx) => (
            <div
              key={`${upload.fileName}-${idx}`}
              className="flex items-center gap-2 text-xs px-1"
            >
              {upload.status === 'uploading' && (
                <Loader2 className="h-3 w-3 text-primary animate-spin shrink-0" />
              )}
              {upload.status === 'done' && (
                <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0" />
              )}
              {upload.status === 'error' && (
                <XCircle className="h-3 w-3 text-destructive shrink-0" />
              )}
              <span className="truncate text-muted-foreground">{upload.fileName}</span>
            </div>
          ))}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        onChange={handleInputChange}
        className="hidden"
        aria-hidden="true"
      />
    </div>
  )
}

export default FileUploadZone
