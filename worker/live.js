// Cloudflare Worker: live scores relay for FootyPredicts.
// Keeps the API-Football key secret and caches the answer for 30 seconds,
// so any number of visitors cost at most ~2 API calls a minute.
// Secret needed: API_FOOTBALL_KEY (Worker -> Settings -> Variables and Secrets).

const LEAGUES = "39-140-78-135-61"; // Premier League, La Liga, Bundesliga, Serie A, Ligue 1
const ALLOWED = [
  "https://footypredicts.com",
  "https://www.footypredicts.com",
  "https://footypredicts.github.io",
];

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
      const r = await fetch(`https://v3.football.api-sports.io/fixtures?live=${LEAGUES}`, {
        headers: { "x-apisports-key": env.API_FOOTBALL_KEY },
        cf: { cacheTtl: 30, cacheEverything: true },
      });
      if (!r.ok) return json({ ts: Date.now(), matches: [], error: "upstream " + r.status }, cors, 10);
      const j = await r.json();
      const matches = (j.response || []).map((f) => ({
        id: f.fixture.id,
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
      return json({ ts: Date.now(), matches }, cors, 20);
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
