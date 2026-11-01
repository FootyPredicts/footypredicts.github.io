"""Shirt numbers from each club's squad list (about 100 API calls, refreshed every few days).
Writes data/<league>/squads.json as {player_id: shirt_number}.  Usage: python -m pipeline.squads [--force]"""
import os
import sys
import time

import load_env  # noqa: F401
from . import fetch
from .config import LEAGUES, current_season
from .fetch import ApiError, api_get, _dir, _load, _save

MAX_AGE_DAYS = 4


def main(force=False):
    key = os.environ["API_FOOTBALL_KEY"]
    fetch.set_interval(float(os.environ.get("API_FOOTBALL_MIN_INTERVAL", "0.25")))
    for league, (_name, league_id, _c, _s) in LEAGUES.items():
        path = os.path.join(_dir(league), "squads.json")
        old = _load(path, {})
        if not force and old and time.time() - os.path.getmtime(path) < MAX_AGE_DAYS * 86400:
            print(f"{league}: squad numbers are recent, skipping")
            continue
        try:
            teams = api_get("teams", {"league": league_id, "season": current_season()}, key).get("response", [])
        except ApiError as e:
            print(f"{league}: could not list teams ({e})")
            continue
        out = dict(old)
        for t in teams:
            tid = t["team"]["id"]
            try:
                resp = api_get("players/squads", {"team": tid}, key).get("response", [])
            except ApiError:
                continue
            for entry in resp:
                for p in entry.get("players", []):
                    if p.get("id") and p.get("number") is not None:
                        out[str(p["id"])] = p["number"]
        _save(path, out)
        print(f"{league}: {len(out)} shirt numbers", flush=True)


if __name__ == "__main__":
    main("--force" in sys.argv)
