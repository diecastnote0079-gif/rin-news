// 2026-11-09 停用 service worker（自我移除）。
// 原因：舊版 SW 把舊 index.html 留在手機上，改版後仍看到舊頁
//（實例：搜尋結果每一列都顯示同一個標題）。本站資料每次上網抓，
// 離線快取的價值遠低於「看到舊頁」的代價。
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    } catch (err) {}
    try { await self.registration.unregister(); } catch (err) {}
    const cs = await self.clients.matchAll({ type: "window" });
    for (const c of cs) { try { c.navigate(c.url); } catch (err) {} }
  })());
});

// 不再攔截任何請求
self.addEventListener("fetch", () => {});
