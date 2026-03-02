/**
 * Electron Main Process OAuth Handler
 *
 * Manages the OAuth 2.0 flow for AI provider subscription connections.
 *
 * Flow:
 * 1. Renderer requests OAuth initiation via IPC
 * 2. Main process starts temporary localhost HTTP server
 * 3. Opens BrowserWindow with provider auth URL
 * 4. Provider redirects to localhost callback
 * 5. HTTP server captures code + state
 * 6. Returns result to renderer via IPC
 * 7. Cleans up window + server
 *
 * Security:
 * - Random port (0 = OS-assigned)
 * - Session partition (isolated cookies)
 * - 5-minute timeout
 * - Origin validation on callback
 */

import { BrowserWindow, ipcMain } from 'electron'
import { createServer, type Server, type IncomingMessage, type ServerResponse } from 'http'
import { URL } from 'url'

// ============================================================================
// Types
// ============================================================================

interface OAuthResult {
  code: string
  state: string
  redirectUri: string
}

// ============================================================================
// Constants
// ============================================================================

const OAUTH_TIMEOUT_MS = 5 * 60 * 1000 // 5 minutes

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

// ============================================================================
// OAuth Window
// ============================================================================

function createOAuthWindow(authUrl: string): BrowserWindow {
  const window = new BrowserWindow({
    width: 600,
    height: 700,
    webPreferences: {
      partition: 'oauth-session', // Isolated session — no cookie leakage
      nodeIntegration: false,
      contextIsolation: true,
    },
    autoHideMenuBar: true,
    title: 'Connect AI Subscription',
  })

  window.loadURL(authUrl)
  return window
}

// ============================================================================
// Localhost Callback Server
// ============================================================================

async function startCallbackServer(): Promise<{
  server: Server
  port: number
  callbackPromise: Promise<OAuthResult>
}> {
  return new Promise((resolveSetup, rejectSetup) => {
    let resolveCallback: ((result: OAuthResult) => void) | null = null
    let rejectCallback: ((error: Error) => void) | null = null

    const callbackPromise = new Promise<OAuthResult>((resolve, reject) => {
      resolveCallback = resolve
      rejectCallback = reject
    })

    const server = createServer((req: IncomingMessage, res: ServerResponse) => {
      // Validate request is from localhost
      const host = req.headers.host || ''
      if (!host.startsWith('127.0.0.1') && !host.startsWith('localhost')) {
        res.writeHead(403, { 'Content-Type': 'text/plain' })
        res.end('Forbidden')
        return
      }

      const url = new URL(req.url || '/', `http://${host}`)

      if (url.pathname === '/oauth/callback') {
        const code = url.searchParams.get('code')
        const state = url.searchParams.get('state')
        const error = url.searchParams.get('error')

        if (error) {
          res.writeHead(200, { 'Content-Type': 'text/html' })
          res.end(`
            <!DOCTYPE html>
            <html>
            <head><title>Authorization Failed</title></head>
            <body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#1a1a2e;color:#e0e0e0;">
              <div style="text-align:center;max-width:400px;padding:2rem;">
                <h2 style="color:#ef4444;">Authorization Failed</h2>
                <p>The provider returned an error: ${escapeHtml(error)}</p>
                <p style="color:#888;">You can close this window.</p>
              </div>
            </body>
            </html>
          `)
          rejectCallback?.(new Error(`OAuth authorization failed: ${error}`))
          return
        }

        if (!code || !state) {
          res.writeHead(400, { 'Content-Type': 'text/plain' })
          res.end('Missing code or state parameter')
          rejectCallback?.(new Error('Missing code or state in OAuth callback'))
          return
        }

        res.writeHead(200, { 'Content-Type': 'text/html' })
        res.end(`
          <!DOCTYPE html>
          <html>
          <head><title>Authorization Complete</title></head>
          <body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#1a1a2e;color:#e0e0e0;">
            <div style="text-align:center;max-width:400px;padding:2rem;">
              <h2 style="color:#22c55e;">Authorization Successful</h2>
              <p>You can close this window and return to PMS.</p>
            </div>
          </body>
          </html>
        `)

        resolveCallback?.({ code, state, redirectUri: '' })
        return
      }

      res.writeHead(404, { 'Content-Type': 'text/plain' })
      res.end('Not Found')
    })

    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      if (!address || typeof address === 'string') {
        rejectSetup(new Error('Failed to start callback server'))
        return
      }
      resolveSetup({ server, port: address.port, callbackPromise })
    })

    server.on('error', (err) => {
      rejectSetup(err)
    })
  })
}

// ============================================================================
// Wait for Callback (with timeout and window close)
// ============================================================================

async function waitForCallback(
  callbackPromise: Promise<OAuthResult>,
  server: Server,
  authWindow: BrowserWindow,
): Promise<OAuthResult> {
  return new Promise<OAuthResult>((resolve, reject) => {
    let settled = false

    const cleanup = (): void => {
      if (settled) return
      settled = true
      clearTimeout(timeoutId)
      // Remove window close listener to avoid double-fire
      authWindow.removeAllListeners('closed')
    }

    // Timeout after 5 minutes
    const timeoutId = setTimeout(() => {
      cleanup()
      try { authWindow.destroy() } catch { /* window may already be destroyed */ }
      try { server.close() } catch { /* server may already be closed */ }
      reject(new Error('OAuth flow timed out after 5 minutes'))
    }, OAUTH_TIMEOUT_MS)

    // User closed window
    authWindow.on('closed', () => {
      cleanup()
      try { server.close() } catch { /* ignore */ }
      reject(new Error('OAuth window was closed by user'))
    })

    // Callback received
    callbackPromise
      .then((result) => {
        cleanup()
        resolve(result)
      })
      .catch((err) => {
        cleanup()
        reject(err)
      })
  })
}

// ============================================================================
// Register IPC Handlers
// ============================================================================

export function registerOAuthHandlers(): void {
  ipcMain.handle(
    'oauth:initiate',
    async (_event, authUrl: string): Promise<OAuthResult> => {
      // 1. Start localhost HTTP server on random port
      const { server, port, callbackPromise } = await startCallbackServer()

      // 2. Append redirect_uri to auth URL if needed (for the callback server)
      const redirectUri = `http://127.0.0.1:${port}/oauth/callback`
      const fullAuthUrl = appendRedirectUri(authUrl, redirectUri)

      // 3. Open BrowserWindow with auth URL
      const authWindow = createOAuthWindow(fullAuthUrl)

      try {
        // 4. Wait for callback (with timeout)
        const result = await waitForCallback(callbackPromise, server, authWindow)

        // 5. Attach the actual redirect_uri (with real port) for token exchange
        result.redirectUri = redirectUri

        // 6. Cleanup
        try { authWindow.destroy() } catch { /* already destroyed */ }
        server.close()

        return result
      } catch (err) {
        // Cleanup on error
        try { authWindow.destroy() } catch { /* already destroyed */ }
        server.close()
        throw err
      }
    },
  )
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * Append or replace redirect_uri in the auth URL.
 * The backend generates the auth URL, but the redirect_uri must point
 * to the dynamically assigned localhost port.
 */
function appendRedirectUri(authUrl: string, redirectUri: string): string {
  const url = new URL(authUrl)
  url.searchParams.set('redirect_uri', redirectUri)
  return url.toString()
}
