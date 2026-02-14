/// <reference types="vite/client" />

/**
 * Type definitions for Vite environment variables
 */
interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_MINIO_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
