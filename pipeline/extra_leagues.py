# -*- coding: utf-8 -*-
"""Fixtures and results for leagues that only get club pages and news (no predictions).
Writes data/<slug>/fixtures_<season>.json in the same shape as the main leagues.   python -m pipeline.extra_leagues"""
import json
import os
import sys

from .config import DATA_DIR, EXTRA_LEAGUES, current_season
from .fetch import api_get


def run():
    key = os.environ.get("API_FOOTBALL_KEY", "")
    if not key:
        sys.exit("API_FOOTBALL_KEY is not set")
    season = current_season()
    for slug, (name, lid, country, _kind) in EXTRA_LEAGUES.items():
        data = api_get("fixtures", {"league": lid, "season": season}, key)
        rows = []
        for f in data.get("response", []):
            rows.append({
                "id": f["fixture"]["id"], "date": f["fixture"]["date"], "status": f["fixture"]["status"]["short"],
                "referee": f["fixture"].get("referee"), "round": f["league"].get("round"),
                "home_id": f["teams"]["home"]["id"], "home": f["teams"]["home"]["name"],
                "away_id": f["teams"]["away"]["id"], "away": f["teams"]["away"]["name"],
                "hg": f["goals"]["home"], "ag": f["goals"]["away"],
                "ht_h": f["score"]["halftime"]["home"], "ht_a": f["score"]["halftime"]["away"],
            })
        if not rows:
            print(f"{name}: no fixtures returned, keeping old file")
            continue
        d = os.path.join(DATA_DIR, slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"fixtures_{season}.json"), "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False)
        print(f"{name}: {len(rows)} fixtures")


if __name__ == "__main__":
    run()
