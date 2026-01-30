/**
 * CommentInput Component
 *
 * Input field for creating new comments with @mention and file attachment support.
 * Features:
 * - Textarea with auto-resize
 * - @mention trigger and autocomplete
 * - File attachments (images, documents)
 * - Submit on Ctrl+Enter
 * - Character count
 * - Loading state
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { Send, Loader2, AtSign, Paperclip, X, FileText, FileImage, File } from 'lucide-react'
import { useUploadFile } from '@/hooks/use-attachments'
import { formatFileSize } from '@/lib/file-utils'

// ============================================================================
// Types
// ============================================================================

export interface MentionSuggestion {
  id: string
  name: string
  email?: string
  avatar_url?: string
}

/** Pending file attachment before upload */
interface PendingAttachment {
  id: string
  file: File
  previewUrl?: string
}

/** Uploaded attachment info for optimistic updates */
export interface UploadedAttachment {
  id: string
  file_name: string
  file_type: string | null
  file_size: number | null
}

export interface CommentInputProps {
  onSubmit: (content: { body_text: string; body_json?: Record<string, unknown> }, attachments?: UploadedAttachment[]) => void | Promise<void>
  placeholder?: string
  disabled?: boolean
  isSubmitting?: boolean
  mentionSuggestions?: MentionSuggestion[]
  onMentionSearch?: (query: string) => void
  onTyping?: () => void
  className?: string
  /** Task ID for uploading attachments */
  taskId?: string
  /** Allow file attachments */
  allowAttachments?: boolean
}

// ============================================================================
// Constants
// ============================================================================

const MAX_COMMENT_LENGTH = 10000
const MENTION_TRIGGER = '@'
const TYPING_DEBOUNCE_MS = 2000
const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50MB
const ALLOWED_FILE_TYPES = [
  'image/*',
  'application/pdf',
  '.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv',
].join(',')

// ============================================================================
// Attachment Preview Component
// ============================================================================

interface AttachmentPreviewProps {
  attachment: PendingAttachment
  onRemove: () => void
  disabled?: boolean
}

function AttachmentPreview({ attachment, onRemove, disabled }: AttachmentPreviewProps): JSX.Element {
  const isImage = attachment.file.type.startsWith('image/')

  return (
    <div
      className={cn(
        'group relative flex items-center gap-2 rounded-lg border border-border/60 bg-muted/30 p-2',
        'transition-all duration-150 hover:border-border hover:bg-muted/50'
      )}
    >
      {/* Thumbnail or Icon */}
      {isImage && attachment.previewUrl ? (
        <div className="h-10 w-10 flex-shrink-0 overflow-hidden rounded-md bg-muted">
          <img
            src={attachment.previewUrl}
            alt={attachment.file.name}
            className="h-full w-full object-cover"
          />
        </div>
      ) : (
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-md bg-primary/10">
          {attachment.file.type.includes('pdf') ? (
            <FileText className="h-5 w-5 text-red-500" />
          ) : isImage ? (
            <FileImage className="h-5 w-5 text-blue-500" />
          ) : (
            <File className="h-5 w-5 text-muted-foreground" />
          )}
        </div>
      )}

      {/* File Info */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-foreground">{attachment.file.name}</p>
        <p className="text-[10px] text-muted-foreground">{formatFileSize(attachment.file.size)}</p>
      </div>

      {/* Remove Button */}
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded-full',
          'bg-muted/80 text-muted-foreground',
          'opacity-0 transition-all duration-150 group-hover:opacity-100',
          'hover:bg-destructive/10 hover:text-destructive',
          'disabled:cursor-not-allowed disabled:opacity-50'
        )}
        title="Remove attachment"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

// Track inserted mentions for building body_json
interface InsertedMention {
  id: string
  name: string
  startIndex: number
  endIndex: number
}

export function CommentInput({
  onSubmit,
  placeholder = 'Write a comment... (@ to mention)',
  disabled = false,
  isSubmitting = false,
  mentionSuggestions = [],
  onMentionSearch,
  onTyping,
  className,
  taskId,
  allowAttachments = true,
}: CommentInputProps): JSX.Element {
  const [text, setText] = useState('')
  const [showMentions, setShowMentions] = useState(false)
  const [_mentionQuery, setMentionQuery] = useState('')
  const [selectedMentionIndex, setSelectedMentionIndex] = useState(0)
  const [insertedMentions, setInsertedMentions] = useState<InsertedMention[]>([])
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const mentionStartRef = useRef<number | null>(null)
  const lastTypingRef = useRef<number>(0)
  const pendingAttachmentsRef = useRef<PendingAttachment[]>(pendingAttachments)
  const handleSubmitRef = useRef<() => Promise<void>>(() => Promise.resolve())

  const uploadMutation = useUploadFile()

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [text])

  // Keep ref in sync for cleanup access
  useEffect(() => {
    pendingAttachmentsRef.current = pendingAttachments
  }, [pendingAttachments])

  // Handle text change and mention detection
  const handleTextChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newText = e.target.value
      setText(newText)

      // Emit typing indicator (debounced)
      if (onTyping && newText.length > 0) {
        const now = Date.now()
        if (now - lastTypingRef.current > TYPING_DEBOUNCE_MS) {
          lastTypingRef.current = now
          onTyping()
        }
      }

      // Check for @ mention trigger
      const cursorPos = e.target.selectionStart || 0
      const textBeforeCursor = newText.substring(0, cursorPos)
      const lastAtIndex = textBeforeCursor.lastIndexOf(MENTION_TRIGGER)

      if (lastAtIndex !== -1) {
        const textAfterAt = textBeforeCursor.substring(lastAtIndex + 1)
        // Check if this is a valid mention context (no spaces in the query)
        if (!textAfterAt.includes(' ') && !textAfterAt.includes('\n')) {
          mentionStartRef.current = lastAtIndex
          setMentionQuery(textAfterAt)
          setShowMentions(true)
          setSelectedMentionIndex(0)
          if (onMentionSearch) {
            onMentionSearch(textAfterAt)
          }
          return
        }
      }

      setShowMentions(false)
      mentionStartRef.current = null
    },
    [onMentionSearch, onTyping]
  )

  // Insert mention
  const insertMention = useCallback(
    (suggestion: MentionSuggestion) => {
      if (mentionStartRef.current === null) return

      const beforeMention = text.substring(0, mentionStartRef.current)
      const cursorPos = textareaRef.current?.selectionStart || text.length
      const afterMention = text.substring(cursorPos)

      const mentionText = `@${suggestion.name}`
      const newText = `${beforeMention}${mentionText} ${afterMention}`

      // Track this mention
      const newMention: InsertedMention = {
        id: suggestion.id,
        name: suggestion.name,
        startIndex: mentionStartRef.current,
        endIndex: mentionStartRef.current + mentionText.length,
      }

      // Update mentions list, adjusting indices for existing mentions after this one
      setInsertedMentions((prev) => {
        const adjusted = prev.map((m) => {
          if (m.startIndex >= mentionStartRef.current!) {
            const shift = mentionText.length + 1 - (cursorPos - mentionStartRef.current!)
            return {
              ...m,
              startIndex: m.startIndex + shift,
              endIndex: m.endIndex + shift,
            }
          }
          return m
        })
        return [...adjusted, newMention]
      })

      setText(newText)
      setShowMentions(false)
      mentionStartRef.current = null

      // Focus and position cursor
      setTimeout(() => {
        if (textareaRef.current) {
          const newCursorPos = beforeMention.length + mentionText.length + 1
          textareaRef.current.focus()
          textareaRef.current.setSelectionRange(newCursorPos, newCursorPos)
        }
      }, 0)
    },
    [text]
  )

  // Handle keyboard navigation for mentions
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (showMentions && mentionSuggestions.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          setSelectedMentionIndex((i) =>
            i < mentionSuggestions.length - 1 ? i + 1 : 0
          )
          return
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault()
          setSelectedMentionIndex((i) =>
            i > 0 ? i - 1 : mentionSuggestions.length - 1
          )
          return
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault()
          insertMention(mentionSuggestions[selectedMentionIndex])
          return
        }
        if (e.key === 'Escape') {
          e.preventDefault()
          setShowMentions(false)
          return
        }
      }

      // Submit on Ctrl+Enter or Cmd+Enter
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        handleSubmitRef.current()
      }
    },
    [showMentions, mentionSuggestions, selectedMentionIndex, insertMention]
  )

  // Handle file selection
  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (!files || files.length === 0) return

      const newAttachments: PendingAttachment[] = []

      Array.from(files).forEach((file) => {
        // Validate file size
        if (file.size > MAX_FILE_SIZE) {
          console.warn(`File "${file.name}" exceeds maximum size of ${formatFileSize(MAX_FILE_SIZE)}`)
          return
        }

        const id = `pending-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
        const isImage = file.type.startsWith('image/')

        // Create preview URL for images
        const previewUrl = isImage ? URL.createObjectURL(file) : undefined

        newAttachments.push({ id, file, previewUrl })
      })

      setPendingAttachments((prev) => [...prev, ...newAttachments])

      // Reset input
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    },
    []
  )

  // Remove pending attachment
  const handleRemoveAttachment = useCallback((attachmentId: string) => {
    setPendingAttachments((prev) => {
      const attachment = prev.find((a) => a.id === attachmentId)
      // Revoke object URL to prevent memory leaks
      if (attachment?.previewUrl) {
        URL.revokeObjectURL(attachment.previewUrl)
      }
      return prev.filter((a) => a.id !== attachmentId)
    })
  }, [])

  // Cleanup preview URLs on unmount
  useEffect(() => {
    return () => {
      pendingAttachmentsRef.current.forEach((a) => {
        if (a.previewUrl) {
          URL.revokeObjectURL(a.previewUrl)
        }
      })
    }
  }, [])

  // Build TipTap JSON from text and mentions
  const buildTipTapJson = useCallback(
    (bodyText: string, mentions: InsertedMention[]): Record<string, unknown> => {
      // Sort mentions by start index
      const sortedMentions = [...mentions].sort((a, b) => a.startIndex - b.startIndex)

      // Build content array with text and mention nodes
      const content: Array<Record<string, unknown>> = []
      let lastIndex = 0

      for (const mention of sortedMentions) {
        // Add text before this mention
        if (mention.startIndex > lastIndex) {
          const textBefore = bodyText.substring(lastIndex, mention.startIndex)
          if (textBefore) {
            content.push({
              type: 'text',
              text: textBefore,
            })
          }
        }

        // Add mention node
        content.push({
          type: 'mention',
          attrs: {
            id: mention.id,
            label: mention.name,
          },
        })

        lastIndex = mention.endIndex
      }

      // Add remaining text after last mention
      if (lastIndex < bodyText.length) {
        content.push({
          type: 'text',
          text: bodyText.substring(lastIndex),
        })
      }

      // If no content nodes (no mentions), just use plain text
      if (content.length === 0) {
        content.push({
          type: 'text',
          text: bodyText,
        })
      }

      return {
        type: 'doc',
        content: [
          {
            type: 'paragraph',
            content,
          },
        ],
      }
    },
    []
  )

  // Handle submit
  const handleSubmit = useCallback(async () => {
    const trimmedText = text.trim()
    const hasContent = trimmedText.length > 0 || pendingAttachments.length > 0
    if (!hasContent || disabled || isSubmitting || isUploading) return

    // Build content object with body_json if there are mentions
    const submitData: { body_text: string; body_json?: Record<string, unknown> } = {
      body_text: trimmedText || ' ', // Ensure we have at least some text if only attachments
    }

    if (insertedMentions.length > 0 && trimmedText) {
      // Filter mentions that are still valid (exist in the text)
      const validMentions = insertedMentions.filter((m) => {
        const mentionText = `@${m.name}`
        return trimmedText.includes(mentionText)
      })

      if (validMentions.length > 0) {
        submitData.body_json = buildTipTapJson(trimmedText, validMentions)
      }
    }

    // Upload attachments first, then submit comment
    // NOTE: We pass the attachment IDs to onSubmit so the parent can link them to the comment
    // after the comment is created. Since comment_id isn't known yet, we first create
    // the comment, then the parent will update attachments with the comment_id.
    // For now, we upload files with just task_id and let the backend handle association later.
    let uploadedAttachments: UploadedAttachment[] = []

    if (pendingAttachments.length > 0) {
      setIsUploading(true)
      try {
        const uploadPromises = pendingAttachments.map(async (pa) => {
          // Upload with entity_type='comment' - the backend will create unlinked attachments
          // that will be linked when comment is created
          const result = await uploadMutation.mutateAsync({
            file: pa.file,
            entityType: 'task', // Attach to task for now, will be linked to comment
            entityId: taskId,
          })
          if (result?.id) {
            return {
              id: result.id,
              file_name: result.file_name || pa.file.name,
              file_type: result.file_type || pa.file.type || null,
              file_size: result.file_size ?? pa.file.size ?? null,
            }
          }
          return null
        })

        const results = await Promise.all(uploadPromises)
        uploadedAttachments = results.filter((a): a is UploadedAttachment => a !== null)
      } catch (error) {
        console.error('Failed to upload attachments:', error)
      } finally {
        setIsUploading(false)
      }
    }

    // Clean up preview URLs
    pendingAttachments.forEach((a) => {
      if (a.previewUrl) {
        URL.revokeObjectURL(a.previewUrl)
      }
    })

    // Submit comment and wait for it to complete before clearing state
    // This prevents the visual glitch where the input clears before the comment appears
    try {
      await onSubmit(submitData, uploadedAttachments.length > 0 ? uploadedAttachments : undefined)
    } finally {
      // Always clear state after submit completes (success or error)
      setText('')
      setShowMentions(false)
      setInsertedMentions([])
      setPendingAttachments([])
    }
  }, [text, disabled, isSubmitting, isUploading, onSubmit, insertedMentions, buildTipTapJson, pendingAttachments, uploadMutation, taskId])

  // Keep ref in sync for keyboard shortcut access
  handleSubmitRef.current = handleSubmit

  const isOverLimit = text.length > MAX_COMMENT_LENGTH
  const hasContent = text.trim().length > 0 || pendingAttachments.length > 0
  const canSubmit = hasContent && !isOverLimit && !disabled && !isSubmitting && !isUploading

  return (
    <div className={cn('relative', className)}>
      {/* Mention suggestions dropdown */}
      {showMentions && mentionSuggestions.length > 0 && (
        <div
          className={cn(
            'absolute bottom-full left-0 mb-1 w-64 max-h-48 overflow-y-auto',
            'rounded-md border border-border bg-popover shadow-lg',
            'z-50'
          )}
        >
          {mentionSuggestions.map((suggestion, index) => (
            <button
              key={suggestion.id}
              onClick={() => insertMention(suggestion)}
              className={cn(
                'flex w-full items-center gap-2 px-3 py-2 text-left',
                'text-sm transition-colors',
                index === selectedMentionIndex
                  ? 'bg-accent text-accent-foreground'
                  : 'hover:bg-muted'
              )}
            >
              {suggestion.avatar_url ? (
                <img
                  src={suggestion.avatar_url}
                  alt={suggestion.name}
                  className="h-6 w-6 rounded-full"
                />
              ) : (
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-medium">
                  {suggestion.name.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{suggestion.name}</div>
                {suggestion.email && (
                  <div className="text-xs text-muted-foreground truncate">
                    {suggestion.email}
                  </div>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Pending attachments */}
      {pendingAttachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {pendingAttachments.map((attachment) => (
            <AttachmentPreview
              key={attachment.id}
              attachment={attachment}
              onRemove={() => handleRemoveAttachment(attachment.id)}
              disabled={disabled || isSubmitting || isUploading}
            />
          ))}
        </div>
      )}

      {/* Input area */}
      <div
        className={cn(
          'flex gap-2 rounded-lg border border-border bg-background p-2',
          'focus-within:ring-1 focus-within:ring-ring',
          'transition-shadow'
        )}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isSubmitting || isUploading}
          rows={1}
          className={cn(
            'flex-1 min-h-[36px] max-h-[200px] resize-none',
            'bg-transparent text-sm text-foreground',
            'placeholder:text-muted-foreground',
            'focus:outline-none',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        />

        <div className="flex flex-col items-end justify-between gap-1">
          {/* Action buttons */}
          <div className="flex items-center gap-1">
            {/* Attachment button */}
            {allowAttachments && (
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ALLOWED_FILE_TYPES}
                  multiple
                  onChange={handleFileSelect}
                  className="hidden"
                  disabled={disabled || isSubmitting || isUploading}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={disabled || isSubmitting || isUploading}
                  className={cn(
                    'flex h-8 w-8 items-center justify-center rounded-md',
                    'text-muted-foreground',
                    'hover:bg-muted hover:text-foreground',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                    'transition-colors'
                  )}
                  title="Attach file"
                >
                  <Paperclip className="h-4 w-4" />
                </button>
              </>
            )}

            {/* Submit button */}
            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-md',
                'text-primary-foreground bg-primary',
                'hover:bg-primary/90',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors'
              )}
              title="Send (Ctrl+Enter)"
            >
              {isSubmitting || isUploading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </button>
          </div>

          {/* Character count */}
          {text.length > 0 && (
            <span
              className={cn(
                'text-[10px] tabular-nums',
                isOverLimit ? 'text-destructive' : 'text-muted-foreground'
              )}
            >
              {text.length}/{MAX_COMMENT_LENGTH}
            </span>
          )}
        </div>
      </div>

      {/* Hint */}
      <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-0.5">
          <AtSign className="h-2.5 w-2.5" />
          to mention
        </span>
        <span>|</span>
        {allowAttachments && (
          <>
            <span className="flex items-center gap-0.5">
              <Paperclip className="h-2.5 w-2.5" />
              to attach
            </span>
            <span>|</span>
          </>
        )}
        <span>Ctrl+Enter to send</span>
      </div>
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export default CommentInput
