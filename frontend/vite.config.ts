import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    // jsdom costs ~15 s of start-up per file (Vitest's own "environment" line
    // summed to 215 s for 18 files). The pure-function suites under lib/ and
    // xp/ don't touch the DOM: node for them, jsdom for the rest. First match
    // wins, so eventDates (reads the browser's date) stays on jsdom.
    environmentMatchGlobs: [
      ['src/lib/eventDates.test.ts', 'jsdom'],
      ['src/lib/**', 'node'],
      ['src/components/xp/**', 'node'],
    ],
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
