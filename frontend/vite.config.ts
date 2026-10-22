import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the backend, so the app reaches it on its own
// origin. INTENTUNE_API_URL points elsewhere (the backend's API_HOST:API_PORT).
const backend = process.env.INTENTUNE_API_URL ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: backend, changeOrigin: false },
    },
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
