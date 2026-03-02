/**
 * Markdown Renderer
 *
 * Lightweight markdown-to-JSX renderer with no external dependencies.
 * Supports bold, italic, inline code, code blocks, headings, lists, tables,
 * blockquotes, horizontal rules, and paragraph breaks.
 * Escapes HTML entities for XSS prevention.
 */

import { useState, useCallback, useMemo } from 'react'
import { Copy, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

interface MarkdownRendererProps {
  content: string
  className?: string
}

type BlockNode =
  | { type: 'heading'; level: number; children: InlineNode[] }
  | { type: 'code_block'; language: string; code: string }
  | { type: 'paragraph'; children: InlineNode[] }
  | { type: 'unordered_list'; items: ListItem[] }
  | { type: 'ordered_list'; items: ListItem[] }
  | { type: 'table'; headers: InlineNode[][]; rows: InlineNode[][][] }
  | { type: 'blockquote'; children: BlockNode[] }
  | { type: 'hr' }

interface ListItem {
  children: InlineNode[]
  subItems?: ListItem[]
}

type InlineNode =
  | { type: 'text'; value: string }
  | { type: 'bold'; children: InlineNode[] }
  | { type: 'italic'; children: InlineNode[] }
  | { type: 'code'; value: string }
  | { type: 'link'; href: string; children: InlineNode[] }

// ============================================================================
// Block Parser
// ============================================================================

function parseBlocks(input: string): BlockNode[] {
  const lines = input.split('\n')
  const blocks: BlockNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Fenced code block
    const codeMatch = line.match(/^```([\w+#.-]*)/)
    if (codeMatch) {
      const language = codeMatch[1] || ''
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      blocks.push({ type: 'code_block', language, code: codeLines.join('\n') })
      i++ // skip closing ```
      continue
    }

    // Horizontal rule (--- or *** or ___)
    if (/^\s*[-]{3,}\s*$/.test(line) || /^\s*[*]{3,}\s*$/.test(line) || /^\s*[_]{3,}\s*$/.test(line)) {
      blocks.push({ type: 'hr' })
      i++
      continue
    }

    // Heading
    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/)
    if (headingMatch) {
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length,
        children: parseInline(headingMatch[2]),
      })
      i++
      continue
    }

    // Blockquote: collect contiguous > lines
    if (/^\s*>\s?/.test(line)) {
      const quoteLines: string[] = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^\s*>\s?/, ''))
        i++
      }
      blocks.push({
        type: 'blockquote',
        children: parseBlocks(quoteLines.join('\n')),
      })
      continue
    }

    // Table: detect header row with pipes
    if (line.includes('|') && i + 1 < lines.length && /^\s*\|?\s*[-:]+/.test(lines[i + 1])) {
      const headers = parseTableRow(line)
      i += 2 // skip header and separator
      const rows: InlineNode[][][] = []
      while (i < lines.length && lines[i].includes('|')) {
        rows.push(parseTableRow(lines[i]))
        i++
      }
      blocks.push({ type: 'table', headers, rows })
      continue
    }

    // Unordered list
    if (/^\s*[-*+]\s/.test(line)) {
      const items = parseListItems(lines, i, 'unordered')
      blocks.push({ type: 'unordered_list', items: items.items })
      i = items.nextIndex
      continue
    }

    // Ordered list
    if (/^\s*\d+\.\s/.test(line)) {
      const items = parseListItems(lines, i, 'ordered')
      blocks.push({ type: 'ordered_list', items: items.items })
      i = items.nextIndex
      continue
    }

    // Empty line
    if (line.trim() === '') {
      i++
      continue
    }

    // Paragraph: collect contiguous non-blank, non-special lines
    const paraLines: string[] = [line]
    i++
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].match(/^#{1,3}\s/) &&
      !lines[i].match(/^```/) &&
      !lines[i].match(/^\s*[-*+]\s/) &&
      !lines[i].match(/^\s*\d+\.\s/) &&
      !lines[i].match(/^\s*>\s?/) &&
      !/^\s*[-]{3,}\s*$/.test(lines[i]) && !/^\s*[*]{3,}\s*$/.test(lines[i]) && !/^\s*[_]{3,}\s*$/.test(lines[i])
    ) {
      paraLines.push(lines[i])
      i++
    }
    blocks.push({
      type: 'paragraph',
      children: parseInline(paraLines.join('\n')),
    })
  }

  return blocks
}

function parseTableRow(line: string): InlineNode[][] {
  // Strip leading/trailing pipes and split
  const stripped = line.replace(/^\s*\|/, '').replace(/\|\s*$/, '')
  return stripped.split('|').map((cell) => parseInline(cell.trim()))
}

function parseListItems(
  lines: string[],
  startIndex: number,
  listType: 'unordered' | 'ordered'
): { items: ListItem[]; nextIndex: number } {
  const items: ListItem[] = []
  let i = startIndex
  const pattern = listType === 'unordered' ? /^(\s*)[-*+]\s(.*)$/ : /^(\s*)\d+\.\s(.*)$/

  while (i < lines.length) {
    const match = lines[i].match(pattern)
    if (!match) break

    const indent = match[1].length
    const content = match[2]
    const item: ListItem = { children: parseInline(content) }

    i++
    // Check for nested items (indented further)
    if (i < lines.length) {
      const nestedPattern =
        listType === 'unordered' ? /^(\s+)[-*+]\s/ : /^(\s+)\d+\.\s/
      const nextMatch = lines[i].match(nestedPattern)
      if (nextMatch && nextMatch[1].length > indent) {
        const nested = parseListItems(lines, i, listType)
        item.subItems = nested.items
        i = nested.nextIndex
      }
    }

    items.push(item)
  }

  return { items, nextIndex: i }
}

// ============================================================================
// Inline Parser
// ============================================================================

function parseInline(text: string): InlineNode[] {
  const nodes: InlineNode[] = []
  let remaining = text

  while (remaining.length > 0) {
    // Inline code (backtick)
    const codeMatch = remaining.match(/^`([^`]+)`/)
    if (codeMatch) {
      nodes.push({ type: 'code', value: codeMatch[1] })
      remaining = remaining.slice(codeMatch[0].length)
      continue
    }

    // Link [text](url)
    const linkMatch = remaining.match(/^\[([^\]]+)\]\(([^)]+)\)/)
    if (linkMatch) {
      nodes.push({ type: 'link', href: linkMatch[2], children: parseInline(linkMatch[1]) })
      remaining = remaining.slice(linkMatch[0].length)
      continue
    }

    // Bold (**text** or __text__)
    const boldMatch = remaining.match(/^\*\*(.+?)\*\*/) || remaining.match(/^__(.+?)__/)
    if (boldMatch) {
      nodes.push({ type: 'bold', children: parseInline(boldMatch[1]) })
      remaining = remaining.slice(boldMatch[0].length)
      continue
    }

    // Italic (*text* or _text_)
    const italicMatch = remaining.match(/^\*(.+?)\*/) || remaining.match(/^_(.+?)_/)
    if (italicMatch) {
      nodes.push({ type: 'italic', children: parseInline(italicMatch[1]) })
      remaining = remaining.slice(italicMatch[0].length)
      continue
    }

    // Plain text: consume until next special character or end
    const nextSpecial = remaining.slice(1).search(/[`*_\[]/)
    if (nextSpecial === -1) {
      nodes.push({ type: 'text', value: remaining })
      break
    } else {
      nodes.push({ type: 'text', value: remaining.slice(0, nextSpecial + 1) })
      remaining = remaining.slice(nextSpecial + 1)
    }
  }

  return nodes
}

// ============================================================================
// Code Block with Copy Button
// ============================================================================

function CodeBlock({ language, code }: { language: string; code: string }): JSX.Element {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [code])

  return (
    <div className="group relative my-2 rounded-lg border border-border bg-muted/60 overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-muted/80 border-b border-border/50 text-xs text-muted-foreground">
        <span className="font-medium">{language || 'code'}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-background/60 transition-colors"
          aria-label="Copy code"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-500" />
              <span className="text-emerald-500">Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  )
}

// ============================================================================
// Renderers
// ============================================================================

function renderInline(nodes: InlineNode[], key = ''): JSX.Element[] {
  return nodes.map((node, i) => {
    const k = `${key}-${i}`
    switch (node.type) {
      case 'text':
        return <span key={k}>{node.value}</span>
      case 'bold':
        return <strong key={k} className="font-semibold">{renderInline(node.children, k)}</strong>
      case 'italic':
        return <em key={k}>{renderInline(node.children, k)}</em>
      case 'code':
        return (
          <code
            key={k}
            className="rounded-md bg-muted px-1.5 py-0.5 text-[0.8em] font-mono text-foreground/90"
          >
            {node.value}
          </code>
        )
      case 'link': {
        // Validate URL scheme for safety
        let isSafe = false
        try {
          const parsed = new URL(node.href)
          isSafe = ['http:', 'https:'].includes(parsed.protocol)
        } catch {
          isSafe = false
        }
        return isSafe ? (
          <a
            key={k}
            href={node.href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2 hover:text-primary/80"
          >
            {renderInline(node.children, k)}
          </a>
        ) : (
          <span key={k}>{renderInline(node.children, k)}</span>
        )
      }
      default:
        return <span key={k} />
    }
  })
}

function renderListItems(items: ListItem[], keyPrefix: string): JSX.Element[] {
  return items.map((item, i) => {
    const k = `${keyPrefix}-${i}`
    return (
      <li key={k}>
        {renderInline(item.children, k)}
        {item.subItems && item.subItems.length > 0 && (
          <ul className="ml-4 mt-1 list-disc space-y-1">
            {renderListItems(item.subItems, `${k}-sub`)}
          </ul>
        )}
      </li>
    )
  })
}

function renderBlock(block: BlockNode, key: string): JSX.Element {
  switch (block.type) {
    case 'heading': {
      const Tag = (`h${block.level}` as 'h1' | 'h2' | 'h3')
      const sizes = {
        1: 'text-base font-bold tracking-tight',
        2: 'text-[0.9rem] font-semibold',
        3: 'text-sm font-semibold',
      }
      return (
        <Tag key={key} className={cn(sizes[block.level as 1 | 2 | 3] || 'text-sm font-semibold', 'mt-3 first:mt-0 mb-1')}>
          {renderInline(block.children, key)}
        </Tag>
      )
    }

    case 'code_block':
      return <CodeBlock key={key} language={block.language} code={block.code} />

    case 'paragraph':
      return (
        <p key={key} className="whitespace-pre-wrap break-words leading-relaxed">
          {renderInline(block.children, key)}
        </p>
      )

    case 'unordered_list':
      return (
        <ul key={key} className="ml-4 list-disc space-y-1 marker:text-muted-foreground/60">
          {renderListItems(block.items, key)}
        </ul>
      )

    case 'ordered_list':
      return (
        <ol key={key} className="ml-4 list-decimal space-y-1 marker:text-muted-foreground/60">
          {renderListItems(block.items, key)}
        </ol>
      )

    case 'blockquote':
      return (
        <blockquote
          key={key}
          className="border-l-2 border-primary/40 pl-3 text-muted-foreground italic"
        >
          {block.children.map((child, ci) => renderBlock(child, `${key}-bq-${ci}`))}
        </blockquote>
      )

    case 'hr':
      return <hr key={key} className="my-3 border-border/60" />

    case 'table':
      return (
        <div key={key} className="my-2.5 overflow-x-auto rounded-lg border border-border/70">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-muted/70">
                {block.headers.map((cell, ci) => (
                  <th
                    key={`${key}-th-${ci}`}
                    className="px-3 py-2 text-left font-semibold text-foreground/90 border-b border-border/70 whitespace-nowrap"
                  >
                    {renderInline(cell, `${key}-th-${ci}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {block.rows.map((row, ri) => (
                <tr
                  key={`${key}-tr-${ri}`}
                  className="transition-colors hover:bg-muted/30 even:bg-muted/20"
                >
                  {row.map((cell, ci) => (
                    <td
                      key={`${key}-td-${ri}-${ci}`}
                      className="px-3 py-1.5 text-foreground/80"
                    >
                      {renderInline(cell, `${key}-td-${ri}-${ci}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
  }
}

// ============================================================================
// Component
// ============================================================================

export function MarkdownRenderer({ content, className }: MarkdownRendererProps): JSX.Element {
  const blocks = useMemo(() => parseBlocks(content), [content])

  return (
    <div className={cn('space-y-2 text-sm leading-relaxed [overflow-wrap:anywhere]', className)}>
      {blocks.map((block, i) => renderBlock(block, `md-${i}`))}
    </div>
  )
}
