/**
 * Chat Input Component
 *
 * Modern chat input with glassmorphism container, auto-resizing textarea,
 * gradient send button, image paste (Ctrl+V), image upload via paperclip,
 * and thumbnail preview strip. Supports up to 5 images per message, max 10MB each.
 */

import { useState, useRef, useCallback, useEffect, useImperativeHandle, forwardRef } from 'react'
import { ArrowUp, X, ImagePlus, Square } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useAiSidebar } from './use-ai-sidebar'
import { useAiChat } from './use-ai-chat'
import { useAiContext } from './ai-context'
import type { PendingImage } from './types'

const MAX_IMAGES = 5
const MAX_IMAGE_BYTES = 10 * 1024 * 1024 // 10 MB

// ============================================================================
// Helpers
// ============================================================================

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      const base64 = result.split(',')[1]
      resolve(base64)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

async function processImageFile(
  file: File,
  currentCount: number
): Promise<PendingImage | null> {
  if (currentCount >= MAX_IMAGES) {
    toast('Image limit reached', {
      description: `Maximum ${MAX_IMAGES} images per message.`,
    })
    return null
  }

  if (file.size > MAX_IMAGE_BYTES) {
    toast('Image too large', {
      description: `${file.name || 'Image'} exceeds the 10 MB limit.`,
    })
    return null
  }

  const data = await fileToBase64(file)
  const previewUrl = URL.createObjectURL(file)

  return {
    id: crypto.randomUUID(),
    data,
    mediaType: file.type || 'image/png',
    filename: file.name || undefined,
    previewUrl,
  }
}

// ============================================================================
// Component
// ============================================================================

export interface ChatInputHandle {
  focus: () => void
}

interface ChatInputProps {
  onReplaySend?: (text: string) => void
  onCancelStream?: () => void
}

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(function ChatInput({ onReplaySend, onCancelStream }, ref) {
  const [input, setInput] = useState('')
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([])
  const { sendMessage } = useAiChat()
  const { context: aiContext } = useAiContext()
  const isStreaming = useAiSidebar((s) => s.isStreaming)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pendingImagesRef = useRef<PendingImage[]>([])
  pendingImagesRef.current = pendingImages
  const lastSendTimeRef = useRef(0)

  useImperativeHandle(ref, () => ({
    focus: () => textareaRef.current?.focus(),
  }), [])

  // Revoke all preview object URLs on unmount
  useEffect(() => {
    return () => {
      pendingImagesRef.current.forEach((img) => URL.revokeObjectURL(img.previewUrl))
    }
  }, [])

  const handleSend = useCallback(() => {
    const trimmed = input.trim()
    if ((!trimmed && pendingImages.length === 0) || isStreaming) return

    const now = Date.now()
    if (now - lastSendTimeRef.current < 1000) return
    lastSendTimeRef.current = now

    const images =
      pendingImages.length > 0
        ? pendingImages.map((img) => ({
            data: img.data,
            mediaType: img.mediaType,
            filename: img.filename,
          }))
        : undefined

    const messageText = aiContext ? `[Context: ${aiContext}]\n${trimmed}` : trimmed

    if (onReplaySend) {
      onReplaySend(messageText)
    } else {
      sendMessage(messageText, images)
    }
    setInput('')

    pendingImages.forEach((img) => URL.revokeObjectURL(img.previewUrl))
    setPendingImages([])

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [input, pendingImages, isStreaming, sendMessage, onReplaySend, aiContext])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend]
  )

  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInput(e.target.value)
      const el = e.target
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 120)}px`
    },
    []
  )

  const handlePaste = useCallback(
    async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const items = e.clipboardData?.items
      if (!items) return

      const imageFiles: File[] = []
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile()
          if (file) imageFiles.push(file)
        }
      }

      if (imageFiles.length === 0) return
      e.preventDefault()

      let count = pendingImages.length
      const newImages: PendingImage[] = []

      for (const file of imageFiles) {
        const img = await processImageFile(file, count)
        if (img) {
          newImages.push(img)
          count++
        }
      }

      if (newImages.length > 0) {
        setPendingImages((prev) => [...prev, ...newImages])
      }
    },
    [pendingImages.length]
  )

  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (!files || files.length === 0) return

      let count = pendingImages.length
      const newImages: PendingImage[] = []

      for (const file of Array.from(files)) {
        const img = await processImageFile(file, count)
        if (img) {
          newImages.push(img)
          count++
        }
      }

      if (newImages.length > 0) {
        setPendingImages((prev) => [...prev, ...newImages])
      }

      e.target.value = ''
    },
    [pendingImages.length]
  )

  const removeImage = useCallback((id: string) => {
    setPendingImages((prev) => {
      const img = prev.find((i) => i.id === id)
      if (img) URL.revokeObjectURL(img.previewUrl)
      return prev.filter((i) => i.id !== id)
    })
  }, [])

  const canSend = (input.trim() || pendingImages.length > 0) && !isStreaming

  return (
    <div className="px-3 pb-3 pt-2">
      {/* Glassmorphism input container */}
      <div
        className={cn(
          'rounded-2xl border border-border/50 bg-muted/30 backdrop-blur-sm',
          'transition-all duration-200',
          'focus-within:border-amber-400/40 focus-within:shadow-[0_0_0_1px_rgba(245,158,11,0.1)]'
        )}
      >
        {/* Image preview thumbnails */}
        {pendingImages.length > 0 && (
          <div className="flex flex-wrap gap-2 px-3 pt-3">
            {pendingImages.map((img) => (
              <div key={img.id} className="group relative">
                <img
                  src={img.previewUrl}
                  alt={img.filename || 'Pending image'}
                  className="h-14 w-14 rounded-lg object-cover ring-1 ring-border/50"
                />
                <button
                  type="button"
                  onClick={() => removeImage(img.id)}
                  className={cn(
                    'absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center',
                    'rounded-full bg-foreground/80 text-background',
                    'opacity-0 group-hover:opacity-100 transition-opacity',
                    'hover:bg-foreground'
                  )}
                  aria-label={`Remove ${img.filename || 'image'}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input row */}
        <div className="flex items-end gap-1.5 p-2">
          {/* Attachment button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isStreaming || pendingImages.length >= MAX_IMAGES}
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl',
              'text-muted-foreground/60 transition-colors',
              'hover:bg-muted/60 hover:text-muted-foreground',
              'disabled:opacity-40 disabled:pointer-events-none'
            )}
            aria-label="Attach image"
          >
            <ImagePlus className="h-4 w-4" />
          </button>

          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={handleFileChange}
          />

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder="Ask Blair anything..."
            disabled={isStreaming}
            rows={1}
            className={cn(
              'flex-1 resize-none bg-transparent px-2 py-1.5',
              'text-sm placeholder:text-muted-foreground/50',
              'focus:outline-none',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'max-h-[120px]'
            )}
          />

          {/* Send / Stop button */}
          {isStreaming && onCancelStream ? (
            <button
              type="button"
              onClick={onCancelStream}
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-all duration-200',
                'bg-red-500/80 text-white shadow-lg shadow-red-500/25 hover:bg-red-600 hover:shadow-red-500/40 hover:scale-105 active:scale-95'
              )}
              aria-label="Stop generating"
              title="Stop generating"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSend}
              disabled={!canSend}
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-all duration-200',
                canSend
                  ? 'bg-gradient-to-br from-amber-400 to-orange-500 text-white shadow-lg shadow-amber-500/25 hover:shadow-amber-500/40 hover:scale-105 active:scale-95'
                  : 'bg-muted/60 text-muted-foreground/40'
              )}
              aria-label="Send message"
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Hint text */}
      <p className="text-center text-[10px] text-muted-foreground/30 mt-1.5 select-none">
        Enter to send · Shift+Enter for new line
      </p>
    </div>
  )
})
