const CACHE_NAME = 'chat-cache-v1';
const urlsToCache = [
  '/chat',
  '/static/css/chat.css',
  '/static/js/socket.io.min.js',
  '/static/js/chat.js',
  '/static/assets/fonts/Vazirmatn/Vazirmatn-font-face.css',
  '/static/assets/favicon.svg',
  '/static/assets/icon-192.png',
  '/static/assets/icon-512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(response => response || fetch(event.request))
  );
});
