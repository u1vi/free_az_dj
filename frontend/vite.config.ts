/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
  },
  // Playwright owns e2e/; Vitest would otherwise try to run it and fail.
  test: { include: ['src/**/*.test.{ts,tsx}'] },
});
