import path from 'node:path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      // Dev-time proxy to the FastAPI backend (src/assayingest/api) -- the
      // demo build instead serves both from one process via app.frontend().
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    // Pure logic (state/fieldSet.ts, lib/api.ts) -- no DOM needed.
    environment: 'node',
  },
})
