// Lets the app open when the backend is unreachable. State is never cached: a stale
// position shown as current is exactly what this project refuses to do — without a
// connection the UI says so instead.
//
// Network first, cache only as the fallback. The first version was cache-first and
// never asked again, so every phone kept the version it first loaded, forever — an
// update on the Pi would never have reached anyone. Found when the dev server kept
// serving day-old modules.
const SHELL = 'shell-v2';

// Development-only paths: never worth keeping, and stale copies break the dev server.
const NEVER_CACHE = ['/api/', '/@vite/', '/@fs/', '/src/', '/node_modules/'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(['/', '/index.html'])));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (NEVER_CACHE.some((prefix) => url.pathname.startsWith(prefix))) return;
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(SHELL).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then((hit) => hit ?? caches.match('/index.html')))
  );
});
