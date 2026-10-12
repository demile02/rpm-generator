import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Build: output ke frontend/dist (disalin ke ui-react/,
// diserve Flask sebagai aplikasi utama di /app). Base relatif agar jalan di sub-path.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      // Dev: teruskan API ke Flask lokal agar tanpa CORS.
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      // Preview build prod: API tetap ke Flask lokal.
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
});
