/* FitTracker service worker — enables install + offline-friendly caching. */
const CACHE = 'fittracker-v2';
const APP_SHELL = [
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/manifest.json',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Dynamic / auth-sensitive endpoints → always network
  if (url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/coach') ||
      url.pathname.startsWith('/login') ||
      url.pathname.startsWith('/logout')) {
    return;
  }

  // HTML navigation → network-first, fall back to cache then home
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req).then((r) => r || caches.match('/')))
    );
    return;
  }

  // Same-origin static assets → stale-while-revalidate
  if (url.origin === location.origin && url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(req).then((cached) => {
        const network = fetch(req)
          .then((res) => {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
            return res;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});
