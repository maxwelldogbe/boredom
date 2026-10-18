/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Full backend WebSocket URL (production). Unset in dev: the Vite proxy is used. */
  readonly VITE_WS_URL?: string
  /** Backend HTTP base URL without trailing slash (production). Unset in dev. */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
