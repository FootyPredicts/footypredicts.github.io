import re, sys, requests, xml.etree.ElementTree as ET
from urllib.parse import quote
UA = {"User-Agent": "FootyPredicts feed test (+https://footypredicts.com)"}
TEAMS = {"Liverpool": "liverpool", "Arsenal": "arsenal", "Sunderland": "sunderland", "Brighton": "brighton-and-hove-albion", "Hull City": "hull-city", "Barnsley": "barnsley"}
def items(url):
    try:
        r = requests.get(url, headers=UA, timeout=25)
    except Exception as e:
        return None, str(e)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        root = ET.fromstring(r.content)
    except Exception as e:
        return None, "parse " + str(e)
    out = []
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip(); d = (it.findtext("pubDate") or "")[:25]; s = it.findtext("source") or ""
        out.append((d, t, s))
    return out, ""
for team, slug in TEAMS.items():
    print("=" * 60, team)
    for label, url in (("BBC", f"https://feeds.bbci.co.uk/sport/football/teams/{slug}/rss.xml"),
                       ("GoogleNews", f"https://news.google.com/rss/search?q={quote(team + ' FC (injury OR transfer OR ruled out OR team news)')}+when:7d&hl=en-GB&gl=GB&ceid=GB:en")):
        its, err = items(url)
        print(f"-- {label}: {'ERROR ' + err if its is None else str(len(its)) + ' items'}")
        for d, t, s in (its or [])[:6]:
            print("   ", d, "|", t[:110], "|", s)
