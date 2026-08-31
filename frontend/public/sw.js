const CACHE_NAME = "mediqa-pwa-v3";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(keys.map((key) => caches.delete(key)));
    }).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  // Always fetch from network first so code updates are immediate
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
