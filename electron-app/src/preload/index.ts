// Preload script - to be implemented in subtask-2-5
import { contextBridge } from 'electron'

// Expose protected APIs to renderer
contextBridge.exposeInMainWorld('electronAPI', {
  // API methods will be added in subtask-2-5
  platform: process.platform
})
