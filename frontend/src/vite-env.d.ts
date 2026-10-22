/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `mock` makes the app use the mock service; otherwise it talks to the backend. */
  readonly VITE_SESSION_SERVICE?: string
  /** Where the backend is; empty means this origin (the dev server proxies /api). */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
