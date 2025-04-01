import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',     // 🔓 Bind to all network interfaces
    port: 5173,          // 🌐 Port (default is 5173)
    strictPort: true     // ❗ If port is taken, don’t auto-pick another
  }
})

