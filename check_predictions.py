# -*- coding: utf-8 -*-
"""
Track record: how did the published predictions do?

For every finished match, takes the LAST prediction that was published
(committed to git) BEFORE kick-off, and compares it with the result, goal
scorers and bookings now saved in data/<league>/. Nothing can be changed
after kick-off because the git history is the record.

    python check_predictions.py            # rebuild data/track_record/

Writes data/track_record/matches.json (one row per match) and summary.json.
Runs automatically in the daily GitHub workflow.
"""
import json
import math
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
LEAGUES = ["premier-league", "la-liga", "bundesliga", "serie-a", "ligue-1"]
FINISHED = {"FT", "AET", "PEN"}
OUT = os.path.join(BASE, "data", "track_record")


def git(*args):
    return subprocess.run(["git", "-C", BASE, *args], capture_output=True, check=True).stdout


def git_json(commit, path):
    try:
        return json.loads(git("show", f"{commit}:{path}"))
    except (subprocess.CalledProcessError, ValueError):
        return None


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def utc(s):
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def published_predictions():
    """fixture id -> (league, commit time, prediction) using the latest
    commit before kick-off."""
    log = git("log", "--format=%H %cI", "--", "data/site").decode().split("\n")
    commits = [(h, utc(t)) for h, t in (l.split() for l in log if l.strip())]
    commits.sort(key=lambda c: c[1])                       # oldest first
    best = {}
    for h, when in commits:
        for lg in LEAGUES:
            d = git_json(h, f"data/site/{lg}.json")
            for f in (d or {}).get("fixtures", []):
                if utc(f["kickoff"]) > when:              # published before kick-off
                    best[f["id"]] = (lg, d.get("name", lg), when, f)   # later commits overwrite
    return best


def event_lists(ev):
    """Who actually scored and who was carded (for the results page)."""
    if not ev:
        return {"goal_events": [], "card_events": []}
    return {
        "goal_events": [{"name": g["name"], "team": g["team"], "minute": g.get("minute")} for g in ev.get("goals", [])],
        "card_events": [{"name": c["name"], "team": c["team"], "minute": c.get("minute"),
                         "card": "Red" if "red" in str(c.get("card", "")).lower() and "yellow" not in str(c.get("card", "")).lower() else "Yellow"}
                        for c in ev.get("cards", [])],
    }


def score_match(lg, name, when, f, result, events, stats, ids_by_name):
    hg, ag = result["hg"], result["ag"]
    actual = "Home" if hg > ag else "Away" if ag > hg else "Draw"
    probs = {"Home": f["home_pct"], "Draw": f["draw_pct"], "Away": f["away_pct"]}
    st = stats.get(str(f["id"]))
    cards = None
    if st:
        cards = sum((st[s].get("Yellow Cards") or 0) + (st[s].get("Red Cards") or 0) for s in ("home", "away"))
    ev = events.get(str(f["id"]))

    def players(kind):
        out = []
        if ev is None:
            return out
        for side, team in (("home", f["home"]), ("away", f["away"])):
            for x in f["players"][side]["scorers" if kind == "goals" else "bookings"]:
                pid = x.get("id") or ids_by_name.get((x["name"], team))
                if pid:
                    out.append({"name": x["name"], "team": team, "p": x["p"],
                                "hit": any(e["id"] == pid for e in ev[kind])})
        return out

    odds = f.get("odds") or {}
    pick_odds = (odds.get({"Home": "home", "Draw": "draw", "Away": "away"}[f["pick"]]) or {}).get("odd")
    return {
        "id": f["id"], "league": lg, "league_name": name, "published": when.isoformat(),
        "kickoff": f["kickoff"], "home": f["home"], "away": f["away"], "score": f"{hg}-{ag}",
        "pick": f["pick"], "pick_pct": probs[f["pick"]], "pick_odds": pick_odds,
        "actual": actual, "correct": f["pick"] == actual, "p_actual": probs[actual],
        "draw_risk": f["pick"] != "Draw" and max(f["home_pct"], f["away_pct"]) - f["draw_pct"] < 8,
        "over25_p": f["over25"], "over25": hg + ag > 2.5,
        "btts_p": f["btts"], "btts": hg > 0 and ag > 0,
        "cards5_p": f["cards5"], "cards": cards, "cards_exp": (f.get("cards") or {}).get("exp"),
        "scorers": players("goals"), "bookings": players("cards"),
        **event_lists(ev),
    }


def summarise(rows):
    n = len(rows)
    if not n:
        return {"matches": 0}
    s = {"matches": n,
         "result_correct": sum(r["correct"] for r in rows),
         "avg_pick_pct": round(sum(r["pick_pct"] for r in rows) / n, 1),
         "log_loss": round(-sum(math.log(max(r["p_actual"] / 100, 1e-3)) for r in rows) / n, 3),
         "draws": sum(r["actual"] == "Draw" for r in rows),
         "draw_risk_flagged": sum(r["draw_risk"] for r in rows),
         "draw_risk_drew": sum(r["draw_risk"] and r["actual"] == "Draw" for r in rows)}
    for key, prob in (("over25", "over25_p"), ("btts", "btts_p")):
        s[f"{key}_correct"] = sum((r[prob] >= 50) == r[key] for r in rows)
        s[f"{key}_happened"] = sum(r[key] for r in rows)
        s[f"{key}_expected"] = round(sum(r[prob] for r in rows) / 100, 1)
    c = [r for r in rows if r["cards"] is not None]
    s["cards_matches"] = len(c)
    s["cards5_correct"] = sum((r["cards5_p"] >= 50) == (r["cards"] >= 5) for r in c)
    s["cards5_happened"] = sum(r["cards"] >= 5 for r in c)
    s["cards5_expected"] = round(sum(r["cards5_p"] for r in c) / 100, 1)
    ce = [r for r in c if r.get("cards_exp") is not None]
    if ce:
        s["cards_exp_avg"] = round(sum(r["cards_exp"] for r in ce) / len(ce), 2)
        s["cards_actual_avg"] = round(sum(r["cards"] for r in ce) / len(ce), 2)
        s["cards_mae"] = round(sum(abs(r["cards_exp"] - r["cards"]) for r in ce) / len(ce), 2)
        s["cards_exp_matches"] = len(ce)
    for kind in ("scorers", "bookings"):
        picks = [x for r in rows for x in r[kind]]
        s[f"{kind}_picks"] = len(picks)
        s[f"{kind}_hits"] = sum(x["hit"] for x in picks)
        s[f"{kind}_expected"] = round(sum(x["p"] for x in picks) / 100, 1)
    return s


def main():
    preds = published_predictions()
    rows = []
    for lg in LEAGUES:
        d = os.path.join(BASE, "data", lg)
        if not os.path.isdir(d):
            continue
        results = {}
        for name in os.listdir(d):
            if name.startswith("fixtures_"):
                for x in load(os.path.join(d, name), []):
                    results[x["id"]] = x
        events = load(os.path.join(d, "match_events.json"), {})
        stats = load(os.path.join(d, "match_stats.json"), {})
        ids_by_name = {}
        for name in os.listdir(d):
            if name.startswith("players_"):
                for p in load(os.path.join(d, name), []):
                    ids_by_name[(p["name"], p["team"])] = p["id"]
        for fid, (plg, lname, when, f) in preds.items():
            if plg != lg:
                continue
            r = results.get(fid)
            if r and r["status"] in FINISHED and r["hg"] is not None:
                rows.append(score_match(lg, lname, when, f, r, events, stats, ids_by_name))
    # keep rows already scored earlier (e.g. when the git history was restarted in a new repository)
    seen = {r["id"] for r in rows}
    rows += [r for r in load(os.path.join(OUT, "matches.json"), []) if r.get("id") not in seen]
    # rows scored earlier may lack the goal/card lists: fill them in from the saved match events
    ev_cache = {}
    for r in rows:
        if "goal_events" not in r:
            lg = r["league"]
            if lg not in ev_cache:
                ev_cache[lg] = load(os.path.join(BASE, "data", lg, "match_events.json"), {})
            r.update(event_lists(ev_cache[lg].get(str(r["id"]))))
    rows.sort(key=lambda r: r["kickoff"], reverse=True)
    by = defaultdict(list)
    for r in rows:
        by[r["league"]].append(r)
    summary = {"updated": datetime.now(timezone.utc).isoformat(), "overall": summarise(rows),
               "leagues": {lg: dict(summarise(v), name=v[0]["league_name"]) for lg, v in by.items()}}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "matches.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    if os.environ.get("SHOW_TRACK_RECORD") == "1":     # totals and percentages are private: never written by the public run
        with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=1)
    o = summary["overall"]
    if o["matches"]:
        print(f"Track record: {o['matches']} matches, results {o['result_correct']}/{o['matches']}, "
              f"scorers {o['scorers_hits']}/{o['scorers_picks']} (expected {o['scorers_expected']})")
    else:
        print("Track record: no finished matches with published predictions yet")


if __name__ == "__main__":
    main()
