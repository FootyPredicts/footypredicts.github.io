// FootyPredicts alerts: wakes up on a push, asks the relay what is new for this browser, shows it.
const RELAY = new URL(self.location.href).searchParams.get('r') || '';
async function sha(s) {
  const h = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return Array.from(new Uint8Array(h)).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('').slice(0, 32);
}
async function getSince() { try { const c = await caches.open('fp-push'); const r = await c.match('since'); return r ? Number(await r.text()) || 0 : 0; } catch (e) { return 0; } }
async function setSince(t) { try { const c = await caches.open('fp-push'); await c.put('since', new Response(String(t))); } catch (e) {} }
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener('push', function (e) {
  e.waitUntil((async function () {
    let msgs = [];
    try {
      const sub = await self.registration.pushManager.getSubscription();
      if (sub && RELAY) {
        const id = await sha(sub.endpoint), since = await getSince();
        const r = await fetch(RELAY + (RELAY.indexOf('?') > -1 ? '&' : '?') + 'push=msg&id=' + id + '&since=' + since, { cache: 'no-store' });
        if (r.ok) { const j = await r.json(); msgs = j.messages || []; await setSince(j.ts || Date.now()); }
      }
    } catch (err) {}
    if (!msgs.length) msgs = [{ title: 'FootyPredicts', body: 'There is an update for the clubs you follow.', url: '/superfan/' }];
    if (msgs.length > 3) msgs = msgs.slice(0, 2).concat([{ title: 'FootyPredicts', body: (msgs.length - 2) + ' more updates for your clubs', url: '/superfan/' }]);
    for (const m of msgs) await self.registration.showNotification(m.title, { body: m.body, tag: m.id || undefined, data: { url: m.url || '/' } });
  })());
});
self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(self.clients.matchAll({ type: 'window' }).then(function (list) {
    for (const c of list) { if (c.url === url && 'focus' in c) return c.focus(); }
    return self.clients.openWindow(url);
  }));
});
