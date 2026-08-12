import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  // ponytail: Vite preview is enough for this single-PC deployment; use nginx/Caddy if traffic grows.
  preview: {
    host: '127.0.0.1',
    port: 8081,
    allowedHosts: ['jackdomain.dpdns.org'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
})
