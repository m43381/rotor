import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'

// В режиме разработки API идёт через шлюз стенда (`just up`), а Keycloak вызывается напрямую:
// issuer в токенах всегда равен публичному адресу шлюза.
const gateway = process.env.DUTYFLOW_GATEWAY ?? 'http://localhost:8088'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: { '/api': { target: gateway, changeOrigin: false } },
  },
  build: {
    target: 'es2020',
    sourcemap: false,
    chunkSizeWarningLimit: 1500,
  },
  test: {
    environment: 'node',
    include: ['src/**/*.spec.ts'],
  },
})
