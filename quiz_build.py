# -*- coding: utf-8 -*-
"""Daily football quiz: builds a pool of questions from our own season data; the page picks 10 a day."""
import json
import os
import random

LEAGUES = [("premier-league", "Premier League"), ("la-liga", "La Liga"), ("bundesliga", "Bundesliga"),
           ("serie-a", "Serie A"), ("ligue-1", "Ligue 1")]
STATS = [("goals", "scored more league goals", "goals"), ("assists", "has more assists", "assists"),
         ("yellow", "has been shown more yellow cards", "yellow cards"), ("sot", "has had more shots on target", "shots on target")]


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def team_table(fixtures):
    t = {}
    for f in fixtures:
        if f.get("status") != "FT" or f.get("hg") is None:
            continue
        for me, opp, gf, ga in ((f["home"], f["away"], f["hg"], f["ag"]), (f["away"], f["home"], f["ag"], f["hg"])):
            r = t.setdefault(me, {"gf": 0, "ga": 0, "w": 0, "cs": 0, "p": 0})
            r["gf"] += gf; r["ga"] += ga; r["p"] += 1
            r["w"] += gf > ga
            r["cs"] += ga == 0
    return t


def build_pool(squads):
    rng = random.Random("fp-quiz-pool")
    hl_p, hl_t, guess = [], [], []
    for key, name in LEAGUES:
        base = os.path.join("data", key)
        players = _load(os.path.join(base, "players_2026.json")) or []
        fixtures = _load(os.path.join(base, "fixtures_2026.json")) or []
        regulars = [p for p in players if p.get("minutes", 0) >= 270 and p.get("position") != "Goalkeeper"]
        names = {}
        for p in regulars:
            names[p["name"]] = names.get(p["name"], 0) + 1
        regulars = [p for p in regulars if names[p["name"]] == 1]
        # higher or lower: players
        for stat, verb, label in STATS:
            pool = [p for p in regulars if p.get(stat, 0) >= (2 if stat != "sot" else 4)]
            rng.shuffle(pool)
            seen = set()
            for i in range(0, len(pool) - 1, 2):
                a, b = pool[i], pool[i + 1]
                if a[stat] == b[stat] or a["team"] == b["team"] or (a["id"], b["id"]) in seen:
                    continue
                if max(a[stat], b[stat]) > 2.5 * min(a[stat], b[stat]) + 2:
                    continue   # too lopsided to be fun
                hl_p.append({"q": f"Who {verb} this season in the {name}?", "o": [f'{a["name"]} ({a["team"]})', f'{b["name"]} ({b["team"]})'],
                             "a": 0 if a[stat] > b[stat] else 1, "n": f'{a["name"]} {a[stat]}, {b["name"]} {b[stat]} {label}.'})
        # higher or lower: teams
        table = team_table(fixtures)
        teams = sorted(table)
        for stat, verb, label in (("gf", "has scored more goals", "goals scored"), ("ga", "has conceded more goals", "goals conceded"),
                                  ("w", "has won more matches", "wins"), ("cs", "has kept more clean sheets", "clean sheets")):
            for _ in range(8):
                if len(teams) < 2:
                    break
                a, b = rng.sample(teams, 2)
                va, vb = table[a][stat], table[b][stat]
                if abs(va - vb) < 2 or table[a]["p"] != table[b]["p"] and abs(table[a]["p"] - table[b]["p"]) > 1:
                    continue
                hl_t.append({"q": f"Which {name} team {verb} this season?", "o": [a, b], "a": 0 if va > vb else 1,
                             "n": f"{a} {va}, {b} {vb} {label}."})
        # guess the player
        cands = [p for p in regulars if (p["goals"] >= 2 or p["assists"] >= 2) and str(p["id"]) in squads]
        for p in cands:
            same = [x for x in regulars if x["position"] == p["position"] and x["id"] != p["id"] and x["team"] != p["team"]]
            if len(same) < 3:
                continue
            opts = [p["name"]] + [x["name"] for x in rng.sample(same, 3)]
            if len(set(opts)) < 4:
                continue
            guess.append({"pos": p["position"], "lg": name, "no": int(squads[str(p["id"])]), "g": p["goals"], "a": p["assists"],
                          "y": p["yellow"], "ap": p["apps"], "club": p["team"], "ans": p["name"], "opts": opts})
    rng.shuffle(hl_p); rng.shuffle(hl_t); rng.shuffle(guess)
    return {"hp": hl_p[:80], "ht": hl_t[:40], "gp": guess[:60]}


QUIZ_CSS = """
<style>
.qz { max-width:640px; margin:0 auto; }
.qz-top { display:flex; justify-content:space-between; align-items:center; color:var(--muted); font-size:14px; margin-bottom:8px; }
.qz-bar { height:8px; background:var(--line); border-radius:6px; overflow:hidden; margin-bottom:16px; }
.qz-bar i { display:block; height:100%; background:var(--pitch); width:0; transition:width .3s; }
.qz-card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:18px; }
.qz-q { font:800 26px/1.1 "Barlow Condensed",sans-serif; margin:0 0 12px; }
.qz-clues { list-style:none; margin:0 0 14px; padding:0; display:flex; flex-wrap:wrap; gap:6px; }
.qz-clues li { background:#eef2ee; border-radius:8px; padding:5px 9px; font-size:14px; font-weight:600; }
.qz-opts { display:grid; gap:10px; }
.qz-opts button, .qz-btn { font:600 16px Barlow,sans-serif; text-align:left; padding:13px 14px; border-radius:11px; border:1.5px solid var(--line); background:#fff; color:var(--ink); cursor:pointer; }
.qz-opts button:hover:not(:disabled) { border-color:var(--pitch); }
.qz-opts button.ok { background:#d9f3e0; border-color:#2f9e55; }
.qz-opts button.bad { background:#fbdcdc; border-color:#d04a4a; }
.qz-btn.main { background:var(--pitch); color:#fff; border-color:var(--pitch); text-align:center; }
.qz-btn.ghost { text-align:center; }
.qz-note { margin:12px 0 0; font-size:14px; color:var(--muted); min-height:20px; }
.qz-end h2 { font:800 44px/1 "Barlow Condensed",sans-serif; margin:0 0 4px; }
.qz-grid { font-size:22px; letter-spacing:0; margin:10px 0; }
.qz-stats { display:flex; gap:12px; margin:12px 0; }
.qz-stats div { flex:1; background:#eef2ee; border-radius:10px; padding:10px; text-align:center; }
.qz-stats b { display:block; font:800 26px "Barlow Condensed",sans-serif; }
.qz-stats span { font-size:12px; color:var(--muted); }
.qz-row { display:flex; gap:10px; margin-top:12px; } .qz-row > * { flex:1; }
</style>"""

QUIZ_JS = r"""
<script>
(function(){
var POOL = __QDATA__;
var START = Date.UTC(2026, 10, 6);          // quiz #1
var DAY = Math.floor((Date.now() - START) / 86400000) + 1;
if (DAY < 1) DAY = 1;
var KEY = 'fp-quiz-v1';
function load(){ try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch(e){ return {}; } }
function save(s){ try { localStorage.setItem(KEY, JSON.stringify(s)); } catch(e){} }
function rng(seed){ return function(){ seed |= 0; seed = seed + 0x6D2B79F5 | 0; var t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
var R = rng(DAY * 7919 + 13);
function pick(arr, n){ var a = arr.slice(), out = []; while (out.length < n && a.length) out.push(a.splice(Math.floor(R() * a.length), 1)[0]); return out; }
function shuffle(a){ a = a.slice(); for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(R() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
var qs = [];
pick(POOL.hp, 4).forEach(function(q){ qs.push({t:'hl', q:q}); });
pick(POOL.ht, 2).forEach(function(q){ qs.push({t:'hl', q:q}); });
pick(POOL.gp, 4).forEach(function(q){ qs.push({t:'gp', q:q, o: shuffle(q.opts)}); });
qs = shuffle(qs);
var root = document.getElementById('qz');
function el(tag, cls, txt){ var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
var S = load(), i = 0, marks = [];
S.days = S.days || {};
function untilNext(){ var ms = START + DAY * 86400000 - Date.now(); var h = Math.floor(ms / 3600000), m = Math.floor(ms % 3600000 / 60000); return h + 'h ' + m + 'm'; }
function finish(marks){
  var score = marks.filter(function(m){ return m !== 'R'; }).length;
  var grid = marks.map(function(m){ return m === 'G' ? '🟩' : m === 'Y' ? '🟨' : '🟥'; }).join('');
  if (!S.days[DAY]) {
    S.days[DAY] = {s: score, g: grid};
    S.streak = (S.last === DAY - 1) ? (S.streak || 0) + 1 : 1;
    S.last = DAY; S.best = Math.max(S.best || 0, S.streak);
    S.played = (S.played || 0) + 1; S.total = (S.total || 0) + score;
    save(S);
  } else { score = S.days[DAY].s; grid = S.days[DAY].g; }
  root.textContent = '';
  var card = el('div', 'qz-card qz-end');
  card.appendChild(el('p', 'qz-note', 'FootyPredicts Daily Quiz #' + DAY));
  card.appendChild(el('h2', '', score + ' / 10'));
  card.appendChild(el('div', 'qz-grid', grid));
  var st = el('div', 'qz-stats');
  [[S.streak || 1, 'day streak'], [S.best || 1, 'best streak'], [S.played ? Math.round(S.total / S.played * 10) / 10 : score, 'average score']].forEach(function(x){ var d = el('div'); d.appendChild(el('b', '', x[0])); d.appendChild(el('span', '', x[1])); st.appendChild(d); });
  card.appendChild(st);
  var text = 'FootyPredicts Quiz #' + DAY + ' ' + score + '/10\n' + grid + '\nfootypredicts.com/quiz/';
  var row = el('div', 'qz-row');
  var sh = el('button', 'qz-btn main', 'Share my score');
  sh.onclick = function(){
    if (navigator.share) { navigator.share({text: text}).catch(function(){}); }
    else if (navigator.clipboard) { navigator.clipboard.writeText(text).then(function(){ sh.textContent = 'Copied!'; }); }
    else { window.prompt('Copy your score:', text); }
  };
  row.appendChild(sh);
  var rv = el('a', 'qz-btn ghost', 'Today’s predictions'); rv.href = '../'; rv.style.textDecoration = 'none';
  row.appendChild(rv);
  card.appendChild(row);
  card.appendChild(el('p', 'qz-note', 'Next quiz in ' + untilNext() + '. Come back tomorrow to keep your streak going.'));
  root.appendChild(card);
}
function show(){
  if (S.days[DAY]) { finish([]); return; }
  root.textContent = '';
  var top = el('div', 'qz-top'); top.appendChild(el('span', '', 'Quiz #' + DAY)); top.appendChild(el('span', '', (i + 1) + ' of 10'));
  root.appendChild(top);
  var bar = el('div', 'qz-bar'); var fill = el('i'); fill.style.width = (i / 10 * 100) + '%'; bar.appendChild(fill); root.appendChild(bar);
  var item = qs[i], card = el('div', 'qz-card'), note = el('p', 'qz-note', ''), next = el('button', 'qz-btn main', i === 9 ? 'See my score' : 'Next question');
  next.hidden = true; next.style.marginTop = '12px'; next.style.width = '100%';
  var opts = el('div', 'qz-opts'), hinted = false;
  function done(ok){
    marks.push(ok ? (hinted ? 'Y' : 'G') : 'R');
    Array.prototype.forEach.call(opts.children, function(b){ b.disabled = true; });
    next.hidden = false; if (hint) hint.hidden = true;
  }
  var hint = null;
  if (item.t === 'hl') {
    card.appendChild(el('h2', 'qz-q', item.q.q));
    item.q.o.forEach(function(label, k){
      var b = el('button', '', label);
      b.onclick = function(){ var ok = k === item.q.a; b.className = ok ? 'ok' : 'bad'; if (!ok) opts.children[item.q.a].className = 'ok'; note.textContent = (ok ? 'Correct. ' : 'Not this time. ') + item.q.n; done(ok); };
      opts.appendChild(b);
    });
  } else {
    var g = item.q;
    card.appendChild(el('h2', 'qz-q', 'Who is this player?'));
    var cl = el('ul', 'qz-clues');
    ['Plays in the ' + g.lg, g.pos, 'Shirt number ' + g.no, g.g + ' goals', g.a + ' assists', g.y + ' yellow cards', g.ap + ' appearances'].forEach(function(c){ cl.appendChild(el('li', '', c)); });
    var clubLi = el('li', '', 'Club: ' + g.club); clubLi.hidden = true; cl.appendChild(clubLi);
    card.appendChild(cl);
    item.o.forEach(function(label){
      var b = el('button', '', label);
      b.onclick = function(){ var ok = label === g.ans; b.className = ok ? 'ok' : 'bad'; if (!ok) Array.prototype.forEach.call(opts.children, function(x){ if (x.textContent === g.ans) x.className = 'ok'; }); note.textContent = ok ? 'Correct, it is ' + g.ans + (hinted ? ' (with the club hint, so a yellow square).' : '.') : 'It was ' + g.ans + ' (' + g.club + ').'; done(ok); };
      opts.appendChild(b);
    });
    hint = el('button', 'qz-btn ghost', 'Show the club (a hint)'); hint.style.margin = '0 0 12px'; hint.style.width = '100%';
    hint.onclick = function(){ hinted = true; clubLi.hidden = false; hint.hidden = true; };
    card.appendChild(hint);
  }
  card.appendChild(opts); card.appendChild(note); card.appendChild(next);
  next.onclick = function(){ if (i === 9) finish(marks); else { i++; show(); } };
  root.appendChild(card);
}
show();
})();
</script>"""


def quiz_body(pool):
    data = json.dumps(pool, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (QUIZ_CSS + '\n<section class="block"><div class="qz" id="qz"><noscript>The quiz needs JavaScript.</noscript></div></section>'
            '\n<section class="block"><p class="halves">A new quiz every day: 10 questions built from this season\'s real stats in the top five leagues. '
            'Your streak and scores are saved only on this device. No sign-up.</p></section>'
            + QUIZ_JS.replace("__QDATA__", data))
