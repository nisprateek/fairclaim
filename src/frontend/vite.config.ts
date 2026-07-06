import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Honour an assigned port (e.g. from a preview harness); default 5173.
  server: { port: Number(process.env.PORT) || 5173 },
})
