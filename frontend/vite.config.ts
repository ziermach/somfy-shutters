import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// The backend serves the built files in production; in development we proxy to it
// so the frontend never needs to know an origin. Nothing is fetched from the
// internet at runtime — see the constitution, principle IV.
export default defineConfig({
  plugins: [svelte()],
  publicDir: 'static',
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true }
    }
  },
  build: { outDir: 'dist', emptyOutDir: true }
});
