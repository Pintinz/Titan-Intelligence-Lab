import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'pwa-icon.svg'],
      manifest: {
        name: 'TitanIQ — Sports Intelligence Beyond Prediction',
        short_name: 'TitanIQ',
        description:
          'Calibrated, explainable, model-driven sports intelligence across Football, Basketball, Baseball, and Table Tennis.',
        theme_color: '#0a0e14',
        background_color: '#0a0e14',
        display: 'standalone',
        start_url: '/app',
        scope: '/',
        icons: [
          { src: '/pwa-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: '/pwa-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' },
        ],
        shortcuts: [
          { name: 'Prediction Center', url: '/app/predictions' },
          { name: 'Match Center', url: '/app/matches' },
          { name: 'Notifications', url: '/app/notifications' },
        ],
      },
      workbox: {
        // Precache the app shell only — API responses (predictions, markets, sports data) are
        // never cached offline: they're per-user, RBAC-gated, and change continuously, so a
        // stale cached response could show a free-tier user administrator-only data from a
        // previous session on the same device, or simply lie about live prediction state.
        navigateFallback: '/index.html',
        globPatterns: ['**/*.{js,css,html,svg}'],
        runtimeCaching: [],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
  },
})
