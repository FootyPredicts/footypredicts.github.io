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

export default {
  async scheduled(event, env, ctx) {
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
      return new Response(null, { headers: { ...cors, "Access-Control-Allow-Methods": "GET", "Access-Control-Max-Age": "86400" } });
    }
    if (request.method !== "GET") return new Response("Method not allowed", { status: 405, headers: cors });
    if (!env.API_FOOTBALL_KEY) return json({ ts: Date.now(), matches: [], error: "not configured" }, cors, 10);

    try {
      // The API call itself is cached at Cloudflare's edge for 30 seconds.
      const q = new URL(request.url).searchParams;
      const want = (q.get("ids") || "").split("-").filter((x) => /^\d+$/.test(x)).slice(0, 20);
      if (want.length) {
        // Final scores for matches that have just left the live feed.
        const rf = await fetch(`https://v3.football.api-sports.io/fixtures?ids=${want.join("-")}`, {
          headers: { "x-apisports-key": env.API_FOOTBALL_KEY },
          cf: { cacheTtl: 60, cacheEverything: true },
        });
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
        for (const season of [cur, cur - 1]) {
          const rs = await fetch(`https://v3.football.api-sports.io/standings?league=${sid}&season=${season}`, {
            headers: { "x-apisports-key": env.API_FOOTBALL_KEY },
            cf: { cacheTtl: 600, cacheEverything: true },
          });
          if (!rs.ok) return json({ ts: Date.now(), groups: [], error: "upstream " + rs.status }, cors, 10);
          const lg = (((await rs.json()).response || [])[0] || {}).league;
          if (lg && lg.standings && lg.standings.length) {
            const groups = lg.standings.map((g) => ({
              name: (g[0] && g[0].group) || "",
              rows: g.map((x) => ({ r: x.rank, n: x.team.name, p: x.all.played, w: x.all.win, d: x.all.draw, l: x.all.lose, gf: x.all.goals.for, ga: x.all.goals.against, pts: x.points, f: x.form || "" })),
            }));
            return json({ ts: Date.now(), name: lg.name, season, groups }, cors, 300);
          }
        }
        return json({ ts: Date.now(), groups: [] }, cors, 60);
      }
      if (q.get("scope") === "world") {
        // Every match in the world for one day (UK dates), with live matches overlaid. Cached, so visitors cost nothing extra.
        const today = new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/London" });
        let d = q.get("date") || today;
        const diff = (Date.parse(d) - Date.parse(today)) / 864e5;
        if (!/^\d{4}-\d{2}-\d{2}$/.test(d) || !(diff >= -3 && diff <= 7)) d = today;
        const hdr = { headers: { "x-apisports-key": env.API_FOOTBALL_KEY } };
        const reqs = [fetch(`https://v3.football.api-sports.io/fixtures?date=${d}&timezone=Europe/London`, { ...hdr, cf: { cacheTtl: d === today ? 90 : 900, cacheEverything: true } })];
        if (d === today) reqs.push(fetch("https://v3.football.api-sports.io/fixtures?live=all&timezone=Europe/London", { ...hdr, cf: { cacheTtl: 30, cacheEverything: true } }));
        const rs = await Promise.all(reqs);
        if (!rs[0].ok) return json({ ts: Date.now(), date: d, matches: [], error: "upstream " + rs[0].status }, cors, 10);
        const day = (await rs[0].json()).response || [];
        const live = rs[1] && rs[1].ok ? (await rs[1].json()).response || [] : [];
        const compact = (f) => {
          const o = {
            id: f.fixture.id, lg: f.league.id, ln: f.league.name, cn: f.league.country, ko: f.fixture.date,
            home: f.teams.home.name, away: f.teams.away.name, hid: f.teams.home.id,
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
      const r = await fetch(`https://v3.football.api-sports.io/fixtures?live=${all ? LEAGUES_ALL : LEAGUES}`, {
        headers: { "x-apisports-key": env.API_FOOTBALL_KEY },
        cf: { cacheTtl: 30, cacheEverything: true },
      });
      if (!r.ok) return json({ ts: Date.now(), matches: [], error: "upstream " + r.status }, cors, 10);
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
          const r2 = await fetch(`https://v3.football.api-sports.io/fixtures?ids=${chunk.join("-")}`, {
            headers: { "x-apisports-key": env.API_FOOTBALL_KEY },
            cf: { cacheTtl: 60, cacheEverything: true },
          });
          dbg.bulk.push(r2.status);
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
      const missing = matches.filter((m) => !m.sx).slice(0, 12);
      await Promise.all(missing.map(async (m) => {
        try {
          const r3 = await fetch(`https://v3.football.api-sports.io/fixtures/statistics?fixture=${m.id}`, {
            headers: { "x-apisports-key": env.API_FOOTBALL_KEY },
            cf: { cacheTtl: 60, cacheEverything: true },
          });
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
