"""Starting line-ups.  `python -m pipeline.lineups live` saves the line-ups of matches
kicking off in the next 100 minutes (they are published about an hour before);
`python -m pipeline.lineups backfill [days]` fetches them for finished matches.
Writes data/<league>/lineups.json  {fixture id: {home: {...}, away: {...}}}."""
import os
import sys
from datetime import datetime, timedelta, timezone

import load_env  # noqa: F401
from . import fetch
from .config import LEAGUES, current_season
from .fetch import ApiError, api_get, _dir, _load, _save

FINISHED = ("FT", "AET", "PEN")


def _parse(data, fx):
    out = {}
    for item in data.get("response", []):
        side = "home" if item["team"]["id"] == fx["home_id"] else "away" if item["team"]["id"] == fx["away_id"] else None
        if not side:
            continue
        out[side] = {"formation": item.get("formation"),
                     "xi": [{"id": p["player"]["id"], "name": p["player"]["name"], "pos": p["player"].get("pos")}
                            for p in item.get("startXI") or []],
                     "subs": [p["player"]["id"] for p in item.get("substitutes") or []]}
    return out if len(out) == 2 and all(len(v["xi"]) >= 11 for v in out.values()) else None


def run(mode, days=150):
    key = os.environ["API_FOOTBALL_KEY"]
    fetch.set_interval(float(os.environ.get("API_FOOTBALL_MIN_INTERVAL", "0.25")))
    now = datetime.now(timezone.utc)
    saved = 0
    for league in LEAGUES:
        d = _dir(league)
        path = os.path.join(d, "lineups.json")
        out = _load(path, {})
        fx = _load(os.path.join(d, f"fixtures_{current_season()}.json"), []) + \
            _load(os.path.join(d, f"fixtures_{current_season() - 1}.json"), [])
        if mode == "live":
            def due(x):
                t = datetime.fromisoformat(x["date"].replace("Z", "+00:00"))
                return x["status"] in ("NS", "TBD", "1H") and timedelta(minutes=-10) <= t - now <= timedelta(minutes=100)
            todo = [x for x in fx if due(x) and str(x["id"]) not in out]
        else:
            cutoff = (now - timedelta(days=days)).isoformat()
            todo = [x for x in fx if x["status"] in FINISHED and x["date"] >= cutoff and str(x["id"]) not in out]
        for n, x in enumerate(todo, 1):
            try:
                data = api_get("fixtures/lineups", {"fixture": x["id"]}, key)
            except ApiError:
                continue
            lu = _parse(data, x)
            if lu:
                lu["saved"] = now.isoformat()
                out[str(x["id"])] = lu
                saved += 1
            if mode != "live" and n % 100 == 0:
                _save(path, out)
        if todo:
            _save(path, out)
        print(f"{league}: {len(todo)} tried", flush=True)
    print(f"lineups saved: {saved}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "live", int(sys.argv[2]) if len(sys.argv) > 2 else 150)
