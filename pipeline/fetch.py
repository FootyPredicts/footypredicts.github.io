# -*- coding: utf-8 -*-
"""
Download and cache data for one league from API-Football.

Per league, in data/<league>/:
  fixtures_<season>.json   every fixture of the season (score, half-time, referee, status)
  match_stats.json         per finished match: shots, cards, corners... (home/away)
  players_<season>.json    season stats of every player in the league

Past seasons are downloaded once. Each run refreshes the current season's
fixtures and players, and fetches statistics only for newly finished matches
(20 matches per API call).
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from .config import API_BASE, API_MIN_INTERVAL, DATA_DIR, PAST_SEASONS, current_season

FINISHED = {"FT", "AET", "PEN"}
_last_call = [0.0]
_interval = [API_MIN_INTERVAL]


def set_interval(seconds):
    _interval[0] = seconds
CALLS = [0]


class ApiError(RuntimeError):
    pass


def api_get(path, params, key, retries=5):
    """GET with spacing between calls and back-off on rate limits."""
    url = f"{API_BASE}/{path}"
    for attempt in range(retries):
        wait = _interval[0] - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        CALLS[0] += 1
        try:
            r = requests.get(url, params=params, headers={"x-apisports-key": key}, timeout=40)
        except requests.RequestException as e:
            time.sleep(2 * (attempt + 1))
            last = str(e)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (attempt + 1))
            last = f"HTTP {r.status_code}"
            continue
        data = r.json()
        errs = data.get("errors")
        if errs:
            text = json.dumps(errs)
            if "rateLimit" in text or "Too many" in text:
                time.sleep(10 * (attempt + 1))
                last = text
                continue
            raise ApiError(f"{path} {params}: {text}")
        return data
    raise ApiError(f"{path} {params}: gave up ({last})")


# ---------------------------------------------------------------- helpers

def _dir(league):
    d = os.path.join(DATA_DIR, league)
    os.makedirs(d, exist_ok=True)
    return d


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def _save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _short_ref(name):
    """'Michael Oliver, England' -> 'M. Oliver'."""
    name = (name or "").split(",")[0].strip()
    parts = name.split()
    if len(parts) >= 2 and not parts[0].endswith("."):
        return f"{parts[0][0]}. {' '.join(parts[1:])}"
    return name


def _flat_fixture(f):
    fx, t, g = f["fixture"], f["teams"], f["goals"]
    ht = (f.get("score") or {}).get("halftime") or {}
    return {
        "id": fx["id"],
        "date": fx["date"],
        "status": (fx.get("status") or {}).get("short"),
        "referee": _short_ref(fx.get("referee")),
        "round": (f.get("league") or {}).get("round"),
        "home_id": t["home"]["id"], "home": t["home"]["name"],
        "away_id": t["away"]["id"], "away": t["away"]["name"],
        "hg": g.get("home"), "ag": g.get("away"),
        "ht_h": ht.get("home"), "ht_a": ht.get("away"),
    }


def _flat_stats(f):
    """{'home': {'Yellow Cards': 2, ...}, 'away': {...}} or None."""
    stats = f.get("statistics") or []
    if len(stats) < 2:
        return None
    home_id = f["teams"]["home"]["id"]
    out = {}
    for side in stats:
        which = "home" if side["team"]["id"] == home_id else "away"
        vals = {}
        for s in side.get("statistics") or []:
            v = s.get("value")
            if isinstance(v, str) and v.endswith("%"):
                v = v[:-1]
            try:
                v = float(v) if v is not None else 0.0
            except ValueError:
                v = None
            vals[s["type"]] = v
        out[which] = vals
    return out if "home" in out and "away" in out else None


# ---------------------------------------------------------------- steps

def fetch_fixtures(league, league_id, key):
    d = _dir(league)
    cur = current_season()
    for season in range(cur - PAST_SEASONS, cur + 1):
        path = os.path.join(d, f"fixtures_{season}.json")
        done = _load(path, None)
        # past seasons: download once (unless the saved copy is incomplete)
        if season < cur and done and all(x["status"] in FINISHED | {"PST", "CANC", "ABD", "AWD", "WO"} for x in done):
            continue
        data = api_get("fixtures", {"league": league_id, "season": season}, key)
        _save(path, [_flat_fixture(f) for f in data.get("response", [])])


def _flat_events(f):
    """Who scored and who was booked (player ids + names) - used to check
    player predictions afterwards."""
    goals, cards = [], []
    for e in f.get("events") or []:
        pl = e.get("player") or {}
        team = (e.get("team") or {}).get("name")
        item = {"id": pl.get("id"), "name": pl.get("name"), "team": team,
                "minute": (e.get("time") or {}).get("elapsed")}
        if e.get("type") == "Goal" and e.get("detail") not in ("Missed Penalty",) and "Own" not in (e.get("detail") or ""):
            goals.append(item)
        elif e.get("type") == "Card":
            cards.append(dict(item, card=e.get("detail")))
    return {"goals": goals, "cards": cards}


def fetch_match_stats(league, key, max_tries=3, events_days=21):
    d = _dir(league)
    stats = _load(os.path.join(d, "match_stats.json"), {})
    tries = _load(os.path.join(d, "stats_attempts.json"), {})
    events = _load(os.path.join(d, "match_events.json"), {})
    finished, recent = [], set()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=events_days)).isoformat()
    for p in sorted(f for f in os.listdir(d) if f.startswith("fixtures_")):
        for x in _load(os.path.join(d, p), []):
            if x["status"] in FINISHED:
                finished.append(x["id"])
                if x["date"] >= cutoff:
                    recent.add(x["id"])
    todo = [i for i in finished if (str(i) not in stats and tries.get(str(i), 0) < max_tries)
            or (i in recent and str(i) not in events)]
    for k in range(0, len(todo), 20):
        batch = todo[k:k + 20]
        data = api_get("fixtures", {"ids": "-".join(map(str, batch))}, key)
        got = set()
        for f in data.get("response", []):
            if f.get("events") is not None:
                events[str(f["fixture"]["id"])] = _flat_events(f)
            s = _flat_stats(f)
            if s:
                stats[str(f["fixture"]["id"])] = s
                got.add(f["fixture"]["id"])
        for i in batch:
            if i not in got and str(i) not in stats:
                tries[str(i)] = tries.get(str(i), 0) + 1
        if k % 200 == 0:   # save progress regularly
            _save(os.path.join(d, "match_stats.json"), stats)
            _save(os.path.join(d, "stats_attempts.json"), tries)
    _save(os.path.join(d, "match_stats.json"), stats)
    _save(os.path.join(d, "stats_attempts.json"), tries)
    _save(os.path.join(d, "match_events.json"), events)
    return len(todo)


def fetch_players(league, league_id, key):
    d = _dir(league)
    season = current_season()
    rows, page, total = {}, 1, 1
    while page <= total:
        data = api_get("players", {"league": league_id, "season": season, "page": page}, key)
        total = (data.get("paging") or {}).get("total", 1) or 1
        for p in data.get("response", []):
            info = p.get("player") or {}
            for st in p.get("statistics") or []:
                if (st.get("league") or {}).get("id") not in (league_id, None):
                    continue
                team = (st.get("team") or {}).get("name")
                if not team:
                    continue
                g, sh, gl, cd = (st.get(x) or {} for x in ("games", "shots", "goals", "cards"))
                k = f"{info.get('id')}|{team}"
                r = rows.setdefault(k, {
                    "id": info.get("id"), "name": info.get("name"), "team": team,
                    "position": g.get("position") or "", "apps": 0, "minutes": 0,
                    "goals": 0, "shots": 0, "sot": 0, "yellow": 0, "red": 0,
                })
                r["apps"] += g.get("appearences") or g.get("appearances") or 0
                r["minutes"] += g.get("minutes") or 0
                r["goals"] += gl.get("total") or 0
                r["shots"] += sh.get("total") or 0
                r["sot"] += sh.get("on") or 0
                r["yellow"] += (cd.get("yellow") or 0) + (cd.get("yellowred") or 0)
                r["red"] += cd.get("red") or 0
        page += 1
    if rows:
        _save(os.path.join(d, f"players_{season}.json"), list(rows.values()))
    return len(rows)


ODDS_MARKETS = re.compile(
    r"^(match winner|goals over/under|both teams score|cards over/under)$|scorer|booked|player.*card",
    re.I)


# bookmakers whose own prices are kept (for the site's "choose your bookmaker" switch)
UK_BOOKS = {"Bet365", "William Hill", "BetVictor", "Betfair"}


def fetch_odds(league, key, n_fixtures=12):
    """Best price (and which bookmaker) for every selection the site shows,
    for the next upcoming fixtures. One API call per fixture."""
    d = _dir(league)
    cur = current_season()
    upcoming = [x for x in _load(os.path.join(d, f"fixtures_{cur}.json"), []) if x["status"] in ("NS", "TBD")]
    upcoming.sort(key=lambda x: x["date"])
    odds = {}
    book_seen = {}   # bookmaker -> number of fixtures it priced (diagnostic)
    for fx in upcoming[:n_fixtures]:
        try:
            data = api_get("odds", {"fixture": fx["id"]}, key)
        except ApiError as e:
            print(f"  odds unavailable for {fx['home']} v {fx['away']}: {e}")
            continue
        best, books = {}, {}
        for item in data.get("response", []):
            for bk in item.get("bookmakers") or []:
                book_seen.setdefault(bk.get("name"), set()).add(fx["id"])
                for bet in bk.get("bets") or []:
                    mname = (bet.get("name") or "").strip()
                    if not ODDS_MARKETS.search(mname):
                        continue
                    for v in bet.get("values") or []:
                        try:
                            odd = float(v.get("odd"))
                        except (TypeError, ValueError):
                            continue
                        sel = str(v.get("value")).strip()
                        if bk.get("name") in UK_BOOKS and odd > 1.0:
                            books.setdefault(mname, {}).setdefault(sel, {})[bk.get("name")] = odd
                        cur_best = best.setdefault(mname, {}).get(sel)
                        if odd > 1.0 and (cur_best is None or odd > cur_best["odd"]):
                            best[mname][sel] = {"odd": odd, "bookie": bk.get("name")}
        if best:
            odds[str(fx["id"])] = {"updated": datetime.now(timezone.utc).isoformat(), "markets": best, "books": books}
    _save(os.path.join(d, "odds.json"), odds)
    # keep the latest pre-kick-off 1X2 prices of every fixture, to test a bookmaker blend later
    hist_path = os.path.join(d, "odds_history.json")
    hist = _load(hist_path, {})
    for fid, v in odds.items():
        mw = (v.get("books") or {}).get("Match Winner")
        if mw:
            hist[fid] = {"Match Winner": mw}
    _save(hist_path, hist)
    _save(os.path.join(d, "odds_bookmakers.json"),
          {"checked_fixtures": min(n_fixtures, len(upcoming)),
           "priced_fixtures_by_bookmaker": {k: len(v) for k, v in sorted(book_seen.items(), key=lambda kv: -len(kv[1]))}})
    return len(odds)


def fetch_injuries(league, key, n_fixtures=12):
    """Injured / suspended / doubtful players for the next upcoming fixtures
    (one API call per fixture) -> injuries.json keyed by fixture id."""
    d = _dir(league)
    cur = current_season()
    upcoming = [x for x in _load(os.path.join(d, f"fixtures_{cur}.json"), []) if x["status"] in ("NS", "TBD")]
    upcoming.sort(key=lambda x: x["date"])
    out = {}
    for fx in upcoming[:n_fixtures]:
        try:
            data = api_get("injuries", {"fixture": fx["id"]}, key)
        except ApiError as e:
            print(f"  injuries unavailable for {fx['home']} v {fx['away']}: {e}")
            continue
        seen, rows = set(), []
        for item in data.get("response", []):
            pl, tm = item.get("player") or {}, item.get("team") or {}
            if pl.get("id") is None or (pl["id"], tm.get("name")) in seen:
                continue
            seen.add((pl["id"], tm.get("name")))
            rows.append({"id": pl["id"], "name": pl.get("name"), "team": tm.get("name"),
                         "type": pl.get("type") or "", "reason": pl.get("reason") or ""})
        out[str(fx["id"])] = {"updated": datetime.now(timezone.utc).isoformat(), "players": rows}
    _save(os.path.join(d, "injuries.json"), out)
    return len(out)


def update_league(league, league_id, key):
    fetch_fixtures(league, league_id, key)
    n = fetch_match_stats(league, key)
    p = fetch_players(league, league_id, key)
    try:
        o = fetch_odds(league, key)
        print(f"  odds for {o} upcoming fixtures")
    except Exception as e:  # odds are optional - never stop the predictions
        print(f"  odds skipped: {e}")
    try:
        i = fetch_injuries(league, key)
        print(f"  injury lists for {i} upcoming fixtures")
    except Exception as e:  # injuries are optional - never stop the predictions
        print(f"  injuries skipped: {e}")
    return n, p
