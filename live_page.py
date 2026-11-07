# -*- coding: utf-8 -*-
"""Live tab: in-play matches with key stats and an experimental 'attacking pressure' meter."""
import json

CSS = """
<style>
.lp-note { color:var(--muted); font-size:14px; margin:0 0 14px; }
.lp-badge { display:inline-block; background:var(--flood); color:var(--flood-ink); font:700 11px/1 Barlow,sans-serif; letter-spacing:.06em; text-transform:uppercase; padding:4px 7px; border-radius:6px; margin-right:6px; vertical-align:middle; }
.lp-card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 16px; margin:0 0 12px; }
.lp-card.hot { border-color:#c0392b; box-shadow:0 0 0 2px rgba(192,57,43,.18); }
.lp-flag { display:inline-block; background:#c0392b; color:#fff; font:700 11px/1 Barlow,sans-serif; letter-spacing:.06em; text-transform:uppercase; padding:4px 7px; border-radius:6px; margin-left:8px; vertical-align:middle; }
.lp-lg { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
.lp-top { display:flex; align-items:center; gap:10px; margin:2px 0 10px; }
.lp-min { font:700 14px Barlow,sans-serif; color:#fff; background:#c0392b; border-radius:6px; padding:3px 7px; white-space:nowrap; }
.lp-min.pause { background:#7a8a80; }
.lp-teams { flex:1; font:800 22px/1.05 "Barlow Condensed",sans-serif; }
.lp-score { font:800 28px/1 "Barlow Condensed",sans-serif; white-space:nowrap; }
.lp-meter { display:grid; grid-template-columns:1fr 1fr 1fr; gap:4px; margin:6px 0 4px; }
.lp-meter i { height:10px; border-radius:5px; background:var(--line); }
.lp-meter.low i:nth-child(1) { background:#8aa597; }
.lp-meter.building i:nth-child(-n+2) { background:#d9a521; }
.lp-meter.high i { background:#c0392b; }
.lp-mrow { display:flex; justify-content:space-between; align-items:baseline; gap:10px; flex-wrap:wrap; }
.lp-lvl { font-weight:700; } .lp-chance { font-size:14px; color:var(--muted); }
.lp-chance b { color:var(--ink); font:800 20px "Barlow Condensed",sans-serif; }
.lp-who { font-size:13px; color:var(--muted); margin:2px 0 10px; min-height:18px; }
.lp-stats { border-top:1px solid var(--line); padding-top:8px; }
.lp-st { display:grid; grid-template-columns:44px 1fr 44px; align-items:center; font-size:14px; padding:3px 0; }
.lp-st b { font-weight:700; } .lp-st b:last-child { text-align:right; }
.lp-st span { text-align:center; color:var(--muted); font-size:13px; }
.lp-none { background:#fff; border:1px dashed var(--line); border-radius:14px; padding:18px; color:var(--muted); }
.lp-wait { font-size:13px; color:var(--muted); margin:6px 0 0; }
</style>"""

JS = r"""
<script>
(function(){
var C = __CFG__, root = document.getElementById('lp'), picks = C.picks || {};
var HKEY = 'fp-pressure-v1', hist = {};
try { hist = JSON.parse(localStorage.getItem(HKEY) || '{}'); } catch (e) { hist = {}; }
var LGN = {39:'Premier League',140:'La Liga',78:'Bundesliga',135:'Serie A',61:'Ligue 1',2:'Champions League',3:'Europa League',848:'Conference League',40:'Championship',41:'League One',42:'League Two',179:'Scottish Premiership',88:'Eredivisie',94:'Primeira Liga',144:'Belgian Pro League',197:'Greek Super League',203:'Super Lig',79:'2. Bundesliga',136:'Serie B',141:'Segunda Division',62:'Ligue 2'};
function el(t, c, x){ var e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; }
function num(v){ return typeof v === 'number' && isFinite(v) ? v : 0; }
function pack(s){ s = s || {}; return { sh: num(s.sh), sot: num(s.sot), co: num(s.co), xg: (typeof s.xg === 'number' && isFinite(s.xg)) ? s.xg : null }; }
/* rough goals expected from the chances a team has made: shots off target, shots on target, corners */
function est(p){ return p.xg != null ? p.xg : 0.04 * Math.max(p.sh - p.sot, 0) + 0.30 * p.sot + 0.03 * p.co; }
function snap(m){
  if (!m.sx) return;
  var a = hist[m.id] = hist[m.id] || [], now = Date.now();
  if (a.length && now - a[a.length - 1].t < 40000) return;
  a.push({ t: now, h: pack(m.sx.h), a: pack(m.sx.a) });
  while (a.length && now - a[0].t > 25 * 60000) a.shift();
}
function model(m){
  var pk = picks[String(m.id)], bx = (pk && pk.xh != null) ? [pk.xh, pk.xa] : [1.4, 1.15];
  var t = Math.min(m.el || 0, 90), live = m.st === '1H' || m.st === '2H' || m.st === 'ET';
  var r0h = bx[0] / 90, r0a = bx[1] / 90, rh = r0h, ra = r0a, basis = 'pre';
  var sx = m.sx, now = Date.now(), h = sx ? pack(sx.h) : null, a = sx ? pack(sx.a) : null;
  if (sx && t >= 8) {
    var wc = Math.min(t / 90, 1) * 0.5, ww = 0, wh = 0, wa = 0;
    var cum = hist[m.id] || [], old = null;
    for (var i = 0; i < cum.length; i++) { var age = (now - cum[i].t) / 60000; if (age <= 16 && age >= 3) { old = cum[i]; break; } }
    if (old) {
      var dt = (now - old.t) / 60000;
      ww = Math.min(dt / 15, 1) * 0.4;
      wh = Math.max(est(h) - est(old.h), 0) / dt; wa = Math.max(est(a) - est(old.a), 0) / dt;
      basis = 'recent';
    } else basis = 'match';
    rh = (1 - wc - ww) * r0h + wc * est(h) / Math.max(t, 1) + ww * wh;
    ra = (1 - wc - ww) * r0a + wc * est(a) / Math.max(t, 1) + ww * wa;
  }
  var d = m.hg - m.ag, late = 1 + 0.1 * Math.max(0, (t - 70) / 20);
  var mh = (d < 0 ? 1 + 0.08 * Math.min(-d, 2) : d > 0 ? 1 - 0.05 * Math.min(d, 2) : 1);
  var ma = (d > 0 ? 1 + 0.08 * Math.min(d, 2) : d < 0 ? 1 - 0.05 * Math.min(-d, 2) : 1);
  if (sx) { mh *= Math.pow(0.8, num(sx.h.rc)) * Math.pow(1.2, num(sx.a.rc)); ma *= Math.pow(0.8, num(sx.a.rc)) * Math.pow(1.2, num(sx.h.rc)); }
  rh *= mh * late; ra *= ma * late;
  var hor = live ? Math.max(1, Math.min(15, 95 - t)) : 15;
  var P = 1 - Math.exp(-(rh + ra) * hor), ratio = (rh + ra) / (r0h + r0a);
  var level = ratio >= 1.25 ? 'high' : ratio >= 0.85 ? 'building' : 'low';
  var fh = rh / (r0h * mh * late), fa = ra / (r0a * ma * late), who = '';
  if (sx && t >= 8) { if (fh > 1.15 * fa && fh > 1.0) who = m.home; else if (fa > 1.15 * fh && fa > 1.0) who = m.away; else who = 'both sides'; }
  return { P: P, level: level, who: who, basis: basis, live: live, hor: hor };
}
function minute(m){
  if (m.st === 'HT') return 'HT'; if (m.st === 'BT' || m.st === 'INT') return 'Break'; if (m.st === 'P') return 'Pens';
  return (m.el || 0) + (m.ex ? '+' + m.ex : '') + "'";
}
function statRow(label, a, b, pct){
  var r = el('div', 'lp-st');
  r.appendChild(el('b', '', a == null ? '-' : a + (pct ? '%' : '')));
  r.appendChild(el('span', '', label));
  r.appendChild(el('b', '', b == null ? '-' : b + (pct ? '%' : '')));
  return r;
}
function card(m){
  var md = model(m), c = el('div', 'lp-card' + (md.live && md.level === 'high' ? ' hot' : ''));
  var lgl = el('div', 'lp-lg', LGN[m.lg] || 'Football');
  if (md.live && md.level === 'high') lgl.appendChild(el('span', 'lp-flag', 'High pressure' + (md.who && md.who !== 'both sides' ? ': ' + md.who : '')));
  c.appendChild(lgl);
  var top = el('div', 'lp-top');
  top.appendChild(el('span', 'lp-min' + (md.live ? '' : ' pause'), minute(m)));
  top.appendChild(el('span', 'lp-teams', m.home + ' v ' + m.away));
  top.appendChild(el('span', 'lp-score', m.hg + ' – ' + m.ag));
  c.appendChild(top);
  if (md.live || m.st === 'HT') {
    var mr = el('div', 'lp-mrow');
    var lv = el('span', 'lp-lvl', 'Attacking pressure: ' + md.level); mr.appendChild(lv);
    var ch = el('span', 'lp-chance'); ch.appendChild(document.createTextNode('Chance of a goal in the next ' + md.hor + ' min ')); ch.appendChild(el('b', '', Math.round(md.P * 100) + '%'));
    mr.appendChild(ch); c.appendChild(mr);
    var mt = el('div', 'lp-meter ' + md.level); mt.appendChild(el('i')); mt.appendChild(el('i')); mt.appendChild(el('i')); c.appendChild(mt);
    c.appendChild(el('div', 'lp-who', md.who ? (md.who === 'both sides' ? 'Pressure is spread across both sides' : 'Pressure is coming from ' + md.who + ' (attacking)') : (m.sx ? 'Too early to say which side is on top' : 'Live stats not available yet, so no side to show')));
  }
  if (m.sx) {
    var s = el('div', 'lp-stats'), H = m.sx.h || {}, A = m.sx.a || {};
    s.appendChild(statRow('Possession', H.pos, A.pos, true));
    s.appendChild(statRow('Shots', H.sh, A.sh));
    s.appendChild(statRow('On target', H.sot, A.sot));
    s.appendChild(statRow('Corners', H.co, A.co));
    s.appendChild(statRow('Yellow cards', H.yc, A.yc));
    if (num(H.rc) || num(A.rc)) s.appendChild(statRow('Red cards', num(H.rc), num(A.rc)));
    c.appendChild(s);
    if (md.basis === 'pre') c.appendChild(el('p', 'lp-wait', 'Early in the match, so the meter is still close to our pre-match expectation.'));
  } else c.appendChild(el('p', 'lp-wait', 'Match stats are not available yet.'));
  return c;
}
function nextKick(){
  var best = null, now = Date.now();
  Object.keys(picks).forEach(function(k){ var t = Date.parse(picks[k].ko); if (t > now && (!best || t < best)) best = t; });
  if (!best) return 'Check back around kick-off time.';
  var d = new Date(best), today = new Date().toDateString() === d.toDateString();
  return 'Next kick-off: ' + (today ? 'today' : d.toLocaleDateString([], { weekday: 'long' })) + ' at ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + '.';
}
var STATUS = '';
function render(list, err){
  root.textContent = '';
  var live = list.filter(function(m){ return m.st !== 'FT' && m.st !== 'AET' && m.st !== 'PEN'; });
  live.forEach(function(m){ m._md = model(m); });
  live.sort(function(a, b){ return ((b._md.live && b._md.level === 'high') - (a._md.live && a._md.level === 'high')) || (a.lg - b.lg) || (a.id - b.id); });
  if (!live.length) { root.appendChild(el('div', 'lp-none', (err ? 'Live data is not available right now. ' : 'No matches in play right now. ') + nextKick() + (STATUS ? ' (' + STATUS + ')' : ''))); return; }
  root.appendChild(el('p', 'lp-note', live.length + (live.length === 1 ? ' match' : ' matches') + ' in play. Updates every minute while this page is open.'));
  live.forEach(function(m){ root.appendChild(card(m)); });
  root.appendChild(el('p', 'lp-wait', STATUS));
}
var last = [];
function poll(){
  if (document.hidden) return;
  fetch(C.url, { cache: 'no-store' }).then(function(r){ return r.ok ? r.json() : null; }).then(function(j){
    var hm = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (!j || !j.matches) { STATUS = 'Last check ' + hm + ': the live feed did not answer.'; render(last, true); return; }
    last = j.matches; last.forEach(snap);
    STATUS = 'Last check ' + hm + ': ' + last.length + ' in play, ' + last.filter(function(m){ return m.sx; }).length + ' with stats' + (j.error ? ' (feed says: ' + j.error + ')' : '') + (j.dbg ? ' [stats calls: ' + (j.dbg.bulk || []).join(',') + '; ' + (j.dbg.single || 0) + ' single]' : '') + '.';
    try { localStorage.setItem(HKEY, JSON.stringify(hist)); } catch (e) {}
    render(last, false);
  }).catch(function(){ STATUS = 'Last check ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ': could not reach the live feed.'; render(last, true); });
}
poll(); setInterval(poll, 60000);
document.addEventListener('visibilitychange', function(){ if (!document.hidden) poll(); });
})();
</script>"""


def live_body(url, picks):
    cfg = json.dumps({"url": url, "picks": {k: {"ko": v["ko"], "xh": v.get("xh"), "xa": v.get("xa")} for k, v in picks.items()}}).replace("</", "<\\/")
    note = ('<section class="block"><p class="lp-note"><span class="lp-badge">Experimental</span>'
            'The pressure meter compares each team\'s recent shots, shots on target and corners with what we expected before kick-off, '
            'and adjusts for the score, the minute and red cards. The chance of a goal is an estimate from that, not a prediction of what will happen. '
            'It is information only, not advice.</p></section>')
    return (CSS + note + '<section class="block"><div id="lp" aria-live="polite"><div class="lp-none">Loading live matches&hellip;</div></div></section>'
            + JS.replace("__CFG__", cfg))
