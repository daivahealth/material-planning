import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// APP_BASE (e.g. "/material-planning/") sets the public base path for a
// reverse-proxy / context deployment. Defaults to "/" for local dev.
export default defineConfig({
  base: process.env.APP_BASE || '/',
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
})
