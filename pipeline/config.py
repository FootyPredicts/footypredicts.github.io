# -*- coding: utf-8 -*-
"""Leagues covered by the site, and shared settings."""
import os
from datetime import date

# key: (display name, API-Football league id, country, url slug)
LEAGUES = {
    "premier-league": ("Premier League", 39, "England", "premier-league"),
    "la-liga":        ("La Liga", 140, "Spain", "la-liga"),
    "bundesliga":     ("Bundesliga", 78, "Germany", "bundesliga"),
    "serie-a":        ("Serie A", 135, "Italy", "serie-a"),
    "ligue-1":        ("Ligue 1", 61, "France", "ligue-1"),
}

# Leagues with club pages, news and form only (no predictions): slug -> (name, API-Football league id, country)
EXTRA_LEAGUES = {
    "scottish-premiership": ("Scottish Premiership", 179, "Scotland"),
}

# How many past seasons to keep for the models (besides the current one)
PAST_SEASONS = 2
# How many upcoming fixtures to predict per league
NEXT_FIXTURES = 10

API_BASE = "https://v3.football.api-sports.io"
# Seconds between API calls. Paid plans allow 300+/minute -> 0.25s is safe.
# Set API_FOOTBALL_MIN_INTERVAL=6.5 for the free plan.
API_MIN_INTERVAL = float(os.environ.get("API_FOOTBALL_MIN_INTERVAL", "0.25"))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")


def current_season(today=None):
    """API-Football season = the year the season starts (Aug-May)."""
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1
