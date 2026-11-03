# -*- coding: utf-8 -*-
"""
Recent team-news headlines for every club with a match in the next few days.

Source: the GDELT DOC API (free and open; it indexes news articles from around the world). We keep only the
headline, the publisher's name and the link, and the site shows them as links to the original article.
No article text is copied.  Writes data/team_news.json:  {team: [{"t": title, "u": url, "s": source, "d": "YYYY-MM-DD HH:MM"}]}
Usage: python -m pipeline.news
"""
import glob
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from .config import DATA_DIR

API = "https://api.gdeltproject.org/api/v2/doc/doc"
TOPICS = '(injury OR injured OR "team news" OR "ruled out" OR suspended OR doubt OR "return" OR lineup OR "starting XI" OR manager OR press conference)'
PER_TEAM = 4
DAYS_AHEAD = 4
PAUSE = 5.5          # GDELT asks for at most one request every 5 seconds
USER_AGENT = "FootyPredicts news fetcher (+https://footypredicts.com)"
# publishers that are mostly betting tips or scraped copies: leave out
BLOCK = ("bet", "odds", "casino", "gambl", "tips", "poker", "prediction", "msn.com", "yahoo.com/news/amp")


def teams_to_cover():
    now = datetime.now(timezone.utc)
    out = set()
    for path in glob.glob(os.path.join(DATA_DIR, "site", "*.json")):
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        for f in d.get("fixtures", []):
            ko = datetime.fromisoformat(f["kickoff"]).replace(tzinfo=timezone.utc)
            if now - timedelta(hours=3) <= ko <= now + timedelta(days=DAYS_AHEAD):
                out.update((f["home"], f["away"]))
    return sorted(out)


def clean_title(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    return t


def fetch_team(team, session):
    q = f'"{team}" football {TOPICS} sourcelang:eng'
    params = {"query": q, "mode": "artlist", "maxrecords": 25, "format": "json", "timespan": "3d", "sort": "datedesc"}
    for attempt in range(3):
        try:
            r = session.get(API, params=params, timeout=40)
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        if r.status_code != 200 or not r.text.strip().startswith("{"):
            return []
        try:
            arts = r.json().get("articles", [])
        except ValueError:
            return []
        items, seen = [], set()
        key = re.sub(r"[^a-z]", "", team.lower())
        for a in arts:
            url, title = a.get("url", ""), clean_title(a.get("title"))
            host = urlparse(url).netloc.lower()
            if not url.startswith(("http://", "https://")) or not title or len(title) < 20:
                continue
            if any(b in host or b in url.lower() for b in BLOCK):
                continue
            short = re.sub(r"[^a-z]", "", title.lower())
            if key[:6] not in short:       # the club must be named in the headline
                continue
            if short[:40] in seen:
                continue
            seen.add(short[:40])
            d = a.get("seendate", "")  # 20261103T061500Z
            try:
                when = datetime.strptime(d, "%Y%m%dT%H%M%SZ").strftime("%Y-%m-%d %H:%M")
            except ValueError:
                when = ""
            items.append({"t": title, "u": url, "s": a.get("domain") or host.replace("www.", ""), "d": when})
            if len(items) >= PER_TEAM:
                break
        return items
    return []


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
            old = json.load(fh)
    except (OSError, ValueError):
        pass
    # keep what we had for a club if this run found nothing (e.g. a rate-limit hiccup)
    merged = {t: (out.get(t) or old.get(t) or []) for t in teams}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(), "teams": merged}, fh, ensure_ascii=False, indent=1)
    print(f"{sum(1 for v in merged.values() if v)} of {len(teams)} clubs have headlines")


if __name__ == "__main__":
    main()
