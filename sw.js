// Minimal service worker: network first, cached copy when offline. Makes the app installable.
const CACHE = 'ppp-v1';
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'assets/lightweight-charts.standalone.production.js',
  'assets/icon-192.png', 'assets/icon-512.png', 'assets/qr.png', 'assets/qr-wise.png', 'assets/qrcode.js'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith(
    fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req).then(hit => hit || Response.error()))
  );
});
