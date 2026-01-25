/**
 * Electron Main Process Entry Point
 *
 * Security Configuration:
 * - contextIsolation: true - Isolates preload scripts from renderer
 * - nodeIntegration: false - Prevents renderer from accessing Node.js
 * - sandbox: true - Enables Chromium sandbox for renderer
 * - webSecurity: true - Enforces same-origin policy
 */

// Load environment variables from .env file FIRST (before other imports that use env vars)
import { config } from 'dotenv'
import { resolve } from 'path'
config({ path: resolve(__dirname, '../../.env') })

import { app, BrowserWindow, shell, session, Menu, MenuItemConstructorOptions } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { registerIpcHandlers } from './ipc/handlers'
import { registerNotificationHandlers } from './notifications'

// Support custom user data directory via environment variable (must be set before app ready)
if (process.env.ELECTRON_USER_DATA_DIR) {
  const userDataPath = resolve(process.env.ELECTRON_USER_DATA_DIR)
  app.setPath('userData', userDataPath)
}

// Enable remote debugging for development/testing with dynamic port
if (is.dev) {
  // Use port from env or default to 9222, allowing multiple instances
  const debugPort = process.env.ELECTRON_DEBUG_PORT || '9222'
  app.commandLine.appendSwitch('remote-debugging-port', debugPort)
}

// Keep a global reference of the window object to prevent garbage collection
let mainWindow: BrowserWindow | null = null

/**
 * Creates the main application window with secure configuration
 */
function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 768,
    show: false, // Don't show until ready-to-show event
    frame: false, // Remove native title bar for custom design
    titleBarStyle: 'hidden', // Hide title bar on macOS
    titleBarOverlay: false, // No overlay - fully custom title bar
    autoHideMenuBar: true, // Hide menu bar by default
    title: 'PMS - Project Management System',
    backgroundColor: '#0f0f12', // Match dark theme background
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      // Security: Isolate preload scripts from renderer context
      contextIsolation: true,
      // Security: Disable Node.js integration in renderer
      nodeIntegration: false,
      // Security: Enable sandbox mode for renderer process
      sandbox: true,
      // Security: Enforce same-origin policy
      webSecurity: true,
      // Security: Disable remote module (deprecated but ensure it's off)
      // @ts-expect-error - enableRemoteModule is deprecated but we want to ensure it's disabled
      enableRemoteModule: false,
      // Security: Disable webview tag
      webviewTag: false,
      // Security: Allow running insecure content only in dev mode
      allowRunningInsecureContent: false,
      // Performance: Enable hardware acceleration
      backgroundThrottling: false,
      // Enable spell checker
      spellcheck: true
    }
  })

  // Show window when ready to prevent visual flash
  mainWindow.on('ready-to-show', () => {
    mainWindow?.show()
    mainWindow?.focus()
  })

  // Notify renderer of maximize state changes
  mainWindow.on('maximize', () => {
    mainWindow?.webContents.send('window-maximized-change', true)
  })

  mainWindow.on('unmaximize', () => {
    mainWindow?.webContents.send('window-maximized-change', false)
  })

  // Handle external links - open in default browser
  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // Security: Prevent navigation to untrusted URLs
  mainWindow.webContents.on('will-navigate', (event, url) => {
    const allowedUrls = [
      process.env.ELECTRON_RENDERER_URL || '',
      'file://'
    ]

    const isAllowed = allowedUrls.some(allowed => url.startsWith(allowed))
    if (!isAllowed) {
      event.preventDefault()
    }
  })

  // Load the renderer
  if (is.dev && process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
    // Open DevTools in development mode
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }

  // Clean up reference when window is closed
  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

/**
 * Configure Content Security Policy for enhanced security
 */
function setupContentSecurityPolicy(): void {
  // Get API URL from environment for CSP
  const apiUrl = process.env.VITE_API_URL || 'http://localhost:8001'
  const wsUrl = apiUrl.replace(/^http/, 'ws')
  // Get MinIO URL for file storage (presigned URLs)
  // Note: In electron-vite, VITE_ vars may not be in process.env for main process
  const minioUrl = process.env.VITE_MINIO_URL || 'http://10.18.137.108:9000'

  console.log('[CSP] API URL:', apiUrl)
  console.log('[CSP] MinIO URL:', minioUrl)

  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          is.dev
            ? // Development CSP - more permissive for internal IPs
              "default-src 'self'; " +
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'; " +
              "style-src 'self' 'unsafe-inline'; " +
              `img-src 'self' data: blob: http://localhost:* http://10.18.137.108:* ${minioUrl} https://*; ` +
              "font-src 'self' data:; " +
              `connect-src 'self' http://localhost:* ws://localhost:* http://10.18.137.108:* ${minioUrl}; ` +
              `media-src 'self' blob: http://10.18.137.108:* ${minioUrl}; ` +
              "worker-src 'self' blob:;"
            : // Production CSP - more restrictive
              "default-src 'self'; " +
              "script-src 'self'; " +
              "style-src 'self' 'unsafe-inline'; " +
              `img-src 'self' data: blob: ${minioUrl}; ` +
              "font-src 'self' data:; " +
              `connect-src 'self' ${apiUrl} ${wsUrl} ${minioUrl}; ` +
              `media-src 'self' blob: ${minioUrl};`
        ]
      }
    })
  })
}

/**
 * Configure session security settings
 */
function setupSessionSecurity(): void {
  // Clear storage data on startup for security (optional - comment out if persistence needed)
  // session.defaultSession.clearStorageData({ storages: ['cookies', 'localstorage'] })

  // Set permission request handler
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    const allowedPermissions = ['clipboard-read', 'clipboard-write', 'notifications']

    if (allowedPermissions.includes(permission)) {
      callback(true)
    } else {
      callback(false)
    }
  })

  // Set permission check handler
  session.defaultSession.setPermissionCheckHandler((_webContents, permission) => {
    const allowedPermissions = ['clipboard-read', 'clipboard-write', 'notifications', 'media']
    return allowedPermissions.includes(permission)
  })
}

/**
 * Create application menu
 */
function createApplicationMenu(): void {
  const isMac = process.platform === 'darwin'

  const template: MenuItemConstructorOptions[] = [
    // App menu (macOS only)
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: 'about' as const },
              { type: 'separator' as const },
              { role: 'services' as const },
              { type: 'separator' as const },
              { role: 'hide' as const },
              { role: 'hideOthers' as const },
              { role: 'unhide' as const },
              { type: 'separator' as const },
              { role: 'quit' as const }
            ]
          }
        ]
      : []),
    // File menu
    {
      label: 'File',
      submenu: [
        isMac ? { role: 'close' } : { role: 'quit' }
      ]
    },
    // Edit menu
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        ...(isMac
          ? [
              { role: 'pasteAndMatchStyle' as const },
              { role: 'delete' as const },
              { role: 'selectAll' as const }
            ]
          : [
              { role: 'delete' as const },
              { type: 'separator' as const },
              { role: 'selectAll' as const }
            ])
      ]
    },
    // View menu
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    },
    // Window menu
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        ...(isMac
          ? [
              { type: 'separator' as const },
              { role: 'front' as const },
              { type: 'separator' as const },
              { role: 'window' as const }
            ]
          : [{ role: 'close' as const }])
      ]
    },
    // Help menu
    {
      role: 'help',
      submenu: [
        {
          label: 'Documentation',
          click: async () => {
            await shell.openExternal('https://github.com/your-repo/pm-desktop')
          }
        },
        { type: 'separator' },
        {
          label: 'About PM Desktop',
          click: () => {
            app.showAboutPanel()
          }
        }
      ]
    }
  ]

  const menu = Menu.buildFromTemplate(template)
  Menu.setApplicationMenu(menu)
}

/**
 * Main application initialization
 */
app.whenReady().then(() => {
  // Set app user model id for Windows
  electronApp.setAppUserModelId('com.pm.desktop')

  // Set about panel info
  app.setAboutPanelOptions({
    applicationName: 'PMS - Project Management System',
    applicationVersion: app.getVersion(),
    copyright: 'Copyright 2024-2026',
    version: app.getVersion()
  })

  // Watch for shortcut events in development
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // Setup security configurations
  setupContentSecurityPolicy()
  setupSessionSecurity()

  // Register IPC handlers for renderer communication
  registerIpcHandlers()

  // Register notification handlers for desktop alerts
  registerNotificationHandlers()

  // Create application menu
  createApplicationMenu()

  // Create the main window
  createWindow()

  // macOS: Re-create window when dock icon is clicked
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

// Quit when all windows are closed, except on macOS
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// Security: Handle certificate errors
app.on('certificate-error', (event, _webContents, url, _error, _certificate, callback) => {
  // In development, ignore certificate errors for localhost
  if (is.dev && url.includes('localhost')) {
    event.preventDefault()
    callback(true)
  } else {
    callback(false)
  }
})

// Prevent multiple instances (disabled for testing)
// const gotTheLock = app.requestSingleInstanceLock()
//
// if (!gotTheLock) {
//   app.quit()
// } else {
//   app.on('second-instance', () => {
//     // Focus the main window if a second instance is attempted
//     if (mainWindow) {
//       if (mainWindow.isMinimized()) {
//         mainWindow.restore()
//       }
//       mainWindow.focus()
//     }
//   })
// }

// Export for potential testing
export { createWindow, mainWindow }
