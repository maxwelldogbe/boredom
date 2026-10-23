/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The Django backend (one process only). Dev requests to /api and /ws are proxied to it.
const BACKEND = 'http://localhost:8000'
// shared/constants.json lives outside this project; allow the dev server to read it.
const SHARED_DIR = fileURLToPath(new URL('../shared', import.meta.url))

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // reachable from phones on the LAN
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND, ws: true, changeOrigin: true },
      // Staff dashboard: the Django admin login, its static files and CSV exports.
      '/manage': { target: BACKEND, changeOrigin: true },
      '/static': { target: BACKEND, changeOrigin: true },
    },
    fs: { allow: ['.', SHARED_DIR] },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
