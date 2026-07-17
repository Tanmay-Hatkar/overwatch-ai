/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Forward backend requests to FastAPI on port 8000.
      // Avoids CORS issues — from the browser's perspective everything is
      // same-origin (localhost:5173). Vite handles the cross-port forwarding.
      '/commitments': 'http://localhost:8000',
      '/briefings': 'http://localhost:8000',
      '/calendar': 'http://localhost:8000',
      '/push': 'http://localhost:8000',
      '/chat': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/test/**', 'src/main.jsx'],
    },
  },
})
