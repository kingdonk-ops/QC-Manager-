/// <reference types="vitest/config" />
import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import { playwright } from '@vitest/browser-playwright'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    tanstackRouter({
      target: 'react',
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
  server: {
    // The API is served from the same origin as the app, so the session cookie and the
    // Entra redirect both stay first-party. In production a reverse proxy does the same.
    proxy: {
      '/api': { target: process.env.API_URL ?? 'http://localhost:8000', changeOrigin: false },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    silent: 'passed-only',
    unstubEnvs: true,
    browser: {
      enabled: true,
      // PLAYWRIGHT_CHROMIUM points at a Chromium already on the machine, instead of Playwright's own download.
      provider: playwright(
        process.env.PLAYWRIGHT_CHROMIUM
          ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM } }
          : {}
      ),
      instances: [{ browser: 'chromium' }],
    },
    coverage: {
      // include: ['src/**/*.{js,jsx,ts,tsx}'], // Uncomment to expand the report to all src/**/* so untested modules appear as 0% coverage.
      exclude: [
        'src/components/ui/**',
        'src/assets/**',
        'src/tanstack-table.d.ts',
        'src/routeTree.gen.ts',
        'src/test-utils/**',
        'src/routes/**',
      ],
    },
  },
})
