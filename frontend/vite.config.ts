import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// The backend serves the built files in production; in development we proxy to it
// so the frontend never needs to know an origin. Nothing is fetched from the
// internet at runtime — see the constitution, principle IV. The Host header is left
// alone (changeOrigin: false): the backend compares it with Origin before trusting a
// cookie (feature 008), and a rewritten host would make every dev request foreign.
export default defineConfig({
  plugins: [svelte()],
  publicDir: 'static',
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: false, ws: true }
    }
  },
  build: { outDir: 'dist', emptyOutDir: true }
});
