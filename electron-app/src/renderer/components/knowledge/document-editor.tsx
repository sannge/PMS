/**
 * DocumentEditor Component
 *
 * Main rich text editor for the knowledge base.
 * Composes the EditorToolbar + TipTap EditorContent + status bar placeholder.
 * Content is persisted as TipTap JSON (not HTML).
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

  // Keep onChange ref current to avoid re-creating editor on every render
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

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
  })

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
  }, [])

  // Sync editable prop
  useEffect(() => {
    if (editor) {
      editor.setEditable(editable)
    }
  }, [editor, editable])

  // Sync content prop (only when editor is not focused, to avoid overwriting user typing)
  useEffect(() => {
    if (editor && content && !editor.isFocused) {
      editor.commands.setContent(content)
    }
  }, [editor, content])

  if (!editor) {
    return null
  }

  return (
    <div className={cn('border rounded-lg overflow-hidden bg-background', className)}>
      {editable && <EditorToolbar editor={editor} />}
      <EditorContent editor={editor} className="prose prose-sm max-w-none" />
      <EditorStatusBar editor={editor} />
    </div>
  )
}
