// Caches the shell so the app opens without the backend reachable. State is
// never cached: a stale position shown as current is exactly what this project
// refuses to do — without a connection the UI says so instead.
const SHELL = 'shell-v1';

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
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/')) return; // never cache state
  event.respondWith(
    caches.match(event.request).then((hit) => hit ?? fetch(event.request).then((response) => {
      const copy = response.clone();
      caches.open(SHELL).then((cache) => cache.put(event.request, copy));
      return response;
    }).catch(() => caches.match('/index.html')))
  );
});
