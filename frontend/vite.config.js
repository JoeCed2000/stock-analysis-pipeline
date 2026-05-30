import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'child_process'

const commit = (() => { try { return execSync('git rev-parse --short HEAD').toString().trim(); } catch { return 'unknown'; } })();
const buildDate = new Date().toISOString().slice(0, 10);

export default defineConfig({
  plugins: [react()],
  base: '/stock-analysis/',
  define: {
    __BUILD_COMMIT__: JSON.stringify(commit),
    __BUILD_DATE__: JSON.stringify(buildDate),
  },
  server: {
    port: 5180,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8780',
        changeOrigin: true,
        ws: true,
      }
    }
  }
})
