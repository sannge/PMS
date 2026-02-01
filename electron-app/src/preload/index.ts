/**
 * Electron Preload Script
 *
 * This script exposes secure APIs to the renderer process via contextBridge.
 * It runs in an isolated context with access to both Node.js and DOM APIs.
 *
 * Security principles:
 * - Never expose ipcRenderer directly
 * - Only expose specific, controlled API methods
 * - Validate data before sending to main process
 * - Use invoke for request-response patterns
 * - Use on/off for event subscriptions
 */

import { contextBridge, ipcRenderer, IpcRendererEvent } from 'electron'

// Type definitions for exposed APIs
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

// Type for the exposed electronAPI
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
}

// Store for notification callbacks
const notificationCallbacks = new Set<(notification: NotificationPayload) => void>()
const webSocketCallbacks = new Set<(message: { type: string; payload: unknown }) => void>()
const maximizedCallbacks = new Set<(isMaximized: boolean) => void>()
const beforeQuitCallbacks = new Set<() => void>()

// Setup IPC listeners
ipcRenderer.on('notification', (_event: IpcRendererEvent, notification: NotificationPayload) => {
  notificationCallbacks.forEach((callback) => callback(notification))
})

ipcRenderer.on('websocket-message', (_event: IpcRendererEvent, message: { type: string; payload: unknown }) => {
  webSocketCallbacks.forEach((callback) => callback(message))
})

ipcRenderer.on('window-maximized-change', (_event: IpcRendererEvent, isMaximized: boolean) => {
  maximizedCallbacks.forEach((callback) => callback(isMaximized))
})

ipcRenderer.on('before-quit-save', () => {
  beforeQuitCallbacks.forEach((callback) => callback())
})

// Expose protected APIs to renderer via contextBridge
contextBridge.exposeInMainWorld('electronAPI', {
  // Platform information
  platform: process.platform,
  versions: {
    node: process.versions.node,
    chrome: process.versions.chrome,
    electron: process.versions.electron
  },

  // Generic API fetch method
  fetch: <T = unknown>(endpoint: string, options: ApiRequestOptions = {}) =>
    ipcRenderer.invoke('api:fetch', { endpoint, options }) as Promise<ApiResponse<T>>,

  // Convenience methods for common HTTP methods
  get: <T = unknown>(endpoint: string, headers?: Record<string, string>) =>
    ipcRenderer.invoke('api:fetch', {
      endpoint,
      options: { method: 'GET', headers }
    }) as Promise<ApiResponse<T>>,

  post: <T = unknown>(endpoint: string, body?: unknown, headers?: Record<string, string>) =>
    ipcRenderer.invoke('api:fetch', {
      endpoint,
      options: { method: 'POST', body, headers }
    }) as Promise<ApiResponse<T>>,

  put: <T = unknown>(endpoint: string, body?: unknown, headers?: Record<string, string>) =>
    ipcRenderer.invoke('api:fetch', {
      endpoint,
      options: { method: 'PUT', body, headers }
    }) as Promise<ApiResponse<T>>,

  patch: <T = unknown>(endpoint: string, body?: unknown, headers?: Record<string, string>) =>
    ipcRenderer.invoke('api:fetch', {
      endpoint,
      options: { method: 'PATCH', body, headers }
    }) as Promise<ApiResponse<T>>,

  delete: <T = unknown>(endpoint: string, headers?: Record<string, string>) =>
    ipcRenderer.invoke('api:fetch', {
      endpoint,
      options: { method: 'DELETE', headers }
    }) as Promise<ApiResponse<T>>,

  // File upload - accepts serializable data
  uploadFile: (
    file: { name: string; type: string; data: ArrayBuffer },
    bucket: string,
    options?: FileUploadOptions
  ) =>
    ipcRenderer.invoke('storage:upload', { file, bucket, options }) as Promise<{
      id: string
      url: string
      key: string
    }>,

  // File download
  downloadFile: (fileId: string) =>
    ipcRenderer.invoke('storage:download', { fileId }) as Promise<FileDownloadResult>,

  // Get presigned URL for file
  getFileUrl: (fileId: string) =>
    ipcRenderer.invoke('storage:getUrl', { fileId }) as Promise<string>,

  // Show desktop notification
  showNotification: (options: ShowNotificationOptions) =>
    ipcRenderer.invoke('notifications:show', options) as Promise<NotificationResult>,

  // Check if notifications are supported
  isNotificationSupported: () =>
    ipcRenderer.invoke('notifications:isSupported') as Promise<boolean>,

  // Close a specific notification
  closeNotification: (id: string) =>
    ipcRenderer.invoke('notifications:close', { id }) as Promise<{ success: boolean }>,

  // Close all notifications
  closeAllNotifications: () =>
    ipcRenderer.invoke('notifications:closeAll') as Promise<{ success: boolean }>,

  // Notification subscription - returns unsubscribe function
  onNotification: (callback: (notification: NotificationPayload) => void) => {
    notificationCallbacks.add(callback)
    return () => {
      notificationCallbacks.delete(callback)
    }
  },

  // Remove notification listener
  offNotification: (callback: (notification: NotificationPayload) => void) => {
    notificationCallbacks.delete(callback)
  },

  // WebSocket message subscription
  onWebSocketMessage: (callback: (message: { type: string; payload: unknown }) => void) => {
    webSocketCallbacks.add(callback)
    return () => {
      webSocketCallbacks.delete(callback)
    }
  },

  // Send WebSocket message
  sendWebSocketMessage: (message: { type: string; payload: unknown }) => {
    ipcRenderer.send('websocket:send', message)
  },

  // Window operations
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close: () => ipcRenderer.send('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:isMaximized') as Promise<boolean>,
  onMaximizedChange: (callback: (isMaximized: boolean) => void) => {
    maximizedCallbacks.add(callback)
    return () => {
      maximizedCallbacks.delete(callback)
    }
  },

  // App information
  getAppVersion: () => ipcRenderer.invoke('app:getVersion') as Promise<string>,
  getAppName: () => ipcRenderer.invoke('app:getName') as Promise<string>,

  // Dialog operations
  showOpenDialog: (options: {
    title?: string
    filters?: { name: string; extensions: string[] }[]
    properties?: ('openFile' | 'openDirectory' | 'multiSelections')[]
  }) =>
    ipcRenderer.invoke('dialog:showOpen', options) as Promise<{
      canceled: boolean
      filePaths: string[]
    }>,

  showSaveDialog: (options: {
    title?: string
    defaultPath?: string
    filters?: { name: string; extensions: string[] }[]
  }) =>
    ipcRenderer.invoke('dialog:showSave', options) as Promise<{
      canceled: boolean
      filePath?: string
    }>,

  showMessageBox: (options: {
    type?: 'none' | 'info' | 'error' | 'question' | 'warning'
    title?: string
    message: string
    detail?: string
    buttons?: string[]
  }) => ipcRenderer.invoke('dialog:showMessage', options) as Promise<{ response: number }>,

  // Clipboard operations
  writeClipboardText: (text: string) => ipcRenderer.send('clipboard:writeText', text),
  readClipboardText: () => ipcRenderer.invoke('clipboard:readText') as Promise<string>,

  // Shell operations
  openExternal: (url: string) => ipcRenderer.invoke('shell:openExternal', url) as Promise<void>,
  openPath: (path: string) => ipcRenderer.invoke('shell:openPath', path) as Promise<string>,

  // Before-quit save coordination
  onBeforeQuit: (callback: () => void) => {
    beforeQuitCallbacks.add(callback)
    return () => {
      beforeQuitCallbacks.delete(callback)
    }
  },
  confirmQuitSave: () => {
    ipcRenderer.send('quit-save-complete')
  }
} satisfies ElectronAPI)
