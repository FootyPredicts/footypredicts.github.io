"""One-off: fetch the injury / suspension lists for finished matches so the
injury weights can be fitted on real results.  Resumable (skips fixtures already
saved).  Usage: python -m pipeline.backfill_injuries [days=400]"""
import os
import sys
from datetime import datetime, timedelta, timezone

import load_env  # noqa: F401
from .config import LEAGUES, current_season
from . import fetch
from .fetch import ApiError, api_get, _dir, _load, _save

FINISHED = ("FT", "AET", "PEN")


def main(days=400):
    key = os.environ["API_FOOTBALL_KEY"]
    fetch.set_interval(float(os.environ.get("API_FOOTBALL_MIN_INTERVAL", "0.25")))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    for league in LEAGUES:
        d = _dir(league)
        path = os.path.join(d, "injuries_history.json")
        out = _load(path, {})
        fx = []
        for season in range(current_season() - 1, current_season() + 1):
            fx += _load(os.path.join(d, f"fixtures_{season}.json"), [])
        todo = [x for x in fx if x["status"] in FINISHED and x["date"] >= cutoff and str(x["id"]) not in out]
        print(f"{league}: {len(todo)} fixtures to fetch ({len(out)} already saved)", flush=True)
        for n, x in enumerate(todo, 1):
            try:
                data = api_get("injuries", {"fixture": x["id"]}, key)
            except ApiError as e:
                print(f"  skip {x['id']}: {e}")
                continue
            seen, rows = set(), []
            for item in data.get("response", []):
                pl, tm = item.get("player") or {}, item.get("team") or {}
                if pl.get("id") is None or (pl["id"], tm.get("name")) in seen:
                    continue
                seen.add((pl["id"], tm.get("name")))
                rows.append({"id": pl["id"], "name": pl.get("name"), "team": tm.get("name"),
                             "type": pl.get("type") or "", "reason": pl.get("reason") or ""})
            out[str(x["id"])] = {"players": rows}
            if n % 100 == 0:
                _save(path, out)
                print(f"  {n}/{len(todo)}", flush=True)
        _save(path, out)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 400)
