// Service worker: 離線時給上一次的 items.json，線上永遠拿新的。
// 策略：items.json = network-first（逾時才 fallback）；其餘靜態 = stale-while-revalidate。
const CACHE = "rin-news-v1";
const SHELL = ["./", "./index.html", "./manifest.json", "./icon.svg"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;

  // 資料檔：先網路（3.5 秒逾時），失敗才用快取
  if (url.pathname.endsWith("/items.json")) {
    e.respondWith((async () => {
      try {
        const fresh = await Promise.race([
          fetch(e.request, { cache: "no-store" }),
          new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 3500)),
        ]);
        const c = await caches.open(CACHE);
        c.put(e.request, fresh.clone());
        return fresh;
      } catch {
        const cached = await caches.match(e.request);
        return cached || new Response('{"items":[],"cats":[]}', { headers: { "Content-Type": "application/json" } });
      }
    })());
    return;
  }

  // 其他靜態資源：先給快取，背景更新
  e.respondWith((async () => {
    const c = await caches.open(CACHE);
    const cached = await c.match(e.request);
    const net = fetch(e.request).then(r => { c.put(e.request, r.clone()); return r; }).catch(() => null);
    return cached || (await net) || new Response("", { status: 504 });
  })());
});
