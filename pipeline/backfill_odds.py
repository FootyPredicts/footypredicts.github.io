"""Fetch 1X2 prices (UK bookmakers) for finished matches, if the API still holds them.
Writes data/<league>/odds_history.json.  Usage: python -m pipeline.backfill_odds [days=150]"""
import os
import sys
from datetime import datetime, timedelta, timezone

import load_env  # noqa: F401
from . import fetch
from .config import LEAGUES, current_season
from .fetch import ApiError, api_get, _dir, _load, _save, UK_BOOKS

FINISHED = ("FT", "AET", "PEN")


def main(days=150):
    key = os.environ["API_FOOTBALL_KEY"]
    fetch.set_interval(float(os.environ.get("API_FOOTBALL_MIN_INTERVAL", "0.25")))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    for league in LEAGUES:
        d = _dir(league)
        path = os.path.join(d, "odds_history.json")
        out = _load(path, {})
        fx = _load(os.path.join(d, f"fixtures_{current_season()}.json"), []) + \
            _load(os.path.join(d, f"fixtures_{current_season() - 1}.json"), [])
        todo = [x for x in fx if x["status"] in FINISHED and x["date"] >= cutoff and str(x["id"]) not in out]
        got = 0
        print(f"{league}: {len(todo)} to try", flush=True)
        for n, x in enumerate(todo, 1):
            try:
                data = api_get("odds", {"fixture": x["id"]}, key)
            except ApiError:
                continue
            books = {}
            for item in data.get("response", []):
                for bk in item.get("bookmakers") or []:
                    if bk.get("name") not in UK_BOOKS:
                        continue
                    for bet in bk.get("bets") or []:
                        if (bet.get("name") or "").strip() != "Match Winner":
                            continue
                        for v in bet.get("values") or []:
                            try:
                                books.setdefault(str(v.get("value")).strip(), {})[bk["name"]] = float(v["odd"])
                            except (TypeError, ValueError, KeyError):
                                pass
            out[str(x["id"])] = {"Match Winner": books} if books else {}
            got += bool(books)
            if n % 100 == 0:
                _save(path, out)
                print(f"  {n}/{len(todo)}  with prices: {got}", flush=True)
        _save(path, out)
        print(f"{league}: prices found for {got} of {len(todo)}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
