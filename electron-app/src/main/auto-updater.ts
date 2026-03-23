/**
 * Auto-Updater Module
 *
 * Handles OTA updates via GitHub Releases using electron-updater.
 * Communicates update status to the renderer process via IPC.
 */

import { autoUpdater, UpdateInfo, ProgressInfo } from 'electron-updater'
import { BrowserWindow, ipcMain } from 'electron'
import { is } from '@electron-toolkit/utils'
import log from 'electron-log'

// Configure electron-updater to use electron-log
autoUpdater.logger = log
autoUpdater.autoDownload = false
autoUpdater.autoInstallOnAppQuit = true

export interface UpdateStatus {
  status: 'checking' | 'available' | 'not-available' | 'downloading' | 'downloaded' | 'error'
  info?: {
    version?: string
    releaseDate?: string
    releaseNotes?: string
  }
  progress?: {
    percent: number
    bytesPerSecond: number
    transferred: number
    total: number
  }
  error?: string
}

function getMainWindow(): BrowserWindow | null {
  const windows = BrowserWindow.getAllWindows()
  return windows.length > 0 ? windows[0] : null
}

function sendUpdateStatus(status: UpdateStatus): void {
  const win = getMainWindow()
  if (win && !win.isDestroyed()) {
    win.webContents.send('update-status', status)
  }
}

export function setupAutoUpdater(): void {
  // Skip auto-update checks in development
  if (is.dev) {
    log.info('[AutoUpdater] Skipping in development mode')
    return
  }


  // --- Event handlers ---

  autoUpdater.on('checking-for-update', () => {
    log.info('[AutoUpdater] Checking for update...')
    sendUpdateStatus({ status: 'checking' })
  })

  autoUpdater.on('update-available', (info: UpdateInfo) => {
    log.info(`[AutoUpdater] Update available: v${info.version}`)
    sendUpdateStatus({
      status: 'available',
      info: {
        version: info.version,
        releaseDate: info.releaseDate,
        releaseNotes: typeof info.releaseNotes === 'string'
          ? info.releaseNotes
          : undefined
      }
    })
  })

  autoUpdater.on('update-not-available', (info: UpdateInfo) => {
    log.info(`[AutoUpdater] Already up to date: v${info.version}`)
    sendUpdateStatus({
      status: 'not-available',
      info: { version: info.version }
    })
  })

  autoUpdater.on('download-progress', (progress: ProgressInfo) => {
    log.info(`[AutoUpdater] Download progress: ${progress.percent.toFixed(1)}%`)
    sendUpdateStatus({
      status: 'downloading',
      progress: {
        percent: progress.percent,
        bytesPerSecond: progress.bytesPerSecond,
        transferred: progress.transferred,
        total: progress.total
      }
    })
  })

  autoUpdater.on('update-downloaded', (info: UpdateInfo) => {
    log.info(`[AutoUpdater] Update downloaded: v${info.version}`)
    sendUpdateStatus({
      status: 'downloaded',
      info: {
        version: info.version,
        releaseDate: info.releaseDate,
        releaseNotes: typeof info.releaseNotes === 'string'
          ? info.releaseNotes
          : undefined
      }
    })
  })

  autoUpdater.on('error', (error: Error) => {
    log.error('[AutoUpdater] Error:', error.message)
    sendUpdateStatus({
      status: 'error',
      error: error.message
    })
  })

  // --- IPC handlers (renderer can trigger these) ---

  ipcMain.handle('updater:check', async () => {
    try {
      const result = await autoUpdater.checkForUpdates()
      return { success: true, version: result?.updateInfo.version }
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Unknown error'
      log.error('[AutoUpdater] Check failed:', msg)
      return { success: false, error: msg }
    }
  })

  ipcMain.handle('updater:download', async () => {
    try {
      await autoUpdater.downloadUpdate()
      return { success: true }
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Unknown error'
      log.error('[AutoUpdater] Download failed:', msg)
      return { success: false, error: msg }
    }
  })

  ipcMain.handle('updater:install', () => {
    autoUpdater.quitAndInstall(false, true)
  })

  // Check for updates on startup (after a short delay to not block launch)
  setTimeout(() => {
    log.info('[AutoUpdater] Initial update check')
    autoUpdater.checkForUpdates().catch((err) => {
      log.error('[AutoUpdater] Initial check failed:', err.message)
    })
  }, 5000)
}
