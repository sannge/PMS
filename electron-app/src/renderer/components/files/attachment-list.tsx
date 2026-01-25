/**
 * Attachment List Component
 *
 * Displays a list of file attachments with actions.
 *
 * Features:
 * - Grid or list view
 * - File type icons
 * - Preview on click
 * - Download action
 * - Delete action (with confirmation)
 * - Loading states
 * - Empty state
 */

import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils'
import {
  File,
  FileImage,
  FileVideo,
  FileAudio,
  FileText,
  FileCode,
  FileArchive,
  Download,
  Trash2,
  Loader2,
  MoreVertical,
  Eye,
  Grid,
  List,
  Paperclip,
} from 'lucide-react'
import {
  type Attachment,
  type EntityType,
  useFilesStore,
  formatFileSize,
  isImageFile,
  getFileIconType,
} from '@/stores/files-store'
import { FilePreview } from './file-preview'
import { wsClient, MessageType } from '@/lib/websocket'
import { SkeletonAttachments } from '@/components/ui/skeleton'
import { DeleteFileDialog } from '@/components/ui/confirm-dialog'

// ============================================================================
// Types
// ============================================================================

export interface AttachmentListProps {
  /**
   * Entity type
   */
  entityType: EntityType
  /**
   * Entity ID
   */
  entityId: string
  /**
   * View mode
   */
  viewMode?: 'grid' | 'list'
  /**
   * Whether to show view mode toggle
   */
  showViewToggle?: boolean
  /**
   * Whether to allow deletion
   */
  allowDelete?: boolean
  /**
   * Optional className
   */
  className?: string
  /**
   * Compact mode for embedded usage
   */
  compact?: boolean
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get icon component for file type
 */
function getFileIcon(fileType: string | null, fileName: string, size: 'sm' | 'md' | 'lg' = 'md'): JSX.Element {
  const iconType = getFileIconType(fileType, fileName)
  const sizeClass = size === 'sm' ? 'h-4 w-4' : size === 'lg' ? 'h-8 w-8' : 'h-5 w-5'

  switch (iconType) {
    case 'image':
      return <FileImage className={cn(sizeClass, 'text-blue-500')} />
    case 'video':
      return <FileVideo className={cn(sizeClass, 'text-purple-500')} />
    case 'audio':
      return <FileAudio className={cn(sizeClass, 'text-green-500')} />
    case 'pdf':
      return <FileText className={cn(sizeClass, 'text-red-500')} />
    case 'word':
    case 'text':
      return <FileText className={cn(sizeClass, 'text-blue-600')} />
    case 'excel':
      return <FileText className={cn(sizeClass, 'text-green-600')} />
    case 'powerpoint':
      return <FileText className={cn(sizeClass, 'text-orange-500')} />
    case 'archive':
      return <FileArchive className={cn(sizeClass, 'text-yellow-600')} />
    case 'code':
      return <FileCode className={cn(sizeClass, 'text-slate-600')} />
    default:
      return <File className={cn(sizeClass, 'text-muted-foreground')} />
  }
}

/**
 * Format date for display
 */
function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

// ============================================================================
// Sub-Components
// ============================================================================

interface AttachmentGridItemProps {
  attachment: Attachment
  onPreview: () => void
  onDownload: () => void
  onDelete?: () => void
  isDeleting?: boolean
  previewUrl?: string | null
}

function AttachmentGridItem({
  attachment,
  onPreview,
  onDownload,
  onDelete,
  isDeleting,
  previewUrl,
}: AttachmentGridItemProps): JSX.Element {
  const [showMenu, setShowMenu] = useState(false)

  const isImage = isImageFile(attachment.file_type)

  return (
    <div
      className={cn(
        'group relative rounded-lg border border-border bg-card overflow-hidden',
        'transition-all hover:border-primary/50 hover:shadow-md',
        isDeleting && 'opacity-50 pointer-events-none'
      )}
    >
      {/* Thumbnail or Icon */}
      <div
        onClick={onPreview}
        className="relative h-32 cursor-pointer bg-muted flex items-center justify-center"
      >
        {isImage && previewUrl ? (
          <img
            src={previewUrl}
            alt={attachment.file_name}
            className="h-full w-full object-cover"
          />
        ) : (
          getFileIcon(attachment.file_type, attachment.file_name, 'lg')
        )}

        {/* Overlay on hover */}
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
          <Eye className="h-8 w-8 text-white" />
        </div>
      </div>

      {/* Info */}
      <div className="p-3">
        <p className="text-sm font-medium text-foreground truncate" title={attachment.file_name}>
          {attachment.file_name}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {formatFileSize(attachment.file_size)}
        </p>
      </div>

      {/* Actions Menu */}
      <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="rounded-md p-1.5 bg-background/90 border border-border text-muted-foreground hover:text-foreground transition-colors"
          >
            <MoreVertical className="h-4 w-4" />
          </button>

          {showMenu && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowMenu(false)}
              />
              <div className="absolute right-0 top-full mt-1 z-20 min-w-[140px] rounded-md border border-border bg-popover shadow-md py-1">
                <button
                  onClick={() => {
                    onPreview()
                    setShowMenu(false)
                  }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-sm text-foreground hover:bg-accent"
                >
                  <Eye className="h-4 w-4" />
                  Preview
                </button>
                <button
                  onClick={() => {
                    onDownload()
                    setShowMenu(false)
                  }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-sm text-foreground hover:bg-accent"
                >
                  <Download className="h-4 w-4" />
                  Download
                </button>
                {onDelete && (
                  <>
                    <div className="my-1 h-px bg-border" />
                    <button
                      onClick={() => {
                        onDelete()
                        setShowMenu(false)
                      }}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10"
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Deleting indicator */}
      {isDeleting && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/50">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}
    </div>
  )
}

interface AttachmentListItemProps {
  attachment: Attachment
  onPreview: () => void
  onDownload: () => void
  onDelete?: () => void
  isDeleting?: boolean
}

function AttachmentListItem({
  attachment,
  onPreview,
  onDownload,
  onDelete,
  isDeleting,
}: AttachmentListItemProps): JSX.Element {
  return (
    <div
      className={cn(
        'group flex items-center gap-3 rounded-md border border-border bg-card p-3',
        'transition-all hover:border-primary/50',
        isDeleting && 'opacity-50 pointer-events-none'
      )}
    >
      {/* Icon */}
      <div className="flex-shrink-0">
        {getFileIcon(attachment.file_type, attachment.file_name)}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0" onClick={onPreview} role="button">
        <p className="text-sm font-medium text-foreground truncate cursor-pointer hover:text-primary">
          {attachment.file_name}
        </p>
        <p className="text-xs text-muted-foreground">
          {formatFileSize(attachment.file_size)} &bull; {formatDate(attachment.created_at)}
        </p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onPreview}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          title="Preview"
        >
          <Eye className="h-4 w-4" />
        </button>
        <button
          onClick={onDownload}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          title="Download"
        >
          <Download className="h-4 w-4" />
        </button>
        {onDelete && (
          <button
            onClick={onDelete}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
            title="Delete"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Deleting indicator */}
      {isDeleting && (
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
      )}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function AttachmentList({
  entityType,
  entityId,
  viewMode: initialViewMode = 'list',
  showViewToggle = true,
  allowDelete = true,
  className,
  compact = false,
}: AttachmentListProps): JSX.Element {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>(initialViewMode)
  const [previewAttachment, setPreviewAttachment] = useState<Attachment | null>(null)
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({})
  const [deleteTarget, setDeleteTarget] = useState<Attachment | null>(null)
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)

  const {
    attachments: allAttachments,
    isLoading,
    error,
    fetchAttachments,
    deleteAttachment,
    getDownloadUrl,
    getDownloadUrls,
    handleAttachmentUploaded,
    handleAttachmentDeleted,
  } = useFilesStore()

  // Get attachments for this entity
  const key = `${entityType}:${entityId}`
  const attachments = allAttachments[key] || []

  // Fetch attachments on mount
  useEffect(() => {
    if (entityId) {
      fetchAttachments(entityType, entityId)
    }
  }, [entityType, entityId, fetchAttachments])

  // Subscribe to WebSocket room for real-time updates
  useEffect(() => {
    if (!entityId) return

    const roomId = `${entityType}:${entityId}`

    // Join the room for this entity
    wsClient.joinRoom(roomId)

    // Handle attachment uploaded event
    // Note: wsClient.on() receives only the data portion, not the full message
    const handleUploaded = (data: { attachment: Attachment; entity_type: string; entity_id: string }) => {
      const { attachment, entity_type, entity_id } = data
      handleAttachmentUploaded(entity_type, entity_id, attachment)
    }

    // Handle attachment deleted event
    const handleDeleted = (data: { attachment_id: string; entity_type: string; entity_id: string }) => {
      const { attachment_id, entity_type, entity_id } = data
      handleAttachmentDeleted(entity_type, entity_id, attachment_id)
    }

    // Subscribe to events
    wsClient.on(MessageType.ATTACHMENT_UPLOADED, handleUploaded)
    wsClient.on(MessageType.ATTACHMENT_DELETED, handleDeleted)

    // Cleanup: leave room and unsubscribe
    return () => {
      wsClient.leaveRoom(roomId)
      wsClient.off(MessageType.ATTACHMENT_UPLOADED, handleUploaded)
      wsClient.off(MessageType.ATTACHMENT_DELETED, handleDeleted)
    }
  }, [entityType, entityId, handleAttachmentUploaded, handleAttachmentDeleted])

  // Load preview URLs for images (grid view) - use batch fetching to reduce API calls
  useEffect(() => {
    if (viewMode === 'grid') {
      const imageAttachments = attachments.filter(
        (a) => isImageFile(a.file_type) && !previewUrls[a.id]
      )

      if (imageAttachments.length === 0) return

      const ids = imageAttachments.map((a) => a.id)

      // Batch fetch all URLs in one request
      getDownloadUrls(ids).then((urls) => {
        if (Object.keys(urls).length > 0) {
          setPreviewUrls((prev) => ({ ...prev, ...urls }))
        }
      })
    }
  }, [attachments, viewMode, previewUrls, getDownloadUrls])

  // Handle preview
  const handlePreview = useCallback((attachment: Attachment) => {
    setPreviewAttachment(attachment)
    setIsPreviewOpen(true)
  }, [])

  // Handle download
  const handleDownload = useCallback(
    async (attachment: Attachment) => {
      const url = await getDownloadUrl(attachment.id)
      if (url) {
        window.electronAPI.openExternal(url)
      }
    },
    [getDownloadUrl]
  )

  // Handle delete - open confirmation dialog
  const handleDelete = useCallback((attachment: Attachment) => {
    setDeleteTarget(attachment)
    setIsDeleteDialogOpen(true)
  }, [])

  // Confirm delete
  const handleConfirmDelete = useCallback(async () => {
    if (!deleteTarget) return

    setDeletingId(deleteTarget.id)
    await deleteAttachment(deleteTarget.id)
    setDeletingId(null)
    setIsDeleteDialogOpen(false)
    setDeleteTarget(null)
  }, [deleteTarget, deleteAttachment])

  // Cancel delete
  const handleCancelDelete = useCallback(() => {
    setDeleteTarget(null)
    setIsDeleteDialogOpen(false)
  }, [])

  // Handle preview navigation
  const handlePreviewNavigate = useCallback((attachment: Attachment) => {
    setPreviewAttachment(attachment)
  }, [])

  // Close preview
  const handleClosePreview = useCallback(() => {
    setIsPreviewOpen(false)
    setPreviewAttachment(null)
  }, [])

  // Loading state - show skeleton
  if (isLoading && attachments.length === 0) {
    return (
      <div className={className}>
        {!compact && showViewToggle && (
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-muted-foreground">Loading...</span>
          </div>
        )}
        <SkeletonAttachments viewMode={viewMode} count={compact ? 2 : 3} />
      </div>
    )
  }

  // Empty state
  if (attachments.length === 0) {
    if (compact) {
      return (
        <p className={cn('text-sm text-muted-foreground italic', className)}>
          No attachments
        </p>
      )
    }

    return (
      <div className={cn('flex flex-col items-center justify-center py-8 text-center', className)}>
        <Paperclip className="h-12 w-12 text-muted-foreground/50" />
        <p className="mt-4 text-sm font-medium text-foreground">No attachments</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload files to attach them to this {entityType}.
        </p>
      </div>
    )
  }

  return (
    <div className={className}>
      {/* Header with view toggle */}
      {showViewToggle && !compact && (
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-muted-foreground">
            {attachments.length} {attachments.length === 1 ? 'attachment' : 'attachments'}
          </span>
          <div className="flex items-center gap-1 rounded-md border border-border p-0.5">
            <button
              onClick={() => setViewMode('list')}
              className={cn(
                'rounded p-1.5 transition-colors',
                viewMode === 'list'
                  ? 'bg-accent text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              title="List view"
            >
              <List className="h-4 w-4" />
            </button>
            <button
              onClick={() => setViewMode('grid')}
              className={cn(
                'rounded p-1.5 transition-colors',
                viewMode === 'grid'
                  ? 'bg-accent text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              title="Grid view"
            >
              <Grid className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Attachment list/grid */}
      {viewMode === 'grid' ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {attachments.map((attachment) => (
            <AttachmentGridItem
              key={attachment.id}
              attachment={attachment}
              onPreview={() => handlePreview(attachment)}
              onDownload={() => handleDownload(attachment)}
              onDelete={allowDelete ? () => handleDelete(attachment) : undefined}
              isDeleting={deletingId === attachment.id}
              previewUrl={previewUrls[attachment.id]}
            />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {attachments.map((attachment) => (
            <AttachmentListItem
              key={attachment.id}
              attachment={attachment}
              onPreview={() => handlePreview(attachment)}
              onDownload={() => handleDownload(attachment)}
              onDelete={allowDelete ? () => handleDelete(attachment) : undefined}
              isDeleting={deletingId === attachment.id}
            />
          ))}
        </div>
      )}

      {/* File Preview Modal */}
      <FilePreview
        attachment={previewAttachment}
        isOpen={isPreviewOpen}
        attachments={attachments}
        onClose={handleClosePreview}
        onNavigate={handlePreviewNavigate}
      />

      {/* Delete Confirmation Dialog */}
      <DeleteFileDialog
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
        fileName={deleteTarget?.file_name || ''}
        fileIcon={deleteTarget ? getFileIcon(deleteTarget.file_type, deleteTarget.file_name, 'lg') : undefined}
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelDelete}
        isDeleting={deletingId === deleteTarget?.id}
      />
    </div>
  )
}

export default AttachmentList
