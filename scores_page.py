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
  var st = { date: null, filter: 'all', q: '', data: null, open: {}, err: '' };
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
    r.onclick = function () { if (m.ev && m.ev.length) { st.open[m.id] = !st.open[m.id]; render(); } };
    wrap.appendChild(r); return wrap;
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
      .then(function (j) { busy = false; if (d !== st.date) return load(); if (j.error) { st.err = 'Scores are catching their breath. Trying again shortly.'; if (!st.data) st.data = null; } else { st.data = j.matches || []; st.err = ''; } render(); })
      .catch(function () { busy = false; if (!st.data) st.err = 'Could not load scores. Trying again shortly.'; render(); });
  }
  root.querySelector('.ls-q').addEventListener('input', function (e) { st.q = e.target.value; render(); });
  setInterval(function () { if (!document.hidden && st.date === today) load(); }, 30000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) load(); });
  render(); load();
})();
</script>
"""


def scores_body(url, picks):
    cfg = {"url": url, "picks": {k: {"pk": v["pk"], "h": v["h"], "a": v["a"], "hp": v["hp"], "dp": v["dp"], "ap": v["ap"]} for k, v in picks.items()}}
    html = """
<section class="ls" id="ls">
  <div class="ls-head"><h2>Live scores</h2><a href="live/">Live pressure &rarr;</a></div>
  <div class="ls-days" role="group" aria-label="Day"></div>
  <div class="ls-tools"><div class="ls-fl" style="display:flex;gap:6px;flex-wrap:wrap"></div>
    <input class="ls-q" type="search" placeholder="Search team, league or country" aria-label="Search matches"></div>
  <div class="ls-list" aria-live="polite"></div>
  <p class="ls-note">Scores from every league in the world, updated about every 30 seconds. Tap a match with goals or cards to see them. Times are UK time.</p>
</section>"""
    return CSS + html + JS.replace("__CFG__", json.dumps(cfg).replace("</", "<\\/"))
