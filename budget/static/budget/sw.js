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

// The payload contains only generic activity text and an authenticated local URL.
self.addEventListener('push', event => event.waitUntil((async () => {
  let data;
  try { data = event.data ? event.data.json() : {}; } catch { data = {}; }
  if (!data || typeof data !== 'object') data = {};
  const bodies = new Set(['En ny kalenderavtale er lagt til.', 'Et familiemedlem har godtatt en avtale.', 'Et familiemedlem har avslått en avtale.', 'Testvarsel fra Familieblikk.']);
  const url = safePushUrl(data.url);
  await self.registration.showNotification('Familieblikk', {body:bodies.has(data.body) ? data.body : 'Ny aktivitet i familiekalenderen.', icon:'/static/budget/icon.svg', badge:'/static/budget/icon.svg', tag:typeof data.tag === 'string' ? data.tag.slice(0, 80) : 'familieblikk-calendar', data:{url}});
})()));

function safePushUrl(value) {
  try {
    const url = new URL(value, self.location.origin);
    if (url.origin === self.location.origin && (/^\/push\/open\/[0-9a-f-]{36}\/$/.test(url.pathname) || url.pathname === '/app/varsler/') && !url.search && !url.hash) return url.href;
  } catch { /* Fall back to authenticated notification overview. */ }
  return new URL('/app/varsler/', self.location.origin).href;
}

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil((async () => {
    const url = safePushUrl(event.notification.data && event.notification.data.url);
    // Preserve any existing page and its unsaved form, even if it disappears.
    await self.clients.openWindow(url);
  })());
});
