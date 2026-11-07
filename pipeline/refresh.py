# -*- coding: utf-8 -*-
"""Matchday refresh: re-fetch injury and suspension lists for upcoming fixtures and re-run the domestic predictions.
Injury lists often appear only a few hours before kick-off, so the once-a-day run can miss them.
Usage: python -m pipeline.refresh"""
import os
import sys
import traceback

from . import fetch, models
from .config import LEAGUES


def main():
    key = os.environ.get("API_FOOTBALL_KEY", "")
    if not key:
        sys.exit("API_FOOTBALL_KEY not set")
    failed = []
    for league, (name, league_id, country, _slug) in LEAGUES.items():
        try:
            n = fetch.fetch_injuries(league, key)
            out = models.predict_league(league, name, country)
            print(f"{name}: injury lists for {n} fixtures, {len(out['fixtures']) if out else 0} predictions")
        except Exception as e:
            traceback.print_exc()
            failed.append(f"{name}: {e}")
    print(f"API calls this run: {fetch.CALLS[0]}")
    if failed:
        print("FAILED: " + "; ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
