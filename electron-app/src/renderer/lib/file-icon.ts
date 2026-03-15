/**
 * Shared file icon utility.
 *
 * Maps file extensions to lucide-react icon components.
 * Used by file-viewer-panel and folder-tree-item.
 */

import {
  FileText,
  FileSpreadsheet,
  FileImage,
  FileVideo,
  FileAudio,
  File,
  FileCode,
  FileArchive,
  Presentation,
  type LucideIcon,
} from 'lucide-react'

/**
 * Returns the appropriate lucide icon component for a given file extension.
 * Accepts extensions with or without a leading dot (e.g. "pdf" or ".pdf").
 */
export function getFileIcon(extension: string): LucideIcon {
  const ext = extension.toLowerCase().replace(/^\./, '')
  switch (ext) {
    case 'pdf':
    case 'docx':
    case 'doc':
    case 'txt':
    case 'rtf':
    case 'odt':
    case 'md':
      return FileText
    case 'xlsx':
    case 'xls':
    case 'xlsm':
    case 'xlsb':
    case 'csv':
    case 'tsv':
    case 'ods':
      return FileSpreadsheet
    case 'pptx':
    case 'ppt':
    case 'odp':
      return Presentation
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'svg':
    case 'webp':
    case 'bmp':
    case 'ico':
      return FileImage
    case 'mp4':
    case 'webm':
    case 'avi':
    case 'mov':
      return FileVideo
    case 'mp3':
    case 'wav':
    case 'ogg':
    case 'flac':
      return FileAudio
    case 'zip':
    case 'rar':
    case '7z':
    case 'tar':
    case 'gz':
      return FileArchive
    case 'js':
    case 'ts':
    case 'jsx':
    case 'tsx':
    case 'py':
    case 'java':
    case 'cpp':
    case 'c':
    case 'rs':
    case 'go':
    case 'html':
    case 'css':
    case 'json':
    case 'xml':
    case 'yaml':
    case 'yml':
      return FileCode
    default:
      return File
  }
}
