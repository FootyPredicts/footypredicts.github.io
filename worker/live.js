// Cloudflare Worker: live scores relay for FootyPredicts.
// Keeps the API-Football key secret and caches the answer for 30 seconds,
// so any number of visitors cost at most ~2 API calls a minute.
// Secret needed: API_FOOTBALL_KEY (Worker -> Settings -> Variables and Secrets).

const LEAGUES = "39-140-78-135-61-2-3"; // Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, Europa League
// The Live tab asks for ?scope=all: those plus Conference League, the English lower leagues, Scotland and other big European leagues.
const LEAGUES_ALL = LEAGUES + "-848-40-41-42-179-88-94-144-197-203-79-136-141-62";
const ALLOWED = [
  "https://footypredicts.com",
  "https://www.footypredicts.com",
  "https://footypredicts.github.io",
];

const STAT_KEYS = {
  "Ball Possession": "pos", "Total Shots": "sh", "Shots on Goal": "sot", "Corner Kicks": "co",
  "Fouls": "fo", "Offsides": "of", "Yellow Cards": "yc", "Red Cards": "rc", "expected_goals": "xg",
};

function statsOf(f) {
  const out = { h: {}, a: {} };
  const list = f.statistics || [];
  for (const t of list) {
    const side = t.team && t.team.id === f.teams.home.id ? "h" : "a";
    for (const s of t.statistics || []) {
      const k = STAT_KEYS[s.type];
      if (!k) continue;
      let v = s.value;
      if (typeof v === "string") v = parseFloat(v);
      out[side][k] = v == null || Number.isNaN(v) ? null : v;
    }
  }
  return list.length ? out : null;
}

// Timer: GitHub's own schedules are unreliable, so Cloudflare starts the jobs on time instead.
// Needs the secret GITHUB_TOKEN (fine-grained token, this repo only, "Actions: read and write").
// Add these cron triggers to the worker (Settings -> Triggers -> Cron Triggers), times are UTC:
//   0 6 * * *                  daily prediction update
//   7,37 9-21 * * *            matchday refresh (injuries, line-ups)
//   0 10,12,14,16,18,20 * * *  pressure log
//   */20 11-21 * * *           capture line-ups
//   40 8,12,16,20 * * *        team news
const REPO = "FootyPredicts/footypredicts.github.io";
const JOBS = {
  "0 6 * * *": ["update-predictions.yml"],
  "7,37 9-21 * * *": ["matchday-refresh.yml"],
  "0 10,12,14,16,18,20 * * *": ["pressure-log.yml"],
  "*/20 11-21 * * *": ["capture-lineups.yml"],
  "40 8,12,16,20 * * *": ["team-news.yml"],
};

async function dispatch(env, file) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${file}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "footypredicts-timer",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  console.log(file, r.status);
  return r.status;
}


// ---------------------------------------------------------------- Alerts (web push)
// Needs: a KV namespace bound as ALERTS, and the secret VAPID_PRIVATE_JWK.
// Pushes carry no text: the browser wakes our service worker, which asks ?push=msg for what is new for that person.
const SITE = "https://footypredicts.com";
const VAPID_PUBLIC = "BB5-VWMp0PQzam8Qnnok8QdP07wLgs1iGtacsKSumJbR-DOe6E_WqWPRSUePJU2QG5GWbtRVuTZ_7Q6ryMlBSTE";

const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
async function sha(s) {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}
async function vapidAuth(env, endpoint) {
  const key = await crypto.subtle.importKey("jwk", JSON.parse(env.VAPID_PRIVATE_JWK), { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const enc = (o) => b64u(new TextEncoder().encode(JSON.stringify(o)));
  const input = enc({ typ: "JWT", alg: "ES256" }) + "." + enc({ aud: new URL(endpoint).origin, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: SITE });
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, new TextEncoder().encode(input));
  return `vapid t=${input}.${b64u(sig)}, k=${VAPID_PUBLIC}`;
}
async function sendPush(env, endpoint) {
  try {
    const r = await fetch(endpoint, { method: "POST", headers: { Authorization: await vapidAuth(env, endpoint), TTL: "3600", Urgency: "normal", "Content-Length": "0" } });
    return r.status;
  } catch (e) { return 0; }
}

// One shared way to call API-Football: cached at the edge, but a failed answer (rate limit etc.) is never cached,
// so one bad minute cannot keep the site empty for longer than that minute.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// API-Football refuses bursts of calls, so every upstream call in this worker goes through one queue with a short gap.
let gate = Promise.resolve();
function queued(fn) {
  const run = gate.then(fn);
  gate = run.catch(() => {}).then(() => sleep(300));
  return run;
}
async function apif(env, path, ttl) {
  const ck = new Request("https://cache.footypredicts.invalid/" + path);
  const cache = caches.default;
  const hit = await cache.match(ck);
  if (hit) return hit;
  let r, txt = "", bad = true;
  for (let attempt = 0; attempt < 3; attempt++) {
    r = await queued(() => fetch("https://v3.football.api-sports.io/" + path, { headers: { "x-apisports-key": env.API_FOOTBALL_KEY } }));
    if (!r.ok) return r;
    txt = await r.text();
    bad = false;
    try { const e = JSON.parse(txt).errors; bad = !!e && (Array.isArray(e) ? e.length > 0 : Object.keys(e).length > 0); } catch (e) { bad = true; }
    // Refused for going too fast: wait a moment and try again. Any other error is final.
    if (bad && /rateLimit/i.test(txt) && attempt < 2) { await sleep(1200 * (attempt + 1)); continue; }
    break;
  }
  const sk = new Request("https://cache.footypredicts.invalid/stale/" + path);
  if (bad) {
    // Still refused: serve the last good answer (up to 10 minutes old) rather than nothing.
    const old = await cache.match(sk);
    if (old) return old;
    return new Response(txt, { status: 429, headers: { "Content-Type": "application/json" } });
  }
  const out = new Response(txt, { status: 200, headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=" + ttl } });
  await cache.put(ck, out.clone());
  await cache.put(sk, new Response(txt, { status: 200, headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=600" } }));
  return out;
}

const kvj = async (env, k, d) => (await env.ALERTS.get(k, "json")) || d;

async function pushApi(request, env, cors, q) {
  const mode = q.get("push");
  if (mode === "msg") {
    const id = (q.get("id") || "").slice(0, 40), since = Number(q.get("since")) || 0;
    const subs = await kvj(env, "subs", {});
    const me = subs[id];
    if (!me) return json({ ts: Date.now(), messages: [] }, cors, 0);
    const st = await kvj(env, "state", { events: [] });
    const msgs = st.events.filter((e) => e.ts > since && ((e.clubs || []).some((c) => me.c.includes(c)) || (e.news && e.lg && me.l.includes(e.lg))));
    return json({ ts: Date.now(), messages: msgs.slice(-5).map((e) => ({ id: e.id, title: e.title, body: e.body, url: e.url })) }, cors, 0);
  }
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405, headers: cors });
  const text = await request.text();
  if (text.length > 6000) return json({ ok: false, error: "too big" }, cors, 0);
  let b; try { b = JSON.parse(text); } catch (e) { return json({ ok: false, error: "bad json" }, cors, 0); }
  const ep = b && b.endpoint;
  if (typeof ep !== "string" || !ep.startsWith("https://") || ep.length > 1000) return json({ ok: false, error: "bad endpoint" }, cors, 0);
  const id = await sha(ep);
  const subs = await kvj(env, "subs", {});
  if (mode === "unsub") { delete subs[id]; await env.ALERTS.put("subs", JSON.stringify(subs)); return json({ ok: true }, cors, 0); }
  const ok = (a, n) => (Array.isArray(a) ? a : []).filter((x) => typeof x === "string" && /^[a-z0-9-]{1,60}$/.test(x)).slice(0, n);
  if (!subs[id] && Object.keys(subs).length >= 20000) return json({ ok: false, error: "full" }, cors, 0);
  subs[id] = { e: ep, c: ok(b.clubs, 60), l: ok(b.leagues, 20), t: Date.now() };
  await env.ALERTS.put("subs", JSON.stringify(subs));
  return json({ ok: true, id }, cors, 0);
}

async function siteJson(path) {
  try { const r = await fetch(SITE + path, { cf: { cacheTtl: 120, cacheEverything: true } }); return r.ok ? await r.json() : null; } catch (e) { return null; }
}

async function alerts(env) {
  if (!env.ALERTS || !env.VAPID_PRIVATE_JWK) return;
  const subs = await kvj(env, "subs", {});
  const list = Object.entries(subs);
  if (!list.length) return;
  const wantClub = new Set(), wantLeague = new Set();
  list.forEach(([, s]) => { s.c.forEach((c) => wantClub.add(c)); s.l.forEach((l) => wantLeague.add(l)); });
  const st = await kvj(env, "state", { events: [], sent: {}, nc: {} });
  st.events = st.events || []; st.sent = st.sent || {}; st.nc = st.nc || {};
  const now = Date.now(), fresh = [];

  // 1. line-ups: a match kicking off within ~95 minutes whose clubs someone follows
  const nx = await siteJson("/api/next.json");
  for (const f of ((nx && nx.fx) || [])) {
    const ko = Date.parse(f.ko), mins = (ko - now) / 60000;
    if (mins > 95 || mins < -10 || st.sent["lu" + f.id]) continue;
    if (!(wantClub.has(f.hs) || wantClub.has(f.as))) continue;
    const r = await apif(env, `fixtures/lineups?fixture=${f.id}`, 120);
    const j = r.ok ? await r.json() : null;
    if (j && (j.response || []).length >= 2) {
      st.sent["lu" + f.id] = now;
      fresh.push({ id: "lu" + f.id, ts: now, clubs: [f.hs, f.as], title: "Line-ups are in", body: `${f.h} v ${f.a}`, url: f.u || SITE + "/" });
    }
  }

  // 2. news: newest headline per club, max 3 a day per club, none overnight (UK)
  const hour = Number(new Date().toLocaleString("en-GB", { hour: "2-digit", hour12: false, timeZone: "Europe/London" }));
  const nw = await siteJson("/api/news.json");
  if (nw && nw.clubs && hour >= 7 && hour < 22) {
    const day = new Date().toISOString().slice(0, 10);
    for (const [slug, c] of Object.entries(nw.clubs)) {
      if (!(wantClub.has(slug) || wantLeague.has(c.lg))) continue;
      for (const it of c.i || []) {
        const when = Date.parse((it.d || "").replace(" ", "T") + ":00Z");
        if (!when || now - when > 12 * 3600e3) continue;
        const key = "nw" + (await sha(it.u)).slice(0, 12);
        if (st.sent[key]) continue;
        const nk = slug + day;
        if ((st.nc[nk] || 0) >= 3) break;
        st.sent[key] = now; st.nc[nk] = (st.nc[nk] || 0) + 1;
        fresh.push({ id: key, ts: now, clubs: [slug], lg: c.lg, news: 1, title: c.n + " news", body: it.t, url: SITE + "/club/" + slug + "/" });
        break;
      }
    }
  }
  if (!fresh.length) return;
  st.events = st.events.concat(fresh).filter((e) => now - e.ts < 2 * 86400e3).slice(-200);
  for (const k of Object.keys(st.sent)) if (now - st.sent[k] > 3 * 86400e3) delete st.sent[k];
  for (const k of Object.keys(st.nc)) if (!k.endsWith(new Date().toISOString().slice(0, 10))) delete st.nc[k];
  await env.ALERTS.put("state", JSON.stringify(st));

  // wake the browsers of everyone affected
  let sent = 0, dropped = false;
  for (const [id, s] of list) {
    if (sent >= 300) break;
    if (!fresh.some((e) => e.clubs.some((c) => s.c.includes(c)) || (e.news && s.l.includes(e.lg)))) continue;
    const code = await sendPush(env, s.e); sent++;
    if (code === 404 || code === 410) { delete subs[id]; dropped = true; }
  }
  if (dropped) await env.ALERTS.put("subs", JSON.stringify(subs));
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(alerts(env).catch((e) => console.log("alerts failed", String(e))));
    if (!env.GITHUB_TOKEN) { console.log("GITHUB_TOKEN not set"); return; }
    ctx.waitUntil(Promise.all((JOBS[event.cron] || []).map((f) => dispatch(env, f))));
  },
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const cors = {
      "Access-Control-Allow-Origin": ALLOWED.includes(origin) ? origin : ALLOWED[0],
      "Vary": "Origin",
    };
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: { ...cors, "Access-Control-Allow-Methods": "GET, POST", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400" } });
    }
    if (new URL(request.url).searchParams.get("push")) {
      if (!env.ALERTS) return json({ ok: false, error: "alerts not set up" }, cors, 0);
      return pushApi(request, env, cors, new URL(request.url).searchParams);
    }
    if (request.method !== "GET") return new Response("Method not allowed", { status: 405, headers: cors });
    if (new URL(request.url).searchParams.get("probe") && env.API_FOOTBALL_KEY) {
      // Diagnostics: what does API-Football say to this worker? Rate-limit numbers only, no account details.
      const out = [];
      for (let i = 0; i < 3; i++) {
        if (i) await sleep(400);
        const r = await fetch("https://v3.football.api-sports.io/fixtures?live=all", { headers: { "x-apisports-key": env.API_FOOTBALL_KEY } });
        let e = null; try { e = (await r.json()).errors; } catch (x) { e = "unreadable"; }
        out.push({ status: r.status, minLimit: r.headers.get("x-ratelimit-limit"), minLeft: r.headers.get("x-ratelimit-remaining"), dayLeft: r.headers.get("x-ratelimit-requests-remaining"), retry: r.headers.get("retry-after"), cfRay: (r.headers.get("cf-ray") || "").slice(-3), errors: e });
      }
      return json({ ts: Date.now(), probe: out }, cors, 0);
    }
    if (!env.API_FOOTBALL_KEY) return json({ ts: Date.now(), matches: [], error: "not configured" }, cors, 10);

    try {
      // The API call itself is cached at Cloudflare's edge for 30 seconds.
      const q = new URL(request.url).searchParams;
      const want = (q.get("ids") || "").split("-").filter((x) => /^\d+$/.test(x)).slice(0, 20);
      if (want.length) {
        // Final scores for matches that have just left the live feed.
        const rf = await apif(env, `fixtures?ids=${want.join("-")}`, 60);
        if (!rf.ok) return json({ ts: Date.now(), matches: [], error: "upstream " + rf.status }, cors, 10);
        const jf = await rf.json();
        return json({ ts: Date.now(), matches: (jf.response || []).map((f) => ({
          id: f.fixture.id, hg: f.goals.home ?? 0, ag: f.goals.away ?? 0, st: f.fixture.status.short, el: f.fixture.status.elapsed,
          ev: (f.events || []).filter((e) => e.type === "Goal" || e.type === "Card").map((e) => ({
            m: e.time.elapsed, x: e.time.extra, s: e.team && e.team.id === f.teams.home.id ? "h" : "a", t: e.type, d: e.detail, p: e.player && e.player.name })),
        })) }, cors, 30);
      }
      const sid = q.get("standings");
      if (sid && /^\d+$/.test(sid)) {
        // League table for any league. Cached for 10 minutes, so visitors cost almost nothing.
        const now = new Date();
        const cur = now.getUTCMonth() >= 6 ? now.getUTCFullYear() : now.getUTCFullYear() - 1;
        const dbgS = [];
        for (const season of [cur, cur - 1]) {
          const rs = await apif(env, `standings?league=${sid}&season=${season}`, 600);
          if (!rs.ok) return json({ ts: Date.now(), groups: [], error: "upstream " + rs.status }, cors, 10);
          const body = await rs.json();
          dbgS.push({ season, results: body.results, errors: body.errors });
          const lg = ((body.response || [])[0] || {}).league;
          if (lg && lg.standings && lg.standings.length) {
            const groups = lg.standings.map((g) => ({
              name: (g[0] && g[0].group) || "",
              rows: g.map((x) => ({ r: x.rank, n: x.team.name, p: x.all.played, w: x.all.win, d: x.all.draw, l: x.all.lose, gf: x.all.goals.for, ga: x.all.goals.against, pts: x.points, f: x.form || "" })),
            }));
            return json({ ts: Date.now(), name: lg.name, season, groups }, cors, 300);
          }
        }
        return json({ ts: Date.now(), groups: [], dbg: dbgS }, cors, 60);
      }
      if (q.get("scope") === "world") {
        // Every match in the world for one day (UK dates), with live matches overlaid. Cached, so visitors cost nothing extra.
        const today = new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/London" });
        let d = q.get("date") || today;
        const diff = (Date.parse(d) - Date.parse(today)) / 864e5;
        if (!/^\d{4}-\d{2}-\d{2}$/.test(d) || !(diff >= -3 && diff <= 7)) d = today;
        const hdr = { headers: { "x-apisports-key": env.API_FOOTBALL_KEY } };
        const reqs = [apif(env, `fixtures?date=${d}&timezone=Europe/London`, d === today ? 90 : 900)];
        if (d === today) reqs.push(apif(env, "fixtures?live=all&timezone=Europe/London", 30));
        const rs = await Promise.all(reqs);
        if (!rs[0].ok) return json({ ts: Date.now(), date: d, matches: [], error: "upstream " + rs[0].status }, cors, 10);
        const day = (await rs[0].json()).response || [];
        const live = rs[1] && rs[1].ok ? (await rs[1].json()).response || [] : [];
        const compact = (f) => {
          const o = {
            id: f.fixture.id, lg: f.league.id, ln: f.league.name, cn: f.league.country, ko: f.fixture.date,
            home: f.teams.home.name, away: f.teams.away.name, hid: f.teams.home.id, aid: f.teams.away.id, cf: f.league.flag,
            hg: f.goals.home, ag: f.goals.away, st: f.fixture.status.short, el: f.fixture.status.elapsed, ex: f.fixture.status.extra,
          };
          const ev = (f.events || []).filter((e) => e.type === "Goal" || (e.type === "Card" && e.detail !== "Second Yellow card" ? true : e.type === "Card"));
          if (ev.length) o.ev = ev.map((e) => ({ m: e.time.elapsed, x: e.time.extra, s: e.team && e.team.id === f.teams.home.id ? "h" : "a", t: e.type, d: e.detail, p: e.player && e.player.name }));
          return o;
        };
        const map = new Map();
        for (const f of day) map.set(f.fixture.id, compact(f));
        for (const f of live) map.set(f.fixture.id, compact(f));
        return json({ ts: Date.now(), date: d, matches: [...map.values()] }, cors, 30);
      }
      const all = q.get("scope") === "all";
      const r = await apif(env, `fixtures?live=${all ? LEAGUES_ALL : LEAGUES}`, 30);
      if (!r.ok) return json({ ts: Date.now(), matches: [], error: r.status === 429 ? "busy, retrying" : "upstream " + r.status, detail: (await r.text()).slice(0, 300) }, cors, 10);
      const j = await r.json();
      const matches = (j.response || []).map((f) => ({
        id: f.fixture.id,
        hid: f.teams.home.id,
        lg: f.league.id,
        home: f.teams.home.name,
        away: f.teams.away.name,
        hg: f.goals.home ?? 0,
        ag: f.goals.away ?? 0,
        st: f.fixture.status.short,
        el: f.fixture.status.elapsed,
        ex: f.fixture.status.extra,
        ev: (f.events || [])
          .filter((e) => e.type === "Goal" || e.type === "Card")
          .map((e) => ({
            m: e.time.elapsed,
            x: e.time.extra,
            s: e.team && e.team.id === f.teams.home.id ? "h" : "a",
            t: e.type,
            d: e.detail,
            p: e.player && e.player.name,
          })),
      }));
      // Live statistics for all matches in play: one extra call, cached for 60 seconds.
      const ids = matches.map((m) => m.id).sort((a, b) => a - b).slice(0, 60);
      const chunks = [];
      for (let i = 0; i < ids.length; i += 20) chunks.push(ids.slice(i, i + 20));
      const byId = Object.fromEntries(matches.map((m) => [m.id, m]));
      const dbg = { bulk: [], single: 0 };
      await Promise.all(chunks.map(async (chunk) => {
        try {
          const r2 = await apif(env, `fixtures?ids=${chunk.join("-")}`, 60);
          dbg.bulk.push(r2.status);
          if (r2.status === 429) dbg.limited = true;
          if (r2.ok) {
            const j2 = await r2.json();
            for (const f of j2.response || []) {
              const m = byId[f.fixture.id];
              if (m) m.sx = statsOf(f);
            }
          }
        } catch (e) { dbg.bulk.push("err"); }
      }));
      // Fallback: for any match the bulk call gave no statistics for, ask the statistics endpoint for that match alone.
      const missing = dbg.limited ? [] : matches.filter((m) => !m.sx).slice(0, 4);
      await Promise.all(missing.map(async (m) => {
        try {
          const r3 = await apif(env, `fixtures/statistics?fixture=${m.id}`, 60);
          dbg.single++;
          if (r3.ok) {
            const j3 = await r3.json();
            m.sx = statsOf({ teams: { home: { id: m.hid } }, statistics: j3.response || [] });
          }
        } catch (e) { /* statistics are optional */ }
      }));
      dbg.stats = matches.filter((m) => m.sx).length;
      return json({ ts: Date.now(), matches, dbg }, cors, 20);
    } catch (e) {
      return json({ ts: Date.now(), matches: [], error: "failed" }, cors, 10);
    }
  },
};

function json(body, cors, maxAge) {
  return new Response(JSON.stringify(body), {
    headers: { ...cors, "Content-Type": "application/json", "Cache-Control": `public, max-age=${maxAge}` },
  });
}
