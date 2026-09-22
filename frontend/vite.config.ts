import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import type { Plugin } from 'vite';

// /@vite/client carries a token that changes on every dev-server start. Served
// from the browser cache after a restart, the HMR socket is refused with the old
// token, edits stop arriving, and a tab can end up holding two copies of a
// module (one with ?t=) — which is how the overview once animated from a clock
// nobody ticked. Never cache that one file.
function freshViteClient(): Plugin {
  return {
    name: 'fresh-vite-client',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.startsWith('/@vite/client')) {
          delete req.headers['if-none-match'];
          const setHeader = res.setHeader.bind(res);
          res.setHeader = (name, value) =>
            name.toLowerCase() === 'cache-control' ? setHeader(name, 'no-store') : setHeader(name, value);
          res.setHeader('Cache-Control', 'no-store');
        }
        next();
      });
    }
  };
}

// The backend serves the built files in production; in development we proxy to it
// so the frontend never needs to know an origin. Nothing is fetched from the
// internet at runtime — see the constitution, principle IV.
export default defineConfig({
  plugins: [freshViteClient(), svelte()],
  publicDir: 'static',
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true }
    }
  },
  build: { outDir: 'dist', emptyOutDir: true }
});
