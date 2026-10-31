"""Fixtures from European and domestic cup competitions, so fixture congestion
(rest days, midweek European ties) can be measured.
Writes data/other_competitions.json.  Usage: python -m pipeline.fetch_other_competitions"""
import os
import load_env  # noqa: F401
from . import fetch
from .config import DATA_DIR, current_season
from .fetch import api_get, ApiError, _flat_fixture, _save

COMPETITIONS = {
    "Champions League": 2, "Europa League": 3, "Conference League": 848,
    "FA Cup": 45, "League Cup": 48, "Copa del Rey": 143,
    "DFB Pokal": 81, "Coppa Italia": 137, "Coupe de France": 66,
}


def main():
    key = os.environ["API_FOOTBALL_KEY"]
    fetch.set_interval(float(os.environ.get("API_FOOTBALL_MIN_INTERVAL", "0.25")))
    cur = current_season()
    out = []
    for name, cid in COMPETITIONS.items():
        for season in (cur - 1, cur):
            try:
                data = api_get("fixtures", {"league": cid, "season": season}, key)
            except ApiError as e:
                print(f"{name} {season}: {e}")
                continue
            rows = [dict(_flat_fixture(f), competition=name) for f in data.get("response", [])]
            for r in rows:
                for k in ("referee", "ht_h", "ht_a"):
                    r.pop(k, None)
            out += rows
            print(f"{name} {season}: {len(rows)} fixtures", flush=True)
    _save(os.path.join(DATA_DIR, "other_competitions.json"), out)


if __name__ == "__main__":
    main()
