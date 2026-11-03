# -*- coding: utf-8 -*-
"""Season stats of every player in the Champions League and Europa League -> data/euro_players.json
(same shape as the domestic players_<season>.json). Usage: python -m pipeline.euro_players"""
import json
import os

from .config import DATA_DIR, current_season
from .fetch import api_get, _save

COMPS = (2, 3)


def main():
    key = os.environ.get("API_FOOTBALL_KEY")
    if not key:
        raise SystemExit("API_FOOTBALL_KEY not set")
    season, rows = current_season(), {}
    for lid in COMPS:
        page, total = 1, 1
        while page <= total:
            data = api_get("players", {"league": lid, "season": season, "page": page}, key)
            total = (data.get("paging") or {}).get("total", 1) or 1
            for p in data.get("response", []):
                info = p.get("player") or {}
                for st in p.get("statistics") or []:
                    if (st.get("league") or {}).get("id") != lid:
                        continue
                    team = (st.get("team") or {}).get("name")
                    if not team:
                        continue
                    g, sh, gl, cd = (st.get(x) or {} for x in ("games", "shots", "goals", "cards"))
                    r = rows.setdefault(f"{info.get('id')}|{team}", {
                        "id": info.get("id"), "name": info.get("name"), "team": team,
                        "position": g.get("position") or "", "apps": 0, "minutes": 0,
                        "goals": 0, "shots": 0, "sot": 0, "yellow": 0, "red": 0})
                    r["apps"] += g.get("appearences") or g.get("appearances") or 0
                    r["minutes"] += g.get("minutes") or 0
                    r["goals"] += gl.get("total") or 0
                    r["shots"] += sh.get("total") or 0
                    r["sot"] += sh.get("on") or 0
                    r["yellow"] += (cd.get("yellow") or 0) + (cd.get("yellowred") or 0)
                    r["red"] += cd.get("red") or 0
            page += 1
    if rows:
        _save(os.path.join(DATA_DIR, "euro_players.json"), list(rows.values()))
    print(f"{len(rows)} player rows")


if __name__ == "__main__":
    main()
