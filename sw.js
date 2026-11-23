/* 임직원 페이지 오프라인/빠른 로딩용 서비스워커 (관리자 페이지와 데이터 JSON은 항상 최신을 우선) */
const VERSION = 'pr-news-v1';
const SHELL = ['./index.html', './assets/common.css', './assets/common.js', './icons/symbol.png', './icons/icon-192.png', './manifest.json'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.endsWith('/admin.html')) return;

  const isData = url.pathname.endsWith('.json') && !url.pathname.endsWith('manifest.json');
  if (isData || req.mode === 'navigate') {
    // 네트워크 우선, 실패 시 캐시
    e.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      }).catch(() => caches.match(req).then((r) => r || caches.match('./index.html')))
    );
    return;
  }
  // 정적 자원: 캐시 우선 + 백그라운드 갱신
  e.respondWith(
    caches.match(req).then((cached) => {
      const net = fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      }).catch(() => cached);
      return cached || net;
    })
  );
});
