/**
 * Markdown Renderer
 *
 * Lightweight markdown-to-JSX renderer with no external dependencies.
 * Supports bold, italic, strikethrough, inline code, code blocks, headings,
 * lists (including task checkboxes), tables with column alignment,
 * blockquotes, horizontal rules, links, and paragraph breaks.
 * Escapes HTML entities for XSS prevention.
 */

import { useState, useCallback, useMemo } from 'react'
import { Copy, Check, Download, FileSpreadsheet, Square, CheckSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getAccessToken } from '@/lib/api-client'

// ============================================================================
// Types
// ============================================================================

interface MarkdownRendererProps {
  content: string
  className?: string
}

type Alignment = 'left' | 'center' | 'right'

type BlockNode =
  | { type: 'heading'; level: number; children: InlineNode[] }
  | { type: 'code_block'; language: string; code: string }
  | { type: 'paragraph'; children: InlineNode[] }
  | { type: 'unordered_list'; items: ListItem[] }
  | { type: 'ordered_list'; items: ListItem[] }
  | { type: 'table'; headers: InlineNode[][]; rows: InlineNode[][][]; alignments: Alignment[] }
  | { type: 'blockquote'; children: BlockNode[] }
  | { type: 'hr' }

interface ListItem {
  children: InlineNode[]
  subItems?: ListItem[]
  checked?: boolean | null // null = not a checkbox, true/false = checkbox state
}

type InlineNode =
  | { type: 'text'; value: string }
  | { type: 'bold'; children: InlineNode[] }
  | { type: 'italic'; children: InlineNode[] }
  | { type: 'strikethrough'; children: InlineNode[] }
  | { type: 'code'; value: string }
  | { type: 'link'; href: string; children: InlineNode[] }
  | { type: 'line_break' }

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
      const alignments = parseTableAlignments(lines[i + 1])
      i += 2 // skip header and separator
      const rows: InlineNode[][][] = []
      while (i < lines.length && lines[i].includes('|')) {
        rows.push(parseTableRow(lines[i]))
        i++
      }
      blocks.push({ type: 'table', headers, rows, alignments })
      continue
    }

    // Unordered list (including task checkboxes)
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
      !(lines[i].includes('|') && i + 1 < lines.length && /^\s*\|?\s*[-:]+/.test(lines[i + 1])) &&
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

function parseTableAlignments(separatorLine: string): Alignment[] {
  const stripped = separatorLine.replace(/^\s*\|/, '').replace(/\|\s*$/, '')
  return stripped.split('|').map((cell) => {
    const trimmed = cell.trim()
    const left = trimmed.startsWith(':')
    const right = trimmed.endsWith(':')
    if (left && right) return 'center'
    if (right) return 'right'
    return 'left'
  })
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
    let content = match[2]

    // Detect task checkbox
    let checked: boolean | null = null
    const checkboxMatch = content.match(/^\[([ xX])\]\s(.*)$/)
    if (checkboxMatch) {
      checked = checkboxMatch[1].toLowerCase() === 'x'
      content = checkboxMatch[2]
    }

    const item: ListItem = { children: parseInline(content), checked }

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
    // Line break (two trailing spaces or backslash before newline)
    const brMatch = remaining.match(/^( {2,}|\\\n)\n/) || remaining.match(/^\\\n/)
    if (brMatch) {
      nodes.push({ type: 'line_break' })
      remaining = remaining.slice(brMatch[0].length)
      continue
    }

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

    // Strikethrough ~~text~~
    const strikeMatch = remaining.match(/^~~(.+?)~~/)
    if (strikeMatch) {
      nodes.push({ type: 'strikethrough', children: parseInline(strikeMatch[1]) })
      remaining = remaining.slice(strikeMatch[0].length)
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
    const nextSpecial = remaining.slice(1).search(/[`*_~\[\n\\]/)
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
    <div className="group relative my-2.5 rounded-lg border border-border bg-muted/50 overflow-hidden shadow-sm">
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
        return <strong key={k} className="font-semibold text-foreground">{renderInline(node.children, k)}</strong>
      case 'italic':
        return <em key={k}>{renderInline(node.children, k)}</em>
      case 'strikethrough':
        return <del key={k} className="text-muted-foreground/60">{renderInline(node.children, k)}</del>
      case 'line_break':
        return <br key={k} />
      case 'code':
        return (
          <code
            key={k}
            className="rounded-md bg-muted/80 border border-border/40 px-1.5 py-0.5 text-[0.8em] font-mono text-foreground/90"
          >
            {node.value}
          </code>
        )
      case 'link': {
        // MED-1: Validate export links match strict UUID/filename pattern
        // to prevent prompt-injected path traversal hitting arbitrary endpoints.
        const EXPORT_LINK_RE = /^\/api\/ai\/export\/[a-f0-9-]{36}\/[\w.-]+$/
        const isExportLink = EXPORT_LINK_RE.test(node.href)
        if (isExportLink) {
          const apiBase = (import.meta.env.VITE_API_URL || 'http://localhost:8001') as string
          const fullUrl = `${apiBase}${node.href}`
          return (
            <ExportDownloadCard
              key={k}
              href={fullUrl}
              filename={node.href.split('/').pop() || 'export.xlsx'}
            />
          )
        }

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
            className="text-primary underline underline-offset-2 hover:text-primary/80 transition-colors"
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
    const isCheckbox = item.checked !== null && item.checked !== undefined
    return (
      <li key={k} className={cn(isCheckbox && 'list-none -ml-4 flex items-start gap-1.5')}>
        {isCheckbox && (
          item.checked ? (
            <CheckSquare className="h-4 w-4 shrink-0 mt-0.5 text-emerald-500" />
          ) : (
            <Square className="h-4 w-4 shrink-0 mt-0.5 text-muted-foreground/50" />
          )
        )}
        <span className={cn(isCheckbox && item.checked && 'line-through text-muted-foreground/60')}>
          {renderInline(item.children, k)}
        </span>
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
      if (block.level === 1) {
        return (
          <Tag key={key} className="text-base font-bold tracking-tight mt-4 first:mt-0 mb-2 pb-1.5 border-b border-border/40 text-foreground">
            {renderInline(block.children, key)}
          </Tag>
        )
      }
      if (block.level === 2) {
        return (
          <Tag key={key} className="text-[0.925rem] font-semibold mt-3.5 first:mt-0 mb-1.5 pl-2.5 border-l-2 border-primary/50 text-foreground">
            {renderInline(block.children, key)}
          </Tag>
        )
      }
      return (
        <Tag key={key} className="text-sm font-semibold mt-3 first:mt-0 mb-1 text-foreground/90">
          {renderInline(block.children, key)}
        </Tag>
      )
    }

    case 'code_block':
      return <CodeBlock key={key} language={block.language} code={block.code} />

    case 'paragraph':
      return (
        <p key={key} className="whitespace-pre-wrap break-words leading-relaxed text-foreground/85">
          {renderInline(block.children, key)}
        </p>
      )

    case 'unordered_list':
      return (
        <ul key={key} className="ml-4 list-disc space-y-1 marker:text-primary/40">
          {renderListItems(block.items, key)}
        </ul>
      )

    case 'ordered_list':
      return (
        <ol key={key} className="ml-4 list-decimal space-y-1 marker:text-primary/40 marker:font-medium">
          {renderListItems(block.items, key)}
        </ol>
      )

    case 'blockquote':
      return (
        <blockquote
          key={key}
          className="border-l-2 border-amber-400/50 bg-amber-500/5 rounded-r-lg pl-3 pr-2 py-1.5 text-muted-foreground"
        >
          {block.children.map((child, ci) => renderBlock(child, `${key}-bq-${ci}`))}
        </blockquote>
      )

    case 'hr':
      return (
        <div key={key} className="my-3 flex items-center gap-2">
          <div className="h-px flex-1 bg-border/60" />
          <div className="h-1 w-1 rounded-full bg-border" />
          <div className="h-px flex-1 bg-border/60" />
        </div>
      )

    case 'table':
      return (
        <div key={key} className="my-3 overflow-x-auto rounded-lg border border-border/60 shadow-sm">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-muted/60">
                {block.headers.map((cell, ci) => (
                  <th
                    key={`${key}-th-${ci}`}
                    className="px-3 py-2 font-semibold text-foreground/90 border-b border-border/60 whitespace-nowrap"
                    style={{ textAlign: block.alignments[ci] || 'left' }}
                  >
                    {renderInline(cell, `${key}-th-${ci}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {block.rows.map((row, ri) => (
                <tr
                  key={`${key}-tr-${ri}`}
                  className="transition-colors hover:bg-muted/25 even:bg-muted/10"
                >
                  {row.map((cell, ci) => (
                    <td
                      key={`${key}-td-${ri}-${ci}`}
                      className="px-3 py-1.5 text-foreground/80"
                      style={{ textAlign: block.alignments[ci] || 'left' }}
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
// Export Download Card
// ============================================================================

function ExportDownloadCard({ href, filename }: { href: string; filename: string }): JSX.Element {
  const handleDownload = useCallback(async () => {
    try {
      // Fetch with auth headers for the Electron app
      const token = getAccessToken()
      const res = await fetch(href, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) throw new Error(`Download failed: ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('[ExportDownloadCard] Download failed:', err)
    }
  }, [href, filename])

  return (
    <button
      type="button"
      onClick={handleDownload}
      className={cn(
        'my-2 flex w-full items-center gap-3 rounded-lg border border-border',
        'bg-muted/40 px-4 py-3 text-left transition-colors',
        'hover:bg-muted/70 hover:border-primary/40 cursor-pointer'
      )}
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10">
        <FileSpreadsheet className="h-5 w-5 text-emerald-600" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{filename}</p>
        <p className="text-xs text-muted-foreground">Click to download</p>
      </div>
      <Download className="h-4 w-4 shrink-0 text-muted-foreground" />
    </button>
  )
}

// ============================================================================
// Component
// ============================================================================

export function MarkdownRenderer({ content, className }: MarkdownRendererProps): JSX.Element {
  const blocks = useMemo(() => parseBlocks(content), [content])

  return (
    <div className={cn('space-y-2.5 text-sm leading-relaxed [overflow-wrap:anywhere]', className)}>
      {blocks.map((block, i) => renderBlock(block, `md-${i}`))}
    </div>
  )
}
