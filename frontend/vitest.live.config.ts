import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/** Opt-in end-to-end run against a real backend: LIVE_BACKEND=1 npx vitest run -c vitest.live.config.ts */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['src/test/live.test.tsx'],
    setupFiles: ['./src/test/live-setup.ts'],
    testTimeout: 120_000,
  },
})
