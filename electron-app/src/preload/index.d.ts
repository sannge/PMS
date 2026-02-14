/**
 * Type definitions for the Electron preload API
 *
 * This file provides TypeScript declarations for the electronAPI
 * exposed to the renderer process via contextBridge.
 */

export interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  headers?: Record<string, string>
  body?: unknown
  timeout?: number
}

export interface ApiResponse<T = unknown> {
  data: T
  status: number
  statusText: string
  headers: Record<string, string>
}

export interface FileUploadOptions {
  entityType?: 'task' | 'note' | 'comment'
  entityId?: string
  onProgress?: (progress: number) => void
}

export interface FileDownloadResult {
  data: ArrayBuffer
  filename: string
  contentType: string
}

export interface NotificationPayload {
  id: string
  type: string
  title: string
  message: string
  entityType?: string
  entityId?: string
  timestamp: string
}

export interface ShowNotificationOptions {
  title: string
  body: string
  type?: 'info' | 'success' | 'warning' | 'error' | 'task' | 'mention' | 'comment'
  entityType?: string
  entityId?: string
  silent?: boolean
}

export interface NotificationResult {
  id: string
  clicked: boolean
  closed: boolean
}

export interface ElectronAPI {
  // Platform info
  platform: NodeJS.Platform
  versions: {
    node: string
    chrome: string
    electron: string
  }

  // API communication
  fetch: <T = unknown>(endpoint: string, options?: ApiRequestOptions) => Promise<ApiResponse<T>>
  get: <T = unknown>(endpoint: string, headers?: Record<string, string>) => Promise<ApiResponse<T>>
  post: <T = unknown>(
    endpoint: string,
    body?: unknown,
    headers?: Record<string, string>
  ) => Promise<ApiResponse<T>>
  put: <T = unknown>(
    endpoint: string,
    body?: unknown,
    headers?: Record<string, string>
  ) => Promise<ApiResponse<T>>
  patch: <T = unknown>(
    endpoint: string,
    body?: unknown,
    headers?: Record<string, string>
  ) => Promise<ApiResponse<T>>
  delete: <T = unknown>(
    endpoint: string,
    headers?: Record<string, string>
  ) => Promise<ApiResponse<T>>

  // File operations
  uploadFile: (
    file: { name: string; type: string; data: ArrayBuffer },
    bucket: string,
    options?: FileUploadOptions
  ) => Promise<{ id: string; url: string; key: string }>
  downloadFile: (fileId: string) => Promise<FileDownloadResult>
  getFileUrl: (fileId: string) => Promise<string>

  // Desktop notification operations
  showNotification: (options: ShowNotificationOptions) => Promise<NotificationResult>
  isNotificationSupported: () => Promise<boolean>
  closeNotification: (id: string) => Promise<{ success: boolean }>
  closeAllNotifications: () => Promise<{ success: boolean }>

  // Notification events (from main process)
  onNotification: (callback: (notification: NotificationPayload) => void) => () => void
  offNotification: (callback: (notification: NotificationPayload) => void) => void

  // WebSocket events
  onWebSocketMessage: (
    callback: (message: { type: string; payload: unknown }) => void
  ) => () => void
  sendWebSocketMessage: (message: { type: string; payload: unknown }) => void

  // Window operations
  minimize: () => void
  maximize: () => void
  close: () => void
  isMaximized: () => Promise<boolean>
  onMaximizedChange: (callback: (isMaximized: boolean) => void) => () => void

  // App info
  getAppVersion: () => Promise<string>
  getAppName: () => Promise<string>

  // Dialog operations
  showOpenDialog: (options: {
    title?: string
    filters?: { name: string; extensions: string[] }[]
    properties?: ('openFile' | 'openDirectory' | 'multiSelections')[]
  }) => Promise<{ canceled: boolean; filePaths: string[] }>
  showSaveDialog: (options: {
    title?: string
    defaultPath?: string
    filters?: { name: string; extensions: string[] }[]
  }) => Promise<{ canceled: boolean; filePath?: string }>
  showMessageBox: (options: {
    type?: 'none' | 'info' | 'error' | 'question' | 'warning'
    title?: string
    message: string
    detail?: string
    buttons?: string[]
  }) => Promise<{ response: number }>

  // Clipboard operations
  writeClipboardText: (text: string) => void
  readClipboardText: () => Promise<string>

  // Shell operations
  openExternal: (url: string) => Promise<void>
  openPath: (path: string) => Promise<string>

  // Before-quit save coordination
  onBeforeQuit: (callback: () => void) => () => void
  confirmQuitSave: () => void
  cancelQuit: () => void
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}

export {}
