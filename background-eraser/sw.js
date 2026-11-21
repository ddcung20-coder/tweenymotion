// Background Eraser — 오프라인 캐시 + cross-origin isolation(멀티스레드 WASM용)
const VERSION = 'bgeraser-shell-v2';
const SHELL = [
  './',
  './index.html',
  './engine.worker.js',
  './manifest.webmanifest',
  './icon.svg',
  './icon-192.png',
  './icon-512.png',
  './icon-180.png',
  './ort/ort.webgpu.bundle.min.mjs',
  './ort/ort-wasm-simd-threaded.asyncify.mjs',
  './ort/ort-wasm-simd-threaded.asyncify.wasm',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith('bgeraser-shell') && k !== VERSION) await caches.delete(k);
    await self.clients.claim();
  })());
});

function isolate(res) {
  if (!res || res.status === 0 || res.type === 'opaque') return res;
  const h = new Headers(res.headers);
  h.set('Cross-Origin-Embedder-Policy', 'require-corp');
  h.set('Cross-Origin-Opener-Policy', 'same-origin');
  h.set('Cross-Origin-Resource-Policy', 'same-origin');
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return; // 모델(huggingface) 등은 앱이 직접 캐시
  if (req.cache === 'only-if-cached' && req.mode !== 'same-origin') return;
  const scope = new URL(self.registration.scope);
  const inScope = url.pathname.startsWith(scope.pathname);
  if (url.pathname.includes('/models/')) { e.respondWith(fetch(req).then(isolate)); return; } // 모델은 앱이 직접 캐시
  const immutable = url.pathname.includes('/ort/');
  e.respondWith((async () => {
    const cache = await caches.open(VERSION);
    const key = req.mode === 'navigate' && inScope ? new URL('./index.html', scope).href : req;
    const cached = await cache.match(key, { ignoreSearch: req.mode === 'navigate' });
    if (cached && immutable) return isolate(cached);
    // 앱 파일: 캐시를 먼저 보여 주고 뒤에서 갱신 (stale-while-revalidate)
    const net = fetch(req).then((res) => {
      if (res.ok && inScope && res.type === 'basic') cache.put(key, res.clone()).catch(() => {});
      return res;
    });
    if (cached) { e.waitUntil(net.catch(() => {})); return isolate(cached); }
    try { return isolate(await net); }
    catch (err) { const fb = await cache.match(key); if (fb) return isolate(fb); throw err; }
  })());
});
