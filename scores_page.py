# -*- coding: utf-8 -*-
"""Livescores board for the home page: every match in the world for a chosen day, live scores, goals and cards."""
import json

CSS = """
<style>
.ls { margin:0 0 28px; }
.ls-head { display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; margin:0 0 8px; }
.ls-head h2 { margin:0; font:800 30px/1 "Barlow Condensed",sans-serif; }
.ls-head a { font-size:14px; }
.ls-days { display:flex; gap:6px; margin:6px 0 10px; overflow-x:auto; }
.ls-day, .ls-f { border:1px solid var(--line); background:#fff; color:var(--ink); border-radius:999px; padding:6px 14px; font:600 14px Barlow,sans-serif; cursor:pointer; white-space:nowrap; }
.ls-day[aria-pressed="true"], .ls-f[aria-pressed="true"] { background:var(--ink); color:#fff; border-color:var(--ink); }
.ls-f b { font-weight:700; opacity:.7; margin-left:4px; }
.ls-tools { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin:0 0 12px; }
.ls-q { flex:1; min-width:180px; border:1px solid var(--line); border-radius:999px; padding:7px 14px; font:16px Barlow,sans-serif; background:#fff; }
.ls-grid { display:grid; grid-template-columns:200px minmax(0,1fr); gap:16px; align-items:start; }
.ls-side { position:sticky; top:12px; max-height:calc(100vh - 24px); overflow-y:auto; background:#fff; border:1px solid var(--line); border-radius:14px; padding:6px; }
.ls-side h4 { margin:8px 8px 4px; font:700 11px Barlow,sans-serif; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
.ls-c { display:flex; align-items:center; gap:6px; width:100%; border:0; background:none; text-align:left; padding:7px 8px; border-radius:8px; font:600 14px Barlow,sans-serif; color:var(--ink); cursor:pointer; }
.ls-c:hover { background:#f1f4f0; }
.ls-c[aria-pressed="true"] { background:var(--ink); color:#fff; }
.ls-c .n { margin-left:auto; font-weight:500; opacity:.7; font-size:13px; }
.ls-c .lsl { color:#c0392b; font-weight:700; margin-left:auto; font-size:13px; }
.ls-c[aria-pressed="true"] .lsl { color:#ffb4a8; }
.ls-sel { display:none; width:100%; border:1px solid var(--line); border-radius:999px; padding:8px 14px; font:16px Barlow,sans-serif; background:#fff; margin:0 0 10px; }
@media (max-width:820px) { .ls-grid { grid-template-columns:minmax(0,1fr); } .ls-side { display:none; } .ls-sel { display:block; } }
.ls-lg { background:#fff; border:1px solid var(--line); border-radius:14px; margin:0 0 10px; overflow:hidden; }
.ls-lgh { display:flex; align-items:center; gap:8px; padding:9px 12px; background:#f1f4f0; cursor:pointer; font:700 14px Barlow,sans-serif; }
.ls-lgh .cn { color:var(--muted); font-weight:500; }
.ls-lgh .n { margin-left:auto; color:var(--muted); font-weight:500; }
.ls-star { border:0; background:none; font-size:18px; line-height:1; cursor:pointer; color:#b8a24a; padding:0 2px; }
.ls-m { display:grid; grid-template-columns:58px 1fr auto 1fr; align-items:center; gap:8px; padding:9px 12px; border-top:1px solid var(--line); cursor:pointer; }
.ls-t { font:700 13px Barlow,sans-serif; color:var(--muted); white-space:nowrap; }
.ls-t.live { color:#c0392b; } .ls-t.live:before { content:""; display:inline-block; width:7px; height:7px; border-radius:50%; background:#c0392b; margin-right:4px; vertical-align:middle; animation:lspulse 1.4s infinite; }
@keyframes lspulse { 50% { opacity:.25; } }
.ls-h, .ls-a { font:600 16px/1.15 Barlow,sans-serif; }
.ls-h { text-align:right; } .ls-a { text-align:left; }
.ls-s { font:800 20px/1 "Barlow Condensed",sans-serif; min-width:54px; text-align:center; white-space:nowrap; }
.ls-s.live { color:#c0392b; }
.ls-x { grid-column:2 / 5; font-size:13px; color:var(--muted); }
.ls-x div { padding:1px 0; }
.ls-p { grid-column:2 / 5; font-size:12px; color:var(--muted); }
.ls-p b { color:var(--ink); }
.ls-tbr { grid-column:2 / 5; }
.ls-tbr .lt-btn { margin:0; padding:2px 9px; font-size:11px; }
.ls-empty { background:#fff; border:1px dashed var(--line); border-radius:14px; padding:18px; color:var(--muted); }
.ls-note { font-size:12px; color:var(--muted); margin:8px 0 0; }
@media (max-width:520px) { .ls-m { grid-template-columns:56px 1fr auto 1fr; gap:6px; padding:9px 8px; } .ls-h, .ls-a { font-size:15px; } }
</style>
"""

JS = r"""
<script>
(function () {
  var CFG = __CFG__;
  var root = document.getElementById('ls');
  if (!root || !CFG.url) return;
  var PRIORITY = [39, 2, 3, 140, 78, 135, 61, 848, 45, 48, 40, 41, 42, 179, 88, 94, 144, 203, 1, 4, 5, 9, 15, 960];
  var LIVE = { '1H': 1, '2H': 1, 'ET': 1, 'BT': 1, 'P': 1, 'LIVE': 1, 'HT': 1, 'INT': 1 };
  var DONE = { 'FT': 1, 'AET': 1, 'PEN': 1 };
  var OFF = { 'PST': 'Postponed', 'CANC': 'Cancelled', 'ABD': 'Abandoned', 'AWD': 'Awarded', 'WO': 'Walkover', 'SUSP': 'Suspended' };
  var KEY = 'fp-ls-v1';
  var store = { fav: [], shut: {} };
  try { var s = JSON.parse(localStorage.getItem(KEY) || '{}'); if (s.fav) store.fav = s.fav; if (s.shut) store.shut = s.shut; } catch (e) {}
  function save() { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) {} }
  var st = { date: null, filter: 'all', q: '', data: null, open: {}, err: '', country: null };
  var tz = 'Europe/London';
  function ukDate(d) { return d.toLocaleDateString('sv-SE', { timeZone: tz }); }
  var today = ukDate(new Date());
  function shift(n) { var d = new Date(); d.setUTCDate(d.getUTCDate() + n); return ukDate(d); }
  st.date = today;
  function h(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function isLive(m) { return !!LIVE[m.st]; }
  function koTime(m) { try { return new Date(m.ko).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: tz }); } catch (e) { return ''; } }
  function label(m) {
    if (isLive(m)) { if (m.st === 'HT') return 'HT'; if (m.st === 'BT') return 'Break'; if (m.st === 'P') return 'Pens'; return (m.el || 0) + (m.ex ? '+' + m.ex : '') + "'"; }
    if (DONE[m.st]) return m.st === 'FT' ? 'FT' : m.st;
    if (OFF[m.st]) return OFF[m.st].slice(0, 5);
    return koTime(m);
  }
  function score(m) { return (m.hg == null || m.ag == null) ? '' : m.hg + ' - ' + m.ag; }
  function isFav(id) { return store.fav.indexOf(id) > -1; }
  function matchText(m) { return (m.home + ' ' + m.away + ' ' + m.ln + ' ' + m.cn).toLowerCase(); }

  function filtered() {
    var q = st.q.trim().toLowerCase();
    return (st.data || []).filter(function (m) {
      if (q && matchText(m).indexOf(q) < 0) return false;
      if (st.country === '__top') { if (PRIORITY.indexOf(m.lg) < 0) return false; }
      else if (st.country && m.cn !== st.country) return false;
      if (st.filter === 'live') return isLive(m);
      if (st.filter === 'fin') return !!DONE[m.st];
      if (st.filter === 'soon') return !isLive(m) && !DONE[m.st] && !OFF[m.st];
      if (st.filter === 'fav') return isFav(m.lg);
      return true;
    });
  }
  function groups(list) {
    var by = {};
    list.forEach(function (m) { (by[m.lg] = by[m.lg] || { lg: m.lg, ln: m.ln, cn: m.cn, ms: [] }).ms.push(m); });
    var out = Object.keys(by).map(function (k) { return by[k]; });
    function rank(g) { var i = PRIORITY.indexOf(g.lg); return isFav(g.lg) ? -1 : (i < 0 ? 999 : i); }
    out.sort(function (a, b) { return rank(a) - rank(b) || (a.cn || '').localeCompare(b.cn || '') || a.ln.localeCompare(b.ln); });
    out.forEach(function (g) { g.ms.sort(function (a, b) { return (isLive(b) - isLive(a)) || a.ko.localeCompare(b.ko); }); });
    return out;
  }

  var TB = CFG.tables || {};
  var tbl = null;
  function tbEsc(t) { return String(t).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function tbDraw() {
    if (!tbl) return;
    if (!document.body.contains(tbl.o)) { tbl = null; return; }
    var D = TB[tbl.lg]; if (!D) return;
    var T = {}; D.rows.forEach(function (r) { T[r.n] = { n: r.n, p: r.p, w: r.w, d: r.d, l: r.l, gf: r.gf, ga: r.ga, lv: false }; });
    var n = 0;
    (st.date === today ? (st.data || []) : []).forEach(function (m) {
      if (m.lg !== tbl.lg || D.done.indexOf(m.id) > -1 || !T[m.home] || !T[m.away]) return;
      var live = isLive(m), fin = !!DONE[m.st];
      if (!live && !fin) return;
      if (m.hg == null || m.ag == null) return;
      if (live) n++;
      [[m.home, m.hg, m.ag], [m.away, m.ag, m.hg]].forEach(function (z) {
        var r = T[z[0]]; if (live) r.lv = true; r.p++; r.gf += z[1]; r.ga += z[2];
        if (z[1] > z[2]) r.w++; else if (z[1] === z[2]) r.d++; else r.l++;
      });
    });
    var L = Object.keys(T).map(function (k) { var r = T[k]; r.pts = r.w * 3 + r.d; r.gd = r.gf - r.ga; return r; });
    L.sort(function (a, b) { return b.pts - a.pts || b.gd - a.gd || b.gf - a.gf || a.n.localeCompare(b.n); });
    var html = '<div class="fm-title"><b>' + tbEsc(tbl.name) + ' table</b></div><p class="halves lt-note">' +
      (n ? '<span class="lt-live">● Live</span> ' + n + ' match' + (n > 1 ? 'es' : '') + ' in play. The table updates by itself.' : 'Based on finished matches. It updates by itself when games are being played.') + '</p>' +
      '<table class="lt"><thead><tr><th>#</th><th class="tl">Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GD</th><th>Pts</th></tr></thead><tbody>';
    L.forEach(function (r, i) {
      html += '<tr class="' + (r.n === tbl.h || r.n === tbl.a ? 'lt-me' : '') + '"><td>' + (i + 1) + '</td><td class="tl">' + tbEsc(r.n) + (r.lv ? ' <span class="lt-dot">●</span>' : '') +
        '</td><td>' + r.p + '</td><td>' + r.w + '</td><td>' + r.d + '</td><td>' + r.l + '</td><td>' + (r.gd > 0 ? '+' : '') + r.gd + '</td><td><b>' + r.pts + '</b></td></tr>';
    });
    var keep = tbl.body.parentNode.scrollTop;
    tbl.body.innerHTML = html + '</tbody></table><p class="halves">Ties on points are split by goal difference, then goals scored.</p>';
    tbl.body.parentNode.scrollTop = keep;
    if (!tbl.sc) { tbl.sc = 1; var me = tbl.body.querySelector('.lt-me'); if (me && me.scrollIntoView) me.scrollIntoView({ block: 'center' }); }
  }
  function openTb(lg, name, hn, an) {
    var old = document.querySelector('.fm-ov'); if (old) old.remove();
    var o = h('div', 'fm-ov'); o.setAttribute('role', 'dialog'); o.setAttribute('aria-modal', 'true');
    var box = h('div', 'fm-box fm-wide'); var x = h('button', 'fm-x', '×'); x.type = 'button'; x.setAttribute('aria-label', 'Close');
    var body = h('div'); box.appendChild(x); box.appendChild(body); o.appendChild(box); document.body.appendChild(o); x.focus();
    tbl = { o: o, body: body, lg: lg, name: name, h: hn, a: an, sc: 0 }; tbDraw(); load();
  }
  function tbBtn(lg, name, hn, an, cls) {
    var b = h('button', cls, '☰ League table'); b.type = 'button';
    b.onclick = function (e) { e.stopPropagation(); openTb(lg, name, hn, an); }; return b;
  }
  function row(m) {
    var wrap = document.createDocumentFragment();
    var r = h('div', 'ls-m');
    var t = h('span', 'ls-t' + (isLive(m) ? ' live' : ''), label(m));
    r.appendChild(t); r.appendChild(h('span', 'ls-h', m.home));
    r.appendChild(h('span', 'ls-s' + (isLive(m) ? ' live' : ''), score(m) || 'v'));
    r.appendChild(h('span', 'ls-a', m.away));
    var pk = CFG.picks[String(m.id)];
    if (pk && !DONE[m.st]) {
      var who = pk.pk === 'Home' ? pk.h : pk.pk === 'Away' ? pk.a : 'Draw';
      var pc = pk.pk === 'Home' ? pk.hp : pk.pk === 'Away' ? pk.ap : pk.dp;
      var p = h('div', 'ls-p'); p.innerHTML = 'FootyPredicts pick: <b></b>';
      p.firstElementChild.textContent = who + ' ' + pc + '%'; r.appendChild(p);
    }
    if (st.open[m.id] && m.ev && m.ev.length) {
      var x = h('div', 'ls-x');
      m.ev.slice().sort(function (a, b) { return a.m - b.m; }).forEach(function (e) {
        var side = e.s === 'h' ? m.home : m.away;
        var d = h('div', '', (e.t === 'Goal' ? '⚽ ' : e.d === 'Red Card' ? '🟥 ' : '🟨 ') + e.m + (e.x ? '+' + e.x : '') + "' " + (e.p || '') + ' (' + side + ')' + (e.d === 'Own Goal' ? ' own goal' : e.d === 'Penalty' ? ' pen' : ''));
        x.appendChild(d);
      });
      r.appendChild(x);
    }
    if (TB[m.lg]) { var tr = h('div', 'ls-tbr'); tr.appendChild(tbBtn(m.lg, m.ln, m.home, m.away, 'lt-btn')); r.appendChild(tr); }
    r.onclick = function () { if (m.ev && m.ev.length) { st.open[m.id] = !st.open[m.id]; render(); } };
    wrap.appendChild(r); return wrap;
  }
  var HOME = ['England', 'Spain', 'Germany', 'Italy', 'France', 'Scotland', 'Netherlands', 'Portugal'];
  function renderSide(data) {
    var by = {};
    data.forEach(function (m) { var c = by[m.cn] = by[m.cn] || { n: 0, live: 0 }; c.n++; if (isLive(m)) c.live++; });
    var names = Object.keys(by).filter(function (n) { return n !== 'World'; });
    names.sort(function (a, b) { var ia = HOME.indexOf(a), ib = HOME.indexOf(b); if (ia > -1 || ib > -1) return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib); return a.localeCompare(b); });
    var top = data.filter(function (m) { return PRIORITY.indexOf(m.lg) > -1; });
    var entries = [{ key: null, label: 'All matches', n: data.length, live: data.filter(isLive).length }];
    if (top.length) entries.push({ key: '__top', label: 'Top leagues', n: top.length, live: top.filter(isLive).length });
    if (by['World']) entries.push({ key: 'World', label: 'International', n: by['World'].n, live: by['World'].live });
    names.forEach(function (n) { entries.push({ key: n, label: n, n: by[n].n, live: by[n].live }); });
    var side = root.querySelector('.ls-side'); side.textContent = '';
    side.appendChild(h('h4', '', 'Countries'));
    entries.forEach(function (e) {
      var b = h('button', 'ls-c'); b.type = 'button'; b.setAttribute('aria-pressed', st.country === e.key ? 'true' : 'false');
      b.appendChild(h('span', '', e.label));
      b.appendChild(h('span', e.live ? 'lsl' : 'n', e.live ? e.live + ' live' : e.n));
      b.onclick = function () { st.country = e.key; render(); };
      side.appendChild(b);
    });
    var sel = root.querySelector('.ls-sel'); sel.textContent = '';
    entries.forEach(function (e) {
      var o = h('option', '', e.label + ' (' + e.n + (e.live ? ', ' + e.live + ' live' : '') + ')'); o.value = e.key === null ? '' : e.key;
      if (st.country === e.key) o.selected = true; sel.appendChild(o);
    });
    sel.onchange = function () { st.country = sel.value === '' ? null : sel.value; render(); };
  }
  function render() {
    var data = st.data || [];
    var nLive = data.filter(isLive).length, nFin = data.filter(function (m) { return DONE[m.st]; }).length;
    var nSoon = data.filter(function (m) { return !isLive(m) && !DONE[m.st] && !OFF[m.st]; }).length;
    var nFav = data.filter(function (m) { return isFav(m.lg); }).length;
    var days = root.querySelector('.ls-days'); days.textContent = '';
    [[-1, 'Yesterday'], [0, 'Today'], [1, 'Tomorrow'], [2, '+2'], [3, '+3']].forEach(function (d) {
      var v = shift(d[0]); var b = h('button', 'ls-day', d[0] === 2 || d[0] === 3 ? new Date(v + 'T12:00:00').toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' }) : d[1]);
      b.type = 'button'; b.setAttribute('aria-pressed', st.date === v ? 'true' : 'false');
      b.onclick = function () { st.date = v; st.data = null; st.open = {}; load(); render(); }; days.appendChild(b);
    });
    var fl = root.querySelector('.ls-fl'); fl.textContent = '';
    [['all', 'All', data.length], ['live', 'Live', nLive], ['soon', 'Upcoming', nSoon], ['fin', 'Finished', nFin], ['fav', '★ My leagues', nFav]].forEach(function (f) {
      var b = h('button', 'ls-f', f[1]); var c = h('b', '', f[2]); b.appendChild(c); b.type = 'button';
      b.setAttribute('aria-pressed', st.filter === f[0] ? 'true' : 'false'); b.onclick = function () { st.filter = f[0]; render(); }; fl.appendChild(b);
    });
    renderSide(data);
    var box = root.querySelector('.ls-list'); box.textContent = '';
    if (st.data === null) { box.appendChild(h('div', 'ls-empty', st.err || 'Loading scores…')); return; }
    var gs = groups(filtered());
    if (!gs.length) { box.appendChild(h('div', 'ls-empty', st.filter === 'live' ? 'No matches in play right now.' : st.filter === 'fav' ? 'Tap the star next to a league to keep it here.' : 'No matches found.')); }
    gs.forEach(function (g) {
      var card = h('div', 'ls-lg'); var hd = h('div', 'ls-lgh');
      var star = h('button', 'ls-star', isFav(g.lg) ? '★' : '☆'); star.type = 'button'; star.title = 'Keep this league at the top';
      star.onclick = function (e) { e.stopPropagation(); var i = store.fav.indexOf(g.lg); if (i > -1) store.fav.splice(i, 1); else store.fav.push(g.lg); save(); render(); };
      hd.appendChild(star); hd.appendChild(h('span', '', g.ln)); hd.appendChild(h('span', 'cn', g.cn)); hd.appendChild(h('span', 'n', g.ms.length));
      var shut = !!store.shut[g.lg] && !st.q;
      hd.onclick = function () { if (store.shut[g.lg]) delete store.shut[g.lg]; else store.shut[g.lg] = 1; save(); render(); };
      card.appendChild(hd);
      if (!shut) g.ms.forEach(function (m) { card.appendChild(row(m)); });
      box.appendChild(card);
    });
  }
  var busy = false;
  function load() {
    if (busy) return; busy = true;
    var d = st.date;
    fetch(CFG.url + (CFG.url.indexOf('?') > -1 ? '&' : '?') + 'scope=world&date=' + d, { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (j) { busy = false; if (d !== st.date) return load(); if (j.error) { st.err = 'Scores are catching their breath. Trying again shortly.'; if (!st.data) st.data = null; } else { st.data = j.matches || []; st.err = ''; } render(); tbDraw(); })
      .catch(function () { busy = false; if (!st.data) st.err = 'Could not load scores. Trying again shortly.'; render(); });
  }
  root.querySelector('.ls-q').addEventListener('input', function (e) { st.q = e.target.value; render(); });
  setInterval(function () { if (!document.hidden && st.date === today) load(); }, 30000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) load(); });
  render(); load();
})();
</script>
"""


def scores_body(url, picks, tables=None):
    cfg = {"tables": tables or {}, "url": url, "picks": {k: {"pk": v["pk"], "h": v["h"], "a": v["a"], "hp": v["hp"], "dp": v["dp"], "ap": v["ap"]} for k, v in picks.items()}}
    html = """
<section class="ls" id="ls">
  <div class="ls-head"><h2>Live scores</h2><a href="live/">Live pressure &rarr;</a></div>
  <div class="ls-days" role="group" aria-label="Day"></div>
  <div class="ls-tools"><div class="ls-fl" style="display:flex;gap:6px;flex-wrap:wrap"></div>
    <input class="ls-q" type="search" placeholder="Search team, league or country" aria-label="Search matches"></div>
  <select class="ls-sel" aria-label="Country"></select>
  <div class="ls-grid"><nav class="ls-side" aria-label="Countries"></nav><div class="ls-list" aria-live="polite"></div></div>
  <p class="ls-note">Scores from every league in the world, updated about every 30 seconds. Tap a match with goals or cards to see them. Times are UK time.</p>
</section>"""
    return CSS + html + JS.replace("__CFG__", json.dumps(cfg).replace("</", "<\\/"))
