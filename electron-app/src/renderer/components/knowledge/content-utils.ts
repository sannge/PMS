/**
 * Content Utilities for Knowledge Base Editor
 *
 * Helpers for transforming TipTap JSON content.
 */

interface TipTapNode {
  type: string
  attrs?: Record<string, unknown>
  content?: TipTapNode[]
  text?: string
}

interface TipTapDoc {
  type: string
  content?: TipTapNode[]
}

/**
 * Ensure TipTap content starts with an h1 heading.
 *
 * - If content is null/empty: returns a doc with h1 (= title) + empty paragraph
 * - If content already starts with h1: returns it unchanged
 * - If content has content but no leading h1: prepends one with the title
 *
 * The heading becomes part of the editor content — editable in edit mode,
 * read-only in view mode, saved/cancelled with the rest of the content.
 * Editing the heading does NOT rename the document in the sidebar.
 */
export function ensureContentHeading(
  contentJson: string | null,
  title: string,
): TipTapDoc {
  const heading: TipTapNode = {
    type: 'heading',
    attrs: { level: 1 },
    content: [{ type: 'text', text: title }],
  }
  const rule: TipTapNode = { type: 'horizontalRule' }

  if (!contentJson) {
    return {
      type: 'doc',
      content: [heading, rule, { type: 'paragraph' }],
    }
  }

  const doc = JSON.parse(contentJson) as TipTapDoc

  if (!doc.content?.length) {
    return { ...doc, content: [heading, rule, { type: 'paragraph' }] }
  }

  const first = doc.content[0]
  if (first.type === 'heading' && first.attrs?.level === 1) {
    return doc
  }

  return { ...doc, content: [heading, rule, ...doc.content] }
}

