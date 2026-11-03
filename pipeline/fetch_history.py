"""Match results back to 2021 for the European competitions, other European leagues and the big five.
Results only (no players or stats), about one API call per league per season.
Writes data/history/<key>_<season>.json.  Past seasons are fetched once; the current season is refreshed each run.
Usage: python -m pipeline.fetch_history [--from=2021]"""
import os
import sys

import load_env  # noqa: F401
from . import fetch
from .config import DATA_DIR, current_season
from .fetch import ApiError, api_get, _save

# key: API-Football league id
COMPETITIONS = {
    "champions-league": 2, "europa-league": 3, "conference-league": 848,
}
LEAGUES = {
    "premier-league": 39, "la-liga": 140, "bundesliga": 78, "serie-a": 135, "ligue-1": 61,
    "portugal": 94, "netherlands": 88, "belgium": 144, "turkey": 203, "scotland": 179, "greece": 197,
    "austria": 218, "switzerland": 207, "czechia": 345, "ukraine": 333, "denmark": 119, "norway": 103,
    "poland": 106, "croatia": 210, "serbia": 286, "israel": 383, "sweden": 113, "hungary": 271, "romania": 283,
    "cyprus": 318, "bulgaria": 172, "slovakia": 332, "slovenia": 373,
}
FIELDS = ("id", "date", "status", "round", "home_id", "home", "away_id", "away", "hg", "ag")


def flat(f):
    t, g = f["teams"], f["goals"]
    return {"id": f["fixture"]["id"], "date": f["fixture"]["date"],
            "status": (f["fixture"].get("status") or {}).get("short"),
            "round": (f.get("league") or {}).get("round"),
            "home_id": t["home"]["id"], "home": t["home"]["name"],
            "away_id": t["away"]["id"], "away": t["away"]["name"],
            "hg": g.get("home"), "ag": g.get("away")}


def main(first=2021):
    key = os.environ["API_FOOTBALL_KEY"]
    fetch.set_interval(float(os.environ.get("API_FOOTBALL_MIN_INTERVAL", "0.25")))
    cur = current_season()
    out_dir = os.path.join(DATA_DIR, "history")
    os.makedirs(out_dir, exist_ok=True)
    todo = {**COMPETITIONS, **LEAGUES}
    for name, lid in todo.items():
        got = []
        for season in range(first, cur + 1):
            path = os.path.join(out_dir, f"{name}_{season}.json")
            if os.path.exists(path) and season < cur:
                continue
            try:
                data = api_get("fixtures", {"league": lid, "season": season}, key)
            except ApiError as e:
                print(f"{name} {season}: {e}")
                continue
            rows = [flat(f) for f in data.get("response", [])]
            if not rows:
                print(f"{name} {season}: nothing returned")
                continue
            lg = data["response"][0].get("league", {})
            _save(path, rows)
            done = sum(1 for r in rows if r["status"] in ("FT", "AET", "PEN"))
            got.append(f"{season}:{done}")
            if season == first or season == cur:
                print(f"  {name} ({lid}) -> {lg.get('name')} / {lg.get('country')}", flush=True)
        print(f"{name}: " + (" ".join(got) or "up to date"), flush=True)
    print(f"API calls this run: {fetch.CALLS[0]}")


if __name__ == "__main__":
    first = 2021
    for a in sys.argv[1:]:
        if a.startswith("--from="):
            first = int(a.split("=")[1])
    main(first)
