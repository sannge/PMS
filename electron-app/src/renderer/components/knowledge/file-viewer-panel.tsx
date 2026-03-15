/**
 * FileViewerPanel
 *
 * Renders file content in the main content area when a file is selected
 * in the knowledge tree. Supports inline preview for images, PDF, video,
 * audio, CSV, Excel (.xlsx), and DOCX. Non-previewable files show a
 * metadata panel with "Open in App" button.
 *
 * Includes embedding sync badge (same as documents) and extraction status.
 */

import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import {
  Download,
  ExternalLink,
  Loader2,
  FileAudio,
  AlertCircle,
  Clock,
} from 'lucide-react'
import { Document, Page, pdfjs } from 'react-pdf'
import pdfjsWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjs.GlobalWorkerOptions.workerSrc = pdfjsWorkerUrl
import { cn } from '@/lib/utils'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useFileSearchHighlight } from '@/hooks/use-file-search-highlight'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import {
  useFileDownloadUrl,
  type FolderFileListItem,
} from '@/hooks/use-folder-files'
import { formatFileSize } from '@/lib/file-utils'
import { getFileIcon } from '@/lib/file-icon'
import { DocumentStatusBadge } from './document-status-badge'

// ============================================================================
// Types
// ============================================================================

interface FileViewerPanelProps {
  file: FolderFileListItem
  className?: string
}

// ============================================================================
// File Type Detection
// ============================================================================

function isImage(mime: string): boolean {
  return mime.startsWith('image/')
}

function isPdf(mime: string): boolean {
  return mime === 'application/pdf'
}

function isVideo(mime: string): boolean {
  return mime.startsWith('video/')
}

function isAudio(mime: string): boolean {
  return mime.startsWith('audio/')
}

function isCsv(ext: string): boolean {
  return ext === 'csv' || ext === 'tsv'
}

function isExcel(ext: string): boolean {
  return ['xlsx', 'xls', 'xlsm', 'xlsb'].includes(ext)
}

function isDocx(ext: string): boolean {
  return ext === 'docx'
}

// ============================================================================
// Extraction Status Display
// ============================================================================

function ExtractionBadge({ status }: { status: string }): JSX.Element | null {
  switch (status) {
    case 'pending':
      return (
        <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium border border-blue-300/50 bg-blue-50/80 text-blue-700 dark:border-blue-700/50 dark:bg-blue-950/30 dark:text-blue-400">
          <Clock className="h-2.5 w-2.5" />
          Pending
        </span>
      )
    case 'processing':
      return (
        <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium border border-yellow-300/50 bg-yellow-50/80 text-yellow-700 dark:border-yellow-700/50 dark:bg-yellow-950/30 dark:text-yellow-400">
          <Loader2 className="h-2.5 w-2.5 animate-spin" />
          Extracting...
        </span>
      )
    case 'completed':
      return null // No need to show — it's the normal state
    case 'failed':
      return (
        <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium border border-red-300/50 bg-red-50/80 text-red-700 dark:border-red-700/50 dark:bg-red-950/30 dark:text-red-400">
          <AlertCircle className="h-2.5 w-2.5" />
          Extraction failed
        </span>
      )
    case 'unsupported':
      return null // Don't clutter UI for non-extractable files
    default:
      return null
  }
}

// ============================================================================
// CSV Preview
// ============================================================================

/** Max file size for CSV preview (5 MB) */
const CSV_PREVIEW_MAX_BYTES = 5 * 1024 * 1024
/** Max file size for Excel/DOCX preview (10 MB) */
const OFFICE_PREVIEW_MAX_BYTES = 10 * 1024 * 1024

function FileTooLargeMessage({ fileSize, limit }: { fileSize: number; limit: number }): JSX.Element {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-2 text-muted-foreground">
      <AlertCircle className="h-8 w-8" />
      <p className="text-sm font-medium">File too large for preview</p>
      <p className="text-xs">
        {formatFileSize(fileSize)} exceeds the {formatFileSize(limit)} preview limit.
        Download the file to view it.
      </p>
    </div>
  )
}

function CsvPreview({ url, fileSize }: { url: string; fileSize: number }): JSX.Element {
  const tooLarge = fileSize > CSV_PREVIEW_MAX_BYTES
  const [rows, setRows] = useState<string[][]>([])
  const [isLoading, setIsLoading] = useState(!tooLarge)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (tooLarge) return
    let cancelled = false
    setIsLoading(true)
    setError(null)

    fetch(url)
      .then((res) => res.text())
      .then((text) => {
        if (cancelled) return
        const lines = text.split('\n').filter((l) => l.trim())
        const parsed = lines.map((line) => {
          // Simple CSV parse — handles quoted fields
          const result: string[] = []
          let current = ''
          let inQuotes = false
          for (let i = 0; i < line.length; i++) {
            const ch = line[i]
            if (ch === '"') {
              if (inQuotes && i + 1 < line.length && line[i + 1] === '"') {
                current += '"'
                i++ // skip the second quote
              } else {
                inQuotes = !inQuotes
              }
            } else if ((ch === ',' || ch === '\t') && !inQuotes) {
              result.push(current.trim())
              current = ''
            } else {
              current += ch
            }
          }
          result.push(current.trim())
          return result
        })
        // Limit to first 500 rows for performance
        setRows(parsed.slice(0, 500))
        setIsLoading(false)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message)
          setIsLoading(false)
        }
      })

    return () => { cancelled = true }
  }, [url, tooLarge])

  if (tooLarge) {
    return <FileTooLargeMessage fileSize={fileSize} limit={CSV_PREVIEW_MAX_BYTES} />
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    )
  }

  if (error) {
    return <div className="p-4 text-sm text-destructive">Failed to load CSV: {error}</div>
  }

  if (rows.length === 0) {
    return <div className="p-4 text-sm text-muted-foreground">Empty file</div>
  }

  const headerRow = rows[0]
  const dataRows = rows.slice(1)

  return (
    <div className="overflow-auto flex-1">
      <table className="w-full text-sm border-collapse">
        <thead className="sticky top-0 bg-muted/90 backdrop-blur-sm">
          <tr>
            {headerRow.map((cell, i) => (
              <th
                key={i}
                className="px-3 py-2 text-left font-medium text-foreground border-b border-border whitespace-nowrap"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dataRows.map((row, ri) => (
            <tr key={ri} className="hover:bg-accent/30">
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  className="px-3 py-1.5 text-foreground border-b border-border/50 whitespace-nowrap max-w-[300px] truncate"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length >= 500 && (
        <div className="p-2 text-xs text-muted-foreground text-center border-t border-border">
          Showing first 500 rows. Download for full data.
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Excel Preview
// ============================================================================

function ExcelPreview({ url, fileSize }: { url: string; fileSize: number }): JSX.Element {
  const tooLarge = fileSize > OFFICE_PREVIEW_MAX_BYTES
  const [sheets, setSheets] = useState<{ name: string; rows: unknown[][] }[]>([])
  const [activeSheet, setActiveSheet] = useState(0)
  const [isLoading, setIsLoading] = useState(!tooLarge)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (tooLarge) return
    let cancelled = false
    setIsLoading(true)
    setError(null)
    setActiveSheet(0)

    fetch(url)
      .then((res) => res.arrayBuffer())
      .then(async (buffer) => {
        if (cancelled) return
        const XLSX = await import('xlsx')
        const workbook = XLSX.read(buffer, { type: 'array' })
        const parsed = workbook.SheetNames.map((name) => {
          const sheet = workbook.Sheets[name]
          const json = XLSX.utils.sheet_to_json(sheet, { header: 1 }) as unknown[][]
          // Limit rows for performance
          return { name, rows: json.slice(0, 500) }
        })
        setSheets(parsed)
        setIsLoading(false)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message)
          setIsLoading(false)
        }
      })

    return () => { cancelled = true }
  }, [url, tooLarge])

  if (tooLarge) {
    return <FileTooLargeMessage fileSize={fileSize} limit={OFFICE_PREVIEW_MAX_BYTES} />
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    )
  }

  if (error) {
    return <div className="p-4 text-sm text-destructive">Failed to load spreadsheet: {error}</div>
  }

  if (sheets.length === 0) {
    return <div className="p-4 text-sm text-muted-foreground">Empty workbook</div>
  }

  const currentSheet = sheets[activeSheet]
  const headerRow = currentSheet.rows[0] as unknown[] ?? []
  const dataRows = currentSheet.rows.slice(1)

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Sheet tabs */}
      {sheets.length > 1 && (
        <div className="flex gap-0.5 px-2 py-1 border-b border-border bg-muted/30 overflow-x-auto">
          {sheets.map((s, i) => (
            <button
              key={s.name}
              onClick={() => setActiveSheet(i)}
              className={cn(
                'px-3 py-1 text-xs rounded-t font-medium transition-colors',
                i === activeSheet
                  ? 'bg-background text-foreground border border-b-0 border-border'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
              )}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="overflow-auto flex-1">
        <table className="w-full text-sm border-collapse">
          <thead className="sticky top-0 bg-muted/90 backdrop-blur-sm">
            <tr>
              {headerRow.map((cell, i) => (
                <th
                  key={i}
                  className="px-3 py-2 text-left font-medium text-foreground border-b border-border whitespace-nowrap"
                >
                  {String(cell ?? '')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dataRows.map((row, ri) => (
              <tr key={ri} className="hover:bg-accent/30">
                {(row as unknown[]).map((cell, ci) => (
                  <td
                    key={ci}
                    className="px-3 py-1.5 text-foreground border-b border-border/50 whitespace-nowrap max-w-[300px] truncate"
                  >
                    {String(cell ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {currentSheet.rows.length >= 500 && (
          <div className="p-2 text-xs text-muted-foreground text-center border-t border-border">
            Showing first 500 rows. Download for full data.
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// DOCX Preview
// ============================================================================

function DocxPreview({ url, fileSize }: { url: string; fileSize: number }): JSX.Element {
  const tooLarge = fileSize > OFFICE_PREVIEW_MAX_BYTES
  const containerRef = useRef<HTMLDivElement>(null)
  const [isLoading, setIsLoading] = useState(!tooLarge)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (tooLarge || !containerRef.current) return
    let cancelled = false
    setIsLoading(true)
    setError(null)

    // Clear previous render
    const container = containerRef.current
    container.innerHTML = ''

    fetch(url)
      .then((res) => res.arrayBuffer())
      .then(async (buffer) => {
        if (cancelled) return
        const docx = await import('docx-preview')
        if (cancelled) return
        await docx.renderAsync(buffer, container, undefined, {
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          ignoreFonts: false,
          breakPages: true,
          ignoreLastRenderedPageBreak: true,
          renderHeaders: true,
          renderFooters: true,
          renderFootnotes: true,
          renderEndnotes: true,
        })
        if (!cancelled) {
          setIsLoading(false)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message)
          setIsLoading(false)
        }
      })

    return () => { cancelled = true }
  }, [url, tooLarge])

  if (tooLarge) {
    return <FileTooLargeMessage fileSize={fileSize} limit={OFFICE_PREVIEW_MAX_BYTES} />
  }

  if (error) {
    return <div className="p-4 text-sm text-destructive">Failed to load document: {error}</div>
  }

  return (
    <div className="flex-1 overflow-auto relative">
      {isLoading && (
        <div className="absolute inset-0 p-6 space-y-4 z-10">
          <Skeleton className="h-5 w-48" />
          <div className="space-y-2.5">
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-3.5 w-[90%]" />
            <Skeleton className="h-3.5 w-[75%]" />
          </div>
          <Skeleton className="h-40 w-full rounded-lg" />
          <div className="space-y-2.5">
            <Skeleton className="h-3.5 w-[85%]" />
            <Skeleton className="h-3.5 w-[60%]" />
          </div>
        </div>
      )}
      <div ref={containerRef} className="docx-preview-container" />
    </div>
  )
}

// ============================================================================
// PDF Preview (react-pdf / PDF.js)
// ============================================================================

function PdfPreview({ url }: { url: string }): JSX.Element {
  const [numPages, setNumPages] = useState<number>(0)
  const [error, setError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState<number>(0)

  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width)
      }
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center text-sm text-destructive">
        Failed to load PDF: {error}
      </div>
    )
  }

  return (
    <div ref={containerRef} className="flex-1 overflow-auto">
      <Document
        file={url}
        onLoadSuccess={({ numPages: n }) => setNumPages(n)}
        onLoadError={(err) => setError(err.message)}
        loading={
          <div className="p-6 space-y-4">
            <Skeleton className="h-5 w-48" />
            <div className="space-y-2.5">
              <Skeleton className="h-3.5 w-full" />
              <Skeleton className="h-3.5 w-[90%]" />
              <Skeleton className="h-3.5 w-[75%]" />
            </div>
            <Skeleton className="h-[600px] w-full rounded-lg" />
          </div>
        }
      >
        {numPages > 0 && Array.from({ length: numPages }, (_, i) => (
          <Page
            key={i}
            pageNumber={i + 1}
            width={containerWidth > 0 ? containerWidth - 2 : undefined}
            renderTextLayer={true}
            renderAnnotationLayer={true}
            className="mb-2"
          />
        ))}
      </Document>
    </div>
  )
}

// ============================================================================
// Image Preview
// ============================================================================

function ImagePreview({ url, alt }: { url: string; alt: string }): JSX.Element {
  const [isLoading, setIsLoading] = useState(true)

  return (
    <div className="relative flex flex-1 items-center justify-center overflow-auto p-4">
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}
      <img
        src={url}
        alt={alt}
        onLoad={() => setIsLoading(false)}
        className="max-h-full max-w-full object-contain"
      />
    </div>
  )
}

// ============================================================================
// Metadata Fallback
// ============================================================================

function MetadataView({ file, onDownload, onOpenExternal }: {
  file: FolderFileListItem
  onDownload?: () => void
  onOpenExternal?: () => void
}): JSX.Element {
  const Icon = getFileIcon(file.file_extension)

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6">
      <div className="rounded-2xl bg-muted/50 p-6">
        <Icon className="h-16 w-16 text-muted-foreground/50" />
      </div>
      <div className="text-center space-y-1.5">
        <p className="text-lg font-medium text-foreground">{file.display_name}</p>
        <p className="text-sm text-muted-foreground">
          .{file.file_extension} &bull; {formatFileSize(file.file_size)}
        </p>
      </div>
      <div className="text-center space-y-3">
        <p className="text-sm text-muted-foreground">
          This file type is not supported for inline preview.
        </p>
        <div className="flex items-center gap-2 justify-center">
          <Button variant="outline" size="sm" onClick={onDownload}>
            <Download className="h-4 w-4 mr-1.5" />
            Download
          </Button>
          <Button variant="outline" size="sm" onClick={onOpenExternal}>
            <ExternalLink className="h-4 w-4 mr-1.5" />
            Open in App
          </Button>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function FileViewerPanel({ file, className }: FileViewerPanelProps): JSX.Element {
  const { data: downloadUrl, isLoading: isUrlLoading } = useFileDownloadUrl(file.id)
  const { searchHighlightTerms } = useKnowledgeBase()
  const contentAreaRef = useRef<HTMLDivElement>(null)

  // MutationObserver-based: auto-detects when async content appears and highlights
  useFileSearchHighlight(contentAreaRef, searchHighlightTerms)

  const ext = file.file_extension.toLowerCase()
  const mime = file.mime_type

  // Determine what kind of preview to show
  const previewType = useMemo(() => {
    if (isImage(mime)) return 'image' as const
    if (isPdf(mime)) return 'pdf' as const
    if (isVideo(mime)) return 'video' as const
    if (isAudio(mime)) return 'audio' as const
    if (isCsv(ext)) return 'csv' as const
    if (isExcel(ext)) return 'excel' as const
    if (isDocx(ext)) return 'docx' as const
    return 'none' as const
  }, [mime, ext])

  const handleDownload = useCallback(() => {
    if (!downloadUrl) return
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = file.display_name
    link.target = '_blank'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [downloadUrl, file.display_name])

  const handleOpenExternal = useCallback(() => {
    if (downloadUrl) {
      window.electronAPI?.openExternal?.(downloadUrl)
    }
  }, [downloadUrl])

  return (
    <div className={cn('flex-1 flex flex-col min-w-0 min-h-0', className)}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-background/95 backdrop-blur-sm">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-medium text-sm text-foreground truncate">
            {file.display_name}
          </span>
          <span className="text-xs text-muted-foreground shrink-0">
            {formatFileSize(file.file_size)}
          </span>

          {/* Extraction status badge */}
          <ExtractionBadge status={file.extraction_status} />

          {/* Embedding status — uses same badge as native documents */}
          <DocumentStatusBadge
            documentId={file.id}
            embeddingStatus={file.embedding_status}
            entityType="file"
            variant="badge"
          />
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleDownload}
            disabled={!downloadUrl}
            title="Download"
          >
            <Download className="h-4 w-4" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleOpenExternal}
            disabled={!downloadUrl}
            title="Open in App"
          >
            <ExternalLink className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Content area — selectable enables text selection (global user-select: none) */}
      <div ref={contentAreaRef} className="selectable flex-1 flex flex-col min-h-0 overflow-hidden">
        {isUrlLoading ? (
          <div className="flex-1 p-6 space-y-4">
            <Skeleton className="h-5 w-48" />
            <div className="space-y-2.5">
              <Skeleton className="h-3.5 w-full" />
              <Skeleton className="h-3.5 w-[90%]" />
              <Skeleton className="h-3.5 w-[75%]" />
            </div>
            <Skeleton className="h-40 w-full rounded-lg" />
            <div className="space-y-2.5">
              <Skeleton className="h-3.5 w-[85%]" />
              <Skeleton className="h-3.5 w-[60%]" />
            </div>
          </div>
        ) : !downloadUrl ? (
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
            Failed to load file URL
          </div>
        ) : (
          <>
            {previewType === 'image' && (
              <ImagePreview url={downloadUrl} alt={file.display_name} />
            )}
            {previewType === 'pdf' && (
              <PdfPreview url={downloadUrl} />
            )}
            {previewType === 'video' && (
              <div className="flex-1 flex items-center justify-center p-4">
                <video
                  src={downloadUrl}
                  controls
                  className="max-h-full max-w-full rounded-lg"
                >
                  Your browser does not support video playback.
                </video>
              </div>
            )}
            {previewType === 'audio' && (
              <div className="flex-1 flex flex-col items-center justify-center gap-4">
                <FileAudio className="h-20 w-20 text-muted-foreground/40" />
                <audio src={downloadUrl} controls className="w-full max-w-md">
                  Your browser does not support audio playback.
                </audio>
              </div>
            )}
            {previewType === 'csv' && <CsvPreview url={downloadUrl} fileSize={file.file_size} />}
            {previewType === 'excel' && <ExcelPreview url={downloadUrl} fileSize={file.file_size} />}
            {previewType === 'docx' && <DocxPreview url={downloadUrl} fileSize={file.file_size} />}
            {previewType === 'none' && <MetadataView file={file} onDownload={handleDownload} onOpenExternal={handleOpenExternal} />}
          </>
        )}
      </div>
    </div>
  )
}

export default FileViewerPanel
