const CACHE_NAME = "psy-2-pwa-v2.1.4";

const APP_SHELL_URLS = [
  "/",
  "/static/css/main.css",
  "/static/js/main.js",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

const CACHEABLE_PATHS = new Set(APP_SHELL_URLS);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) =>
        cache.addAll(
          APP_SHELL_URLS.map(
            (url) => new Request(url, { credentials: "same-origin" })
          )
        )
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== CACHE_NAME)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

function shouldBypass(request, url) {
  if (request.method !== "GET") return true;
  if (url.pathname.startsWith("/api/")) return true;
  if (url.searchParams.has("token")) return true;
  if (request.headers.has("Authorization")) return true;
  if (request.headers.has("X-Personal-OS-Token")) return true;
  return false;
}

function canUpdateCache(request, response, url) {
  if (!response || !response.ok || response.type !== "basic") return false;
  if (CACHEABLE_PATHS.has(url.pathname)) return true;
  return (
    request.destination === "style" ||
    request.destination === "script" ||
    request.destination === "image"
  );
}

async function networkFirst(request) {
  const url = new URL(request.url);
  const cache = await caches.open(CACHE_NAME);

  try {
    const response = await fetch(request);
    if (canUpdateCache(request, response, url)) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (request.mode === "navigate") return cache.match("/");
    throw error;
  }
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || shouldBypass(event.request, url)) {
    return;
  }

  event.respondWith(networkFirst(event.request));
});
