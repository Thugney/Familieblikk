const CACHE = 'familieblikk-public-__PUBLIC_VERSION__';
const PUBLIC = ['/offline/', '/static/budget/app.css', '/static/budget/app.js', '/static/budget/icon.svg'];
self.addEventListener('install', event => event.waitUntil((async () => {
  const cache = await caches.open(CACHE);
  for (const path of PUBLIC) {
    const request = new Request(new URL(path, self.location.origin), {cache: 'no-store', credentials: 'omit'});
    const response = await fetch(request);
    if (!response.ok) throw new Error('Offentlig ressurs kunne ikke hentes');
    await cache.put(request, response);
  }
  await self.skipWaiting();
})()));
self.addEventListener('activate', event => event.waitUntil((async () => {
  for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key);
  await self.clients.claim();
})()));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (PUBLIC.includes(url.pathname) && !url.search) {
    event.respondWith(caches.match(event.request).then(hit => hit || fetch(event.request, {cache: 'no-store'})));
  } else if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request, {cache: 'no-store'}).catch(() => caches.match(new URL('/offline/', self.location.origin).href)));
  }
});
