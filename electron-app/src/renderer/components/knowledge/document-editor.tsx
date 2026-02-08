/**
 * DocumentEditor Component
 *
 * Pure rich text editor for the knowledge base.
 * Composes the EditorToolbar + TipTap EditorContent + status bar.
 * Content is persisted as TipTap JSON (not HTML).
 *
 * When `editable=false`, shows read-only content without toolbar.
 * When `editable=true`, shows toolbar and allows editing.
 * Content sync: always syncs in view mode; only on initial load in edit mode.
 */

import { useEditor, EditorContent, useEditorState } from '@tiptap/react'
import type { Editor } from '@tiptap/core'
import { useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { createDocumentExtensions } from './editor-extensions'
import { EditorToolbar } from './editor-toolbar'
import type { DocumentEditorProps } from './editor-types'
import './editor-styles.css'

// ============================================================================
// EditorStatusBar -- reactive word + character count
// ============================================================================

function EditorStatusBar({ editor }: { editor: Editor }) {
  const { wordCount, charCount } = useEditorState({
    editor,
    selector: (ctx) => ({
      wordCount: ctx.editor?.storage.characterCount?.words() ?? 0,
      charCount: ctx.editor?.storage.characterCount?.characters() ?? 0,
    }),
  }) ?? { wordCount: 0, charCount: 0 }

  return (
    <div className="flex items-center justify-between px-3 py-1.5 border-t text-xs text-muted-foreground">
      <span>{wordCount} words</span>
      <span>{charCount} characters</span>
    </div>
  )
}

// ============================================================================
// DocumentEditor
// ============================================================================

export function DocumentEditor({
  content,
  onChange,
  editable = true,
  placeholder,
  className,
}: DocumentEditorProps) {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onChangeRef = useRef(onChange)
  const editableRef = useRef(editable)

  // Keep refs current
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    editableRef.current = editable
  }, [editable])

  // Stable onUpdate handler using ref-based debounce
  const handleUpdate = useCallback(({ editor: ed }: { editor: ReturnType<typeof useEditor> extends infer E ? NonNullable<E> : never }) => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
    }
    debounceRef.current = setTimeout(() => {
      onChangeRef.current?.(ed.getJSON())
    }, 300)
  }, [])

  const editor = useEditor({
    extensions: createDocumentExtensions({ placeholder }),
    content: content || undefined,
    editable,
    onUpdate: handleUpdate,
    editorProps: {
      handleClick: (view, pos, event) => {
        // In view mode, allow link clicks to open in new tab
        if (!editable) {
          // Find closest anchor tag (handles nested elements like <a><strong>text</strong></a>)
          const anchor = (event.target as HTMLElement).closest('a')
          if (anchor && anchor.hasAttribute('href')) {
            const href = anchor.getAttribute('href')
            // Security: Only allow safe URL schemes
            if (href && /^(https?:\/\/|mailto:|tel:)/.test(href)) {
              window.open(href, '_blank', 'noopener,noreferrer')
              event.preventDefault()
              return true
            }
          }
        }
        return false
      },
      // No context menu handler - let browser/Electron handle it natively
    },
  })

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
  }, [])

  // Sync editable state
  useEffect(() => {
    if (editor) {
      editor.setEditable(editable)
    }
  }, [editor, editable])

  // Sync content prop:
  // - In view mode (not editable): always sync to reflect latest server data
  // - In edit mode (editable): only sync if editor is not focused (initial load)
  // - When switching from edit to view: always sync to discard unsaved changes
  useEffect(() => {
    if (!editor || !content) return
    if (!editableRef.current || !editor.isFocused) {
      editor.commands.setContent(content)
    }
  }, [editor, content, editable])

  if (!editor) {
    return null
  }

  return (
    <div className={cn('overflow-hidden bg-background flex flex-col min-h-0', className)}>
      {editable && <EditorToolbar editor={editor} />}
      <div className="flex-1 overflow-y-auto min-h-0">
        <EditorContent editor={editor} className="prose prose-sm max-w-none" />
      </div>
      <EditorStatusBar editor={editor} />
    </div>
  )
}
