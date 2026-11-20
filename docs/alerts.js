(function () {
  var C = window.FP_PUSH || {}; if (!C.url) return;
  function b64(s) { var p = '='.repeat((4 - s.length % 4) % 4), r = atob((s + p).replace(/-/g, '+').replace(/_/g, '/')); var o = new Uint8Array(r.length); for (var i = 0; i < r.length; i++) o[i] = r.charCodeAt(i); return o; }
  function prefs() {
    var clubs = [], leagues = [];
    try { clubs = JSON.parse(localStorage.getItem('fp-clubs') || 'null') || []; if (!clubs.length) { var o = localStorage.getItem('fp-club'); if (o) clubs = [o]; } } catch (e) {}
    try { leagues = (JSON.parse(localStorage.getItem('fp-follow') || '{}').leagues) || []; } catch (e) {}
    return { clubs: clubs, leagues: leagues };
  }
  function supported() { return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window; }
  function post(mode, body) {
    return fetch(C.url + (C.url.indexOf('?') > -1 ? '&' : '?') + 'push=' + mode, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(body) }).then(function (r) { return r.json(); });
  }
  function reg() { return navigator.serviceWorker.register('/sw.js?r=' + encodeURIComponent(C.url)).then(function () { return navigator.serviceWorker.ready; }); }
  var A = {
    supported: supported,
    on: function () { try { return localStorage.getItem('fp-alerts') === '1'; } catch (e) { return false; } },
    sync: function () {
      if (!A.on() || !supported()) return Promise.resolve();
      return reg().then(function (r) { return r.pushManager.getSubscription(); }).then(function (s) {
        if (!s) return; var p = prefs(); return post('sub', { endpoint: s.endpoint, clubs: p.clubs, leagues: p.leagues });
      }).catch(function () {});
    },
    enable: function () {
      if (!supported()) return Promise.reject(new Error('unsupported'));
      return Notification.requestPermission().then(function (perm) {
        if (perm !== 'granted') throw new Error('denied');
        return reg();
      }).then(function (r) {
        return r.pushManager.getSubscription().then(function (s) { return s || r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(C.key) }); });
      }).then(function (s) {
        var p = prefs(); return post('sub', { endpoint: s.endpoint, clubs: p.clubs, leagues: p.leagues });
      }).then(function (j) { if (!j || !j.ok) throw new Error('server'); try { localStorage.setItem('fp-alerts', '1'); } catch (e) {} });
    },
    disable: function () {
      try { localStorage.removeItem('fp-alerts'); } catch (e) {}
      if (!supported()) return Promise.resolve();
      return navigator.serviceWorker.getRegistration('/').then(function (r) { return r && r.pushManager.getSubscription(); }).then(function (s) {
        if (!s) return; var ep = s.endpoint; return s.unsubscribe().then(function () { return post('unsub', { endpoint: ep }); });
      }).catch(function () {});
    }
  };
  window.FPAlerts = A;
  A.sync();
})();
