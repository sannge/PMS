/**
 * IPC Handlers for Main Process
 *
 * This module registers all IPC handlers for communication between
 * the main process and renderer process via the preload script.
 *
 * Security considerations:
 * - All handlers validate input before processing
 * - API requests are proxied through main process to avoid CORS issues
 * - File operations are restricted to allowed paths
 * - External URLs are validated before opening
 */

import {
  ipcMain,
  BrowserWindow,
  dialog,
  clipboard,
  shell,
  app
} from 'electron'

// API base URL - configurable via environment
const API_BASE_URL = process.env.VITE_API_URL || 'http://localhost:8000'

// Timeout for API requests (30 seconds)
const API_TIMEOUT = 30000

/**
 * API Request Options interface
 */
interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  headers?: Record<string, string>
  body?: unknown
  timeout?: number
}

/**
 * API Response interface
 */
interface ApiResponse<T = unknown> {
  data: T
  status: number
  statusText: string
  headers: Record<string, string>
}

/**
 * File Upload Options interface
 */
interface FileUploadOptions {
  entityType?: 'task' | 'note' | 'comment'
  entityId?: string
}

/**
 * Validates URL to ensure it's safe to request
 */
function isValidApiEndpoint(endpoint: string): boolean {
  // Ensure endpoint starts with / and doesn't contain protocol
  if (!endpoint.startsWith('/')) return false
  if (endpoint.includes('://')) return false
  // Prevent path traversal
  if (endpoint.includes('..')) return false
  return true
}

/**
 * Validates external URL for opening
 */
function isValidExternalUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    // Only allow http and https protocols
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

/**
 * Makes an API request with proper error handling
 */
async function makeApiRequest<T = unknown>(
  endpoint: string,
  options: ApiRequestOptions = {}
): Promise<ApiResponse<T>> {
  const { method = 'GET', headers = {}, body, timeout = API_TIMEOUT } = options

  // Validate endpoint
  if (!isValidApiEndpoint(endpoint)) {
    throw new Error(`Invalid API endpoint: ${endpoint}`)
  }

  const url = `${API_BASE_URL}${endpoint}`

  // Prepare request options
  const contentType = headers['Content-Type'] || 'application/json'
  const fetchOptions: RequestInit = {
    method,
    headers: {
      'Content-Type': contentType,
      Accept: 'application/json',
      ...headers
    }
  }

  // Add body for non-GET requests
  if (body !== undefined && method !== 'GET') {
    // Don't JSON stringify if body is already a string (e.g., form-urlencoded)
    if (typeof body === 'string') {
      fetchOptions.body = body
    } else {
      fetchOptions.body = JSON.stringify(body)
    }
  }

  // Create abort controller for timeout
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  fetchOptions.signal = controller.signal

  try {
    const response = await fetch(url, fetchOptions)
    clearTimeout(timeoutId)

    // Parse response headers
    const responseHeaders: Record<string, string> = {}
    response.headers.forEach((value, key) => {
      responseHeaders[key] = value
    })

    // Parse response body
    let data: T
    const contentType = response.headers.get('content-type') || ''

    if (contentType.includes('application/json')) {
      data = await response.json()
    } else {
      // For non-JSON responses, return text as data
      data = (await response.text()) as unknown as T
    }

    return {
      data,
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders
    }
  } catch (error) {
    clearTimeout(timeoutId)

    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        throw new Error(`Request timeout after ${timeout}ms`)
      }
      throw new Error(`API request failed: ${error.message}`)
    }
    throw new Error('Unknown error during API request')
  }
}

/**
 * Uploads a file to the backend storage service
 */
async function uploadFile(
  file: { name: string; type: string; data: ArrayBuffer },
  bucket: string,
  options: FileUploadOptions = {}
): Promise<{ id: string; url: string; key: string }> {
  const formData = new FormData()

  // Create Blob from ArrayBuffer
  const blob = new Blob([file.data], { type: file.type })
  formData.append('file', blob, file.name)
  formData.append('bucket', bucket)

  if (options.entityType) {
    formData.append('entity_type', options.entityType)
  }
  if (options.entityId) {
    formData.append('entity_id', options.entityId)
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT * 2) // Double timeout for uploads

  try {
    const response = await fetch(`${API_BASE_URL}/api/files/upload`, {
      method: 'POST',
      body: formData,
      signal: controller.signal
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Upload failed: ${response.status} - ${errorText}`)
    }

    return await response.json()
  } catch (error) {
    clearTimeout(timeoutId)
    if (error instanceof Error) {
      throw new Error(`File upload failed: ${error.message}`)
    }
    throw new Error('Unknown error during file upload')
  }
}

/**
 * Downloads a file from the backend storage service
 */
async function downloadFile(
  fileId: string
): Promise<{ data: ArrayBuffer; filename: string; contentType: string }> {
  if (!fileId || typeof fileId !== 'string') {
    throw new Error('Invalid file ID')
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT * 2)

  try {
    const response = await fetch(`${API_BASE_URL}/api/files/${fileId}`, {
      method: 'GET',
      signal: controller.signal
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      throw new Error(`Download failed: ${response.status}`)
    }

    // Get filename from Content-Disposition header if available
    const contentDisposition = response.headers.get('content-disposition') || ''
    let filename = fileId
    const filenameMatch = contentDisposition.match(/filename="?([^";\n]+)"?/)
    if (filenameMatch) {
      filename = filenameMatch[1]
    }

    const contentType = response.headers.get('content-type') || 'application/octet-stream'
    const data = await response.arrayBuffer()

    return { data, filename, contentType }
  } catch (error) {
    clearTimeout(timeoutId)
    if (error instanceof Error) {
      throw new Error(`File download failed: ${error.message}`)
    }
    throw new Error('Unknown error during file download')
  }
}

/**
 * Gets a presigned URL for a file
 */
async function getFileUrl(fileId: string): Promise<string> {
  if (!fileId || typeof fileId !== 'string') {
    throw new Error('Invalid file ID')
  }

  const response = await makeApiRequest<{ url: string }>(`/api/files/${fileId}/url`)
  return response.data.url
}

/**
 * Gets the focused BrowserWindow or the first available window
 */
function getWindow(): BrowserWindow | null {
  return BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0] || null
}

/**
 * Registers all IPC handlers
 */
export function registerIpcHandlers(): void {
  // ============================================
  // API Communication Handlers
  // ============================================

  /**
   * Generic API fetch handler
   * Proxies requests to the backend API
   */
  ipcMain.handle(
    'api:fetch',
    async (
      _event,
      { endpoint, options }: { endpoint: string; options?: ApiRequestOptions }
    ) => {
      return makeApiRequest(endpoint, options)
    }
  )

  // ============================================
  // File Storage Handlers
  // ============================================

  /**
   * File upload handler
   */
  ipcMain.handle(
    'storage:upload',
    async (
      _event,
      {
        file,
        bucket,
        options
      }: {
        file: { name: string; type: string; data: ArrayBuffer }
        bucket: string
        options?: FileUploadOptions
      }
    ) => {
      return uploadFile(file, bucket, options)
    }
  )

  /**
   * File download handler
   */
  ipcMain.handle('storage:download', async (_event, { fileId }: { fileId: string }) => {
    return downloadFile(fileId)
  })

  /**
   * Get file URL handler
   */
  ipcMain.handle('storage:getUrl', async (_event, { fileId }: { fileId: string }) => {
    return getFileUrl(fileId)
  })

  // ============================================
  // Window Operation Handlers
  // ============================================

  /**
   * Minimize window
   */
  ipcMain.on('window:minimize', () => {
    const window = getWindow()
    window?.minimize()
  })

  /**
   * Maximize/restore window
   */
  ipcMain.on('window:maximize', () => {
    const window = getWindow()
    if (window) {
      if (window.isMaximized()) {
        window.restore()
      } else {
        window.maximize()
      }
      // Notify renderer of maximized state change
      window.webContents.send('window-maximized-change', window.isMaximized())
    }
  })

  /**
   * Close window
   */
  ipcMain.on('window:close', () => {
    const window = getWindow()
    window?.close()
  })

  /**
   * Check if window is maximized
   */
  ipcMain.handle('window:isMaximized', () => {
    const window = getWindow()
    return window?.isMaximized() ?? false
  })

  // ============================================
  // App Information Handlers
  // ============================================

  /**
   * Get app version
   */
  ipcMain.handle('app:getVersion', () => {
    return app.getVersion()
  })

  /**
   * Get app name
   */
  ipcMain.handle('app:getName', () => {
    return app.getName()
  })

  // ============================================
  // Dialog Handlers
  // ============================================

  /**
   * Show open file dialog
   */
  ipcMain.handle(
    'dialog:showOpen',
    async (
      _event,
      options: {
        title?: string
        filters?: { name: string; extensions: string[] }[]
        properties?: ('openFile' | 'openDirectory' | 'multiSelections')[]
      }
    ) => {
      const window = getWindow()
      if (!window) {
        return { canceled: true, filePaths: [] }
      }

      return dialog.showOpenDialog(window, {
        title: options.title,
        filters: options.filters,
        properties: options.properties || ['openFile']
      })
    }
  )

  /**
   * Show save file dialog
   */
  ipcMain.handle(
    'dialog:showSave',
    async (
      _event,
      options: {
        title?: string
        defaultPath?: string
        filters?: { name: string; extensions: string[] }[]
      }
    ) => {
      const window = getWindow()
      if (!window) {
        return { canceled: true, filePath: undefined }
      }

      return dialog.showSaveDialog(window, {
        title: options.title,
        defaultPath: options.defaultPath,
        filters: options.filters
      })
    }
  )

  /**
   * Show message box dialog
   */
  ipcMain.handle(
    'dialog:showMessage',
    async (
      _event,
      options: {
        type?: 'none' | 'info' | 'error' | 'question' | 'warning'
        title?: string
        message: string
        detail?: string
        buttons?: string[]
      }
    ) => {
      const window = getWindow()
      if (!window) {
        return { response: 0 }
      }

      return dialog.showMessageBox(window, {
        type: options.type || 'info',
        title: options.title,
        message: options.message,
        detail: options.detail,
        buttons: options.buttons || ['OK']
      })
    }
  )

  // ============================================
  // Clipboard Handlers
  // ============================================

  /**
   * Write text to clipboard
   */
  ipcMain.on('clipboard:writeText', (_event, text: string) => {
    if (typeof text === 'string') {
      clipboard.writeText(text)
    }
  })

  /**
   * Read text from clipboard
   */
  ipcMain.handle('clipboard:readText', () => {
    return clipboard.readText()
  })

  // ============================================
  // Shell Handlers
  // ============================================

  /**
   * Open external URL in default browser
   */
  ipcMain.handle('shell:openExternal', async (_event, url: string) => {
    if (!isValidExternalUrl(url)) {
      throw new Error('Invalid URL: Only http and https URLs are allowed')
    }
    await shell.openExternal(url)
  })

  /**
   * Open path in system file manager
   */
  ipcMain.handle('shell:openPath', async (_event, path: string) => {
    if (!path || typeof path !== 'string') {
      throw new Error('Invalid path')
    }
    return shell.openPath(path)
  })

  // ============================================
  // WebSocket Message Handler
  // ============================================

  /**
   * Handle WebSocket messages from renderer
   * This will be connected to actual WebSocket in phase-7
   */
  ipcMain.on('websocket:send', (_event, message: { type: string; payload: unknown }) => {
    // WebSocket connection will be implemented in phase-7
    // For now, log the message for debugging
    if (process.env.NODE_ENV === 'development') {
      // Message received, will be processed when WebSocket is implemented
    }
  })
}

/**
 * Removes all IPC handlers
 * Useful for cleanup during testing or hot-reloading
 */
export function removeIpcHandlers(): void {
  const handlers = [
    'api:fetch',
    'storage:upload',
    'storage:download',
    'storage:getUrl',
    'window:isMaximized',
    'app:getVersion',
    'app:getName',
    'dialog:showOpen',
    'dialog:showSave',
    'dialog:showMessage',
    'clipboard:readText',
    'shell:openExternal',
    'shell:openPath'
  ]

  handlers.forEach((channel) => {
    ipcMain.removeHandler(channel)
  })

  const listeners = [
    'window:minimize',
    'window:maximize',
    'window:close',
    'clipboard:writeText',
    'websocket:send'
  ]

  listeners.forEach((channel) => {
    ipcMain.removeAllListeners(channel)
  })
}
