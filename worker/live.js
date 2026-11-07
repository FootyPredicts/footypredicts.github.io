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

export default {
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
      const all = new URL(request.url).searchParams.get("scope") === "all";
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
