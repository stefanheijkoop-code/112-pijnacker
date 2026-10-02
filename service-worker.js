/* Increment SHELL_VERSION whenever app files change. Data survives shell updates. */
const SHELL_VERSION = '112-pijnacker-shell-v1';
const DATA_CACHE = '112-pijnacker-data-v1';
const base = self.registration.scope;
const url = path => new URL(path, base).href;
const DATA_URL = url('data.json');
const FILES = ['index.html', 'manifest.json', 'vendor/leaflet/leaflet.js', 'vendor/leaflet/leaflet.css',
  'vendor/leaflet/images/marker-icon.png', 'vendor/leaflet/images/marker-icon-2x.png',
  'vendor/leaflet/images/marker-shadow.png', 'vendor/leaflet/images/layers.png',
  'vendor/leaflet/images/layers-2x.png'].map(url);
self.addEventListener('install', event => event.waitUntil((async () => {
  const cache = await caches.open(SHELL_VERSION);
  try { await cache.addAll(FILES.map(path => new Request(path, {cache: 'reload'}))); }
  catch (error) { await caches.delete(SHELL_VERSION); throw error; }
})()));
self.addEventListener('activate', event => event.waitUntil((async () => {
  for (const name of await caches.keys()) {
    if (name.startsWith('112-pijnacker-shell-') && name !== SHELL_VERSION) await caches.delete(name);
  }
  await self.clients.claim();
})()));
function valid(data) {
  return data && Array.isArray(data.incidents) && Number.isFinite(Date.parse(data.updated)) &&
    data.incidents.every(item => item && typeof item === 'object' && typeof item.title === 'string' && typeof item.service === 'string');
}
function tagged(response, source) {
  const headers = new Headers(response.headers);
  headers.set('X-112-Data-Source', source);
  return new Response(response.body, {status: response.status, statusText: response.statusText, headers});
}
async function loadData() {
  let cache, saved;
  try { cache = await caches.open(DATA_CACHE); saved = await cache.match(DATA_URL); } catch (_) {}
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(DATA_URL, {cache: 'no-store', signal: controller.signal});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const data = await response.clone().json();
    if (!valid(data)) throw new Error('Invalid data');
    if (saved) {
      const previous = await saved.clone().json();
      if (Date.parse(previous.updated) > Date.parse(data.updated)) return tagged(saved, 'cache');
    }
    let stored = false;
    try { if (cache) { await cache.put(DATA_URL, response.clone()); stored = true; } } catch (_) {}
    const result = tagged(response, 'network');
    result.headers.set('X-112-Data-Stored', stored ? 'yes' : 'no');
    return result;
  } catch (_) {
    if (saved) return tagged(saved, 'cache');
    return new Response(JSON.stringify({error: 'Geen opgeslagen meldingen beschikbaar'}),
      {status: 503, headers: {'Content-Type': 'application/json'}});
  } finally { clearTimeout(timer); }
}
self.addEventListener('fetch', event => {
  const request = event.request, target = new URL(request.url);
  if (request.method !== 'GET' || target.origin !== new URL(base).origin) return;
  if (target.pathname === new URL(DATA_URL).pathname) {
    event.respondWith(loadData()); return;
  }
  if (request.mode === 'navigate' && target.href.startsWith(base)) {
    event.respondWith((async () => (await caches.open(SHELL_VERSION)).match(url('index.html')).then(saved => saved || fetch(request)))());
    return;
  }
  if (FILES.includes(target.href)) {
    event.respondWith((async () => (await caches.open(SHELL_VERSION)).match(request).then(saved => saved || fetch(request)))());
  }
});
