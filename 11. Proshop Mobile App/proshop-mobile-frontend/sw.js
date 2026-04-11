const CACHE_NAME = 'proshop-mobile-v8';
const STATIC_ASSETS = [
  '/app/',
  '/app/index.html',
  '/app/css/app.css',
  '/app/js/app.js',
  '/app/js/api.js',
  '/app/js/jsQR.js',
  '/app/js/scanner.js',
  '/app/js/counter.js',
  '/app/js/chat.js',
  '/app/manifest.json',
];

// Install — cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network-first for EVERYTHING
// Online: always gets fresh files, updates cache
// Offline: falls back to cached version
self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
