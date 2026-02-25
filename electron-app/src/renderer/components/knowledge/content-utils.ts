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
 * Check if a parsed content object is in canvas format.
 */
export function isCanvasFormat(content: object | null): boolean {
  return content !== null && typeof content === 'object' && (content as Record<string, unknown>).format === 'canvas'
}

/**
 * Ensure TipTap content starts with an h1 heading.
 *
 * - If content is null/empty: returns a doc with h1 (= title) + empty paragraph
 * - If content already starts with h1: returns it unchanged
 * - If content has content but no leading h1: prepends one with the title
 * - If content is canvas format: returns it unchanged (canvas docs don't have heading structure)
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

  let doc: Record<string, unknown>
  try {
    const parsed: unknown = JSON.parse(contentJson)
    if (typeof parsed !== 'object' || parsed === null) {
      return { type: 'doc', content: [heading, rule, { type: 'paragraph' }] }
    }
    doc = parsed as Record<string, unknown>
  } catch {
    return {
      type: 'doc',
      content: [heading, rule, { type: 'paragraph' }],
    }
  }

  // Canvas documents don't have heading structure — return unchanged
  if (isCanvasFormat(doc)) {
    return doc as unknown as TipTapDoc
  }

  const typedDoc = doc as unknown as TipTapDoc

  if (!typedDoc.content?.length) {
    return { ...typedDoc, content: [heading, rule, { type: 'paragraph' }] }
  }

  const first = typedDoc.content[0]
  if (first.type === 'heading' && first.attrs?.level === 1) {
    return typedDoc
  }

  return { ...typedDoc, content: [heading, rule, ...typedDoc.content] }
}

