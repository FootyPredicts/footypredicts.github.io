# -*- coding: utf-8 -*-
"""
Recent news headlines for every club in the leagues we cover.

Source: Google News RSS searches (one per club). We keep only the headline, the publisher's name, the date and the link,
and the site shows them as links to the original article. No article text is copied.
Writes data/team_news.json:  {"updated": ..., "teams": {team: [{"t": title, "u": url, "s": source, "d": "YYYY-MM-DD HH:MM"}]}}
Usage: python -m pipeline.news
"""
import glob
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

from .config import DATA_DIR

FEED = "https://news.google.com/rss/search?q={q}+when:7d&hl=en-GB&gl=GB&ceid=GB:en"
TOPICS = "(injury OR injured OR transfer OR signing OR \"ruled out\" OR \"team news\" OR suspended OR contract OR manager OR \"press conference\")"
PER_TEAM = 8
PAUSE = 0.6
USER_AGENT = "FootyPredicts news fetcher (+https://footypredicts.com)"
# publishers that are mostly betting tips, and other sports / teams that share a club's name
BLOCK_SRC = ("bet", "odds", "casino", "gambl", "tips", "poker", "prediction", "msn", "yahoo finance")
BLOCK_WORDS = (" women", " wsl", "lfc women", "rugby", "hull fc", "hull kr", " u21", " u18", " u19", " u23", "academy", "ladies", "fantasy", "betting", "odds", "prediction")
ALIASES = {
    "Athletic Club": "Athletic Bilbao", "SC Freiburg": "Freiburg", "Stade Brestois 29": "Brest", "Alaves": "Alavés",
    "Slavia Praha": "Slavia Prague", "AEK Athens FC": "AEK Athens", "FK Crvena Zvezda": "Red Star Belgrade",
    "Ferencvarosi TC": "Ferencvaros", "Gornik Zabrze": "Gornik Zabrze", "Hradec Králové": "Hradec Kralove",
    "Lask Linz": "LASK", "Mjallby AIF": "Mjallby", "Hammarby FF": "Hammarby", "FC Midtjylland": "Midtjylland",
    "St. Truiden": "Sint-Truiden", "Universitatea Cluj": "Universitatea Cluj", "Žilina": "Zilina", "Tromso": "Tromsø",
    "Accrington ST": "Accrington Stanley", "Fleetwood Town": "Fleetwood Town", "AZ Alkmaar": "AZ Alkmaar",
    "Hamburger SV": "Hamburg", "Borussia Mönchengladbach": "Borussia Monchengladbach", "FC Augsburg": "Augsburg", "AC Milan": "AC Milan",
}
GENERIC = {"city", "united", "town", "real", "sporting", "athletic", "club", "football", "borussia", "saint", "stade", "olympique", "rovers", "wanderers", "albion", "county", "forest"}


def teams_to_cover():
    out = set()
    for path in glob.glob(os.path.join(DATA_DIR, "*", "fixtures_2026.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                for r in json.load(fh):
                    out.update((r["home"], r["away"]))
        except (OSError, ValueError):
            continue
    return sorted(out)


def keys_for(team):
    """Lower-case strings, any of which must appear in a headline for it to count as about this club."""
    t = team.lower()
    words = [re.sub(r"[^a-z]", "", w) for w in re.split(r"[\s\-]+", t)]
    ks = {t}
    al = ALIASES.get(team)
    if al:
        ks.add(al.lower())
        words += [re.sub(r"[^a-z]", "", w) for w in re.split(r"[\s\-]+", al.lower())]
    ks.update(w for w in words if len(w) >= 4 and w not in GENERIC)
    return ks


def fetch_team(team, session):
    name = ALIASES.get(team, team)
    for q in (quote(f'"{name}" football {TOPICS}'), quote(f'"{name}" football')):
        items = fetch_query(team, q, session)
        if items:
            return items
        time.sleep(PAUSE)
    return []


def fetch_query(team, q, session):
    try:
        r = session.get(FEED.format(q=q), timeout=30)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError):
        return []
    ks, items, seen = keys_for(team), [], set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    for it in root.iter("item"):
        raw = re.sub(r"\s+", " ", it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        title = raw[: -len(src) - 3].strip() if src and raw.endswith(" - " + src) else raw
        url = (it.findtext("link") or "").strip()
        low = " " + title.lower() + " "
        if not url.startswith(("http://", "https://")) or len(title) < 20:
            continue
        if any(b in src.lower() for b in BLOCK_SRC) or any(b in low for b in BLOCK_WORDS):
            continue
        if not any(k in low for k in ks):
            continue
        sig = re.sub(r"[^a-z]", "", title.lower())[:40]
        if sig in seen:
            continue
        seen.add(sig)
        try:
            when = parsedate_to_datetime(it.findtext("pubDate"))
            if when < cutoff:
                continue
            ds = when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            ds = ""
        items.append({"t": title, "u": url, "s": src, "d": ds})
    items.sort(key=lambda x: x["d"], reverse=True)
    return items[:PER_TEAM]


def main():
    teams = teams_to_cover()
    print(f"{len(teams)} clubs to look up")
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    out = {}
    for i, t in enumerate(teams, 1):
        out[t] = fetch_team(t, s)
        print(f"  {i}/{len(teams)} {t}: {len(out[t])}", flush=True)
        time.sleep(PAUSE)
    path = os.path.join(DATA_DIR, "team_news.json")
    old = {}
    try:
        with open(path, encoding="utf-8") as fh:
            old = json.load(fh).get("teams", {})
    except (OSError, ValueError):
        pass
    merged = {t: (out.get(t) or old.get(t) or []) for t in teams}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(), "teams": merged}, fh, ensure_ascii=False, indent=1)
    print(f"{sum(1 for v in merged.values() if v)} of {len(teams)} clubs have headlines")


if __name__ == "__main__":
    main()
