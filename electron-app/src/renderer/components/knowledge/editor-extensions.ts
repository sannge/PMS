/**
 * Knowledge Base Editor Extensions
 *
 * Single factory function that configures ALL TipTap extensions upfront.
 * Later plans (03-02 through 03-04) only add toolbar UI sections --
 * the extensions themselves are already registered here.
 */

import { Extension, RawCommands } from '@tiptap/core'
import type { Transaction } from '@tiptap/pm/state'
import type { EditorState } from '@tiptap/pm/state'
import type { Node as ProseMirrorNode } from '@tiptap/pm/model'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import TextStyle from '@tiptap/extension-text-style'
import FontFamily from '@tiptap/extension-font-family'
import Color from '@tiptap/extension-color'
import Highlight from '@tiptap/extension-highlight'
import TextAlign from '@tiptap/extension-text-align'
import Link from '@tiptap/extension-link'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import { common, createLowlight } from 'lowlight'

// ============================================================================
// Custom Extensions (copied from RichTextEditor.tsx)
// ============================================================================

// Custom FontSize extension - extends TextStyle to support font-size
const FontSize = Extension.create({
  name: 'fontSize',

  addOptions() {
    return {
      types: ['textStyle'],
    }
  },

  addGlobalAttributes() {
    return [
      {
        types: this.options.types,
        attributes: {
          fontSize: {
            default: null,
            parseHTML: element => element.style.fontSize?.replace(/['"]+/g, '') || null,
            renderHTML: attributes => {
              if (!attributes.fontSize) {
                return {}
              }
              return {
                style: `font-size: ${attributes.fontSize}`,
              }
            },
          },
        },
      },
    ]
  },
})

// Custom Indent extension - adds margin-left based indentation for paragraph/heading nodes
const INDENT_STEP = 40
const MAX_INDENT_LEVEL = 8

const Indent = Extension.create({
  name: 'indent',

  addGlobalAttributes() {
    return [
      {
        types: ['paragraph', 'heading'],
        attributes: {
          indent: {
            default: 0,
            parseHTML: element => {
              const marginLeft = element.style.marginLeft
              if (!marginLeft) return 0
              return Math.round(parseInt(marginLeft, 10) / INDENT_STEP) || 0
            },
            renderHTML: attributes => {
              if (!attributes.indent || attributes.indent <= 0) return {}
              return {
                style: `margin-left: ${attributes.indent * INDENT_STEP}px`,
              }
            },
          },
        },
      },
    ]
  },

  addCommands() {
    return {
      indent: () => ({ tr, state, dispatch }: { tr: Transaction; state: EditorState; dispatch?: (tr: Transaction) => void }) => {
        const { selection } = state
        const { from, to } = selection
        let changed = false
        state.doc.nodesBetween(from, to, (node: ProseMirrorNode, pos: number) => {
          if (node.type.name === 'paragraph' || node.type.name === 'heading') {
            const currentIndent = node.attrs.indent || 0
            if (currentIndent < MAX_INDENT_LEVEL) {
              if (dispatch) {
                tr.setNodeMarkup(pos, undefined, {
                  ...node.attrs,
                  indent: currentIndent + 1,
                })
              }
              changed = true
            }
          }
        })
        return changed
      },
      outdent: () => ({ tr, state, dispatch }: { tr: Transaction; state: EditorState; dispatch?: (tr: Transaction) => void }) => {
        const { selection } = state
        const { from, to } = selection
        let changed = false
        state.doc.nodesBetween(from, to, (node: ProseMirrorNode, pos: number) => {
          if (node.type.name === 'paragraph' || node.type.name === 'heading') {
            const currentIndent = node.attrs.indent || 0
            if (currentIndent > 0) {
              if (dispatch) {
                tr.setNodeMarkup(pos, undefined, {
                  ...node.attrs,
                  indent: currentIndent - 1,
                })
              }
              changed = true
            }
          }
        })
        return changed
      },
    } as Partial<RawCommands>
  },
})

// ============================================================================
// Constants
// ============================================================================

export const COLORS = [
  // Grays
  '#000000', '#1f2937', '#374151', '#6b7280', '#9ca3af', '#d1d5db',
  // Reds
  '#7f1d1d', '#991b1b', '#dc2626', '#ef4444', '#f87171', '#fca5a5',
  // Oranges
  '#7c2d12', '#c2410c', '#ea580c', '#f97316', '#fb923c', '#fdba74',
  // Yellows
  '#713f12', '#a16207', '#ca8a04', '#eab308', '#facc15', '#fde047',
  // Greens
  '#14532d', '#166534', '#16a34a', '#22c55e', '#4ade80', '#86efac',
  // Teals
  '#134e4a', '#115e59', '#0d9488', '#14b8a6', '#2dd4bf', '#5eead4',
  // Blues
  '#1e3a5f', '#1e40af', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd',
  // Indigos
  '#312e81', '#3730a3', '#4f46e5', '#6366f1', '#818cf8', '#a5b4fc',
  // Purples
  '#581c87', '#7e22ce', '#9333ea', '#a855f7', '#c084fc', '#d8b4fe',
  // Pinks
  '#831843', '#be185d', '#ec4899', '#f472b6', '#f9a8d4', '#fbcfe8',
]

export const HIGHLIGHT_COLORS = [
  // Yellows
  '#fef9c3', '#fef3c7', '#fde68a', '#fcd34d',
  // Pinks
  '#fce7f3', '#fbcfe8', '#f9a8d4', '#f472b6',
  // Blues
  '#dbeafe', '#bfdbfe', '#93c5fd', '#60a5fa',
  // Greens
  '#d1fae5', '#a7f3d0', '#6ee7b7', '#34d399',
  // Purples
  '#f3e8ff', '#e9d5ff', '#d8b4fe', '#c084fc',
  // Teals
  '#ccfbf1', '#99f6e4', '#5eead4', '#2dd4bf',
  // Reds
  '#fee2e2', '#fecaca', '#fca5a5', '#f87171',
  // Indigos
  '#e0e7ff', '#c7d2fe', '#a5b4fc', '#818cf8',
  // Oranges
  '#ffedd5', '#fed7aa', '#fdba74', '#fb923c',
  // Grays
  '#f3f4f6', '#e5e7eb', '#d1d5db', '#9ca3af',
]

export const FONT_SIZES = [
  { label: 'Small', value: '0.875rem' },
  { label: 'Normal', value: '1rem' },
  { label: 'Large', value: '1.25rem' },
  { label: 'Heading', value: '1.5rem' },
]

export const FONT_FAMILIES = [
  { label: 'Arial (Default)', value: 'Arial, sans-serif' },
  { label: 'Sans Serif', value: 'ui-sans-serif, system-ui, sans-serif' },
  { label: 'Serif', value: 'ui-serif, Georgia, serif' },
  { label: 'Mono', value: 'ui-monospace, monospace' },
  { label: 'Times New Roman', value: 'Times New Roman, serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Verdana', value: 'Verdana, sans-serif' },
  { label: 'Tahoma', value: 'Tahoma, sans-serif' },
  { label: 'Trebuchet MS', value: 'Trebuchet MS, sans-serif' },
  { label: 'Courier New', value: 'Courier New, monospace' },
]

export const DEFAULT_FONT_FAMILY = 'Arial, sans-serif'

// ============================================================================
// Extension Factory
// ============================================================================

/**
 * Creates the complete set of TipTap extensions for the knowledge base editor.
 * All extensions are configured upfront; subsequent plans only add toolbar UI.
 */
export function createDocumentExtensions(options?: { placeholder?: string }) {
  const lowlight = createLowlight(common)

  return [
    StarterKit.configure({
      heading: { levels: [1, 2, 3, 4, 5, 6] },
      codeBlock: false, // Use CodeBlockLowlight instead
    }),
    Underline,
    TextStyle,
    FontFamily,
    FontSize,
    Indent,
    Color,
    Highlight.configure({
      multicolor: true,
    }),
    TextAlign.configure({
      types: ['heading', 'paragraph'],
    }),
    Link.configure({
      openOnClick: false,
      HTMLAttributes: {
        class: 'text-primary underline cursor-pointer',
      },
    }),
    Table.configure({
      resizable: true,
      HTMLAttributes: {
        class: 'border-collapse border border-border w-full',
      },
    }),
    TableRow,
    TableCell.configure({
      HTMLAttributes: {
        class: 'border border-border p-2',
      },
    }),
    TableHeader.configure({
      HTMLAttributes: {
        class: 'border border-border p-2 bg-muted font-semibold',
      },
    }),
    TaskList.configure({
      HTMLAttributes: {
        class: 'not-prose',
      },
    }),
    TaskItem.configure({
      HTMLAttributes: {
        class: 'flex items-start gap-2',
      },
      nested: true,
    }),
    CodeBlockLowlight.configure({
      lowlight,
      defaultLanguage: 'plaintext',
      HTMLAttributes: {
        class: 'rounded-md bg-muted p-4 font-mono text-sm overflow-x-auto',
      },
    }),
    CharacterCount,
    Placeholder.configure({
      placeholder: options?.placeholder || 'Start writing...',
    }),
  ]
}
