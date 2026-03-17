# Desktop Releases & OTA Updates

PM Desktop uses `electron-updater` with GitHub Releases for over-the-air (OTA) updates. Users receive update notifications automatically after launch.

## How It Works

1. **Build** — `electron-vite build` compiles the main/preload/renderer processes
2. **Package** — `electron-builder` creates an NSIS installer (`.exe`) and a `latest.yml` manifest
3. **Publish** — `electron-builder --publish always` uploads both to a GitHub Release tagged with the version
4. **Update check** — On launch, `electron-updater` fetches `latest.yml` from GitHub and compares versions
5. **Download** — If a newer version exists, the user is notified and can trigger a download
6. **Install** — After download, the update installs on next app restart (or immediately via `installUpdate()`)

## Prerequisites

### GitHub Personal Access Token

electron-builder needs a `GH_TOKEN` to create releases and upload artifacts.

1. Go to **github.com > Settings > Developer settings > Personal access tokens > Tokens (classic)**
2. Generate a new token with the **`repo`** scope
3. Set it as an environment variable before publishing:

```bash
# Bash / Git Bash
export GH_TOKEN=ghp_your_token_here

# PowerShell
$env:GH_TOKEN = "ghp_your_token_here"
```

### Administrator Terminal (Windows)

On Windows, run the build from an **Administrator** terminal. electron-builder extracts signing tools that require symlink privileges. Without Admin, the build fails with `Cannot create symbolic link` errors.

## Publishing a Release

```bash
cd electron-app

# 1. Bump version in package.json
npm version patch   # 1.0.1 → 1.0.2 (use minor/major for bigger changes)

# 2. Build all processes (main, preload, renderer)
npx electron-vite build

# 3. Package and publish to GitHub Releases
npx electron-builder --publish always
```

This creates a GitHub Release tagged `v<version>` containing:
- `PM-Desktop-Setup-<version>.exe` — NSIS installer
- `PM-Desktop-Setup-<version>.exe.blockmap` — Delta update block map
- `latest.yml` — Version manifest for auto-updater

## electron-builder Configuration

The build config lives in `electron-app/package.json` under `"build"`:

```json
{
  "build": {
    "appId": "com.pm.desktop",
    "productName": "PM Desktop",
    "publish": {
      "provider": "github",
      "owner": "sannge",
      "repo": "PMS"
    },
    "win": {
      "target": ["nsis"]
    },
    "mac": {
      "target": ["dmg", "zip"],
      "category": "public.app-category.productivity"
    },
    "linux": {
      "target": ["AppImage", "deb"],
      "category": "Office"
    },
    "nsis": {
      "oneClick": false,
      "allowToChangeInstallationDirectory": true
    }
  }
}
```

## Auto-Updater Architecture

### Main Process (`src/main/auto-updater.ts`)

- Checks for updates 5 seconds after app launch (skipped in dev mode)
- Does **not** auto-download — waits for user confirmation
- Auto-installs on app quit if an update was downloaded
- Logs all events via `electron-log`
- Sends status updates to renderer via IPC (`update-status` channel)

### Preload Bridge (`src/preload/index.ts`)

Exposes these methods on `window.electronAPI`:

| Method | Description |
|--------|-------------|
| `checkForUpdates()` | Manually trigger an update check |
| `downloadUpdate()` | Start downloading the available update |
| `installUpdate()` | Quit the app and install the update |
| `onUpdateStatus(callback)` | Subscribe to update status events (returns unsubscribe function) |

### Update Status Events

The `onUpdateStatus` callback receives objects with this shape:

```typescript
interface UpdateStatus {
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
```

## Code Signing

Code signing is **optional** but recommended for public distribution:

- Without signing: Windows SmartScreen shows "Unknown publisher" warning on first install (goes away over time as reputation builds)
- **Standard (OV) certificate**: ~$200-400/year (DigiCert, Sectigo)
- **EV certificate**: ~$400-600/year (eliminates SmartScreen warnings immediately)

Auto-updates via `electron-updater` work fine without code signing.

## Known Issues

- **Windows symlink error**: Run the build from an Administrator terminal (see Prerequisites)
- **"author is missed" warning**: Add `"author": "sannge"` to `package.json`
- **"default Electron icon" warning**: Place your app icon at `electron-app/public/icon.ico`

## Build Output

Current build produces these renderer assets:

| Asset | Size | Notes |
|-------|------|-------|
| `index-*.js` | ~5.4 MB | Main bundle (no code splitting yet) |
| `pdf.worker.min-*.mjs` | ~1.4 MB | PDF.js worker (already chunked) |
| `xlsx-*.js` | ~847 KB | SheetJS (already chunked) |
| `docx-preview-*.js` | ~276 KB | DOCX previewer (already chunked) |
| `index-*.css` | ~167 KB | Tailwind styles |

The main bundle can be optimized with code splitting (recharts, TipTap lazy loading). See the bundle optimization section in the [Frontend Guide](./frontend.md).
