# -*- coding: utf-8 -*-
"""Pressure log: watches live matches, records every 'high attacking pressure' flag and whether a goal followed.

A flag is a WIN if at least one goal is scored in the 15 match-minutes after it is raised.
Results go to data/pressure_log.json (not published on the website).

    python -m pipeline.pressure_log [minutes_to_run]     # polls about every 90 seconds
"""
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timezone

from . import fetch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "pressure_log.json")
PICKS = os.path.join(ROOT, "data", "live_picks.json")
LEAGUES = "39-140-78-135-61-2-3-848-40-41-42-179-88-94-144-197-203-79-136-141-62"
WINDOW = 15          # minutes after a flag in which a goal counts as a win
COOLDOWN = 15        # no second flag for the same match within this many match minutes
POLL = 90            # seconds between checks
KEYS = {"Total Shots": "sh", "Shots on Goal": "sot", "Corner Kicks": "co", "expected_goals": "xg"}


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pack(s):
    def n(v):
        if isinstance(v, str):
            try:
                v = float(v.strip("%"))
            except ValueError:
                return 0
        return v if isinstance(v, (int, float)) and math.isfinite(v) else 0
    s = s or {}
    xg = s.get("xg")
    return {"sh": n(s.get("sh")), "sot": n(s.get("sot")), "co": n(s.get("co")),
            "xg": float(xg) if isinstance(xg, (int, float)) and math.isfinite(xg) else None}


def est(p):
    return p["xg"] if p["xg"] is not None else 0.04 * max(p["sh"] - p["sot"], 0) + 0.30 * p["sot"] + 0.03 * p["co"]


def stats_of(f):
    out = {"h": {}, "a": {}}
    lst = f.get("statistics") or []
    for t in lst:
        side = "h" if (t.get("team") or {}).get("id") == f["teams"]["home"]["id"] else "a"
        for s in t.get("statistics") or []:
            k = KEYS.get(s.get("type"))
            if k:
                out[side][k] = s.get("value")
    return out if lst else None


def model(m, bx, hist, now):
    """Python copy of the Live tab's pressure model (live_page.py). Returns (level, ratio, who, P) or None."""
    t = min(m["el"] or 0, 90)
    sx = m["sx"]
    if not sx or t < 8:
        return None
    r0h, r0a = bx[0] / 90, bx[1] / 90
    h, a = pack(sx["h"]), pack(sx["a"])
    wc, ww, wh, wa = min(t / 90, 1) * 0.5, 0.0, 0.0, 0.0
    old = None
    for c in hist:
        age = (now - c["t"]) / 60
        if 3 <= age <= 16:
            old = c
            break
    if old:
        dt = (now - old["t"]) / 60
        ww = min(dt / 15, 1) * 0.4
        wh = max(est(h) - est(old["h"]), 0) / dt
        wa = max(est(a) - est(old["a"]), 0) / dt
    rh = (1 - wc - ww) * r0h + wc * est(h) / max(t, 1) + ww * wh
    ra = (1 - wc - ww) * r0a + wc * est(a) / max(t, 1) + ww * wa
    d = m["hg"] - m["ag"]
    late = 1 + 0.1 * max(0, (t - 70) / 20)
    mh = 1 + 0.08 * min(-d, 2) if d < 0 else (1 - 0.05 * min(d, 2) if d > 0 else 1)
    ma = 1 + 0.08 * min(d, 2) if d > 0 else (1 - 0.05 * min(-d, 2) if d < 0 else 1)
    rc_h, rc_a = pack_rc(sx, "h"), pack_rc(sx, "a")
    mh *= 0.8 ** rc_h * 1.2 ** rc_a
    ma *= 0.8 ** rc_a * 1.2 ** rc_h
    rh *= mh * late
    ra *= ma * late
    hor = max(1, min(15, 95 - t))
    P = 1 - math.exp(-(rh + ra) * hor)
    ratio = (rh + ra) / (r0h + r0a)
    level = "high" if ratio >= 1.25 else "building" if ratio >= 0.85 else "low"
    fh, fa = rh / (r0h * mh * late), ra / (r0a * ma * late)
    who = "both sides"
    if fh > 1.15 * fa and fh > 1.0:
        who = "home"
    elif fa > 1.15 * fh and fa > 1.0:
        who = "away"
    return level, ratio, who, P


def pack_rc(sx, side):
    v = (sx.get(side) or {}).get("rc")
    return v if isinstance(v, (int, float)) else 0


def summary(flags):
    done = [f for f in flags if f.get("result") in ("win", "loss")]
    wins = [f for f in done if f["result"] == "win"]
    side = [f for f in done if f["who"] != "both sides"]
    side_wins = [f for f in side if f.get("by_flagged_side")]
    bands = {}
    for lo, hi, name in ((0, 30, "0-30"), (30, 60, "30-60"), (60, 75, "60-75"), (75, 120, "75+")):
        b = [f for f in done if lo <= f["min"] < hi]
        bands[name] = {"flags": len(b), "wins": sum(f["result"] == "win" for f in b),
                       "avg_model_chance": round(sum(f["P"] for f in b) / len(b), 3) if b else None}
    return {"by_minute": bands, "flags": len(flags), "resolved": len(done), "wins": len(wins),
            "hit_rate": round(len(wins) / len(done), 3) if done else None,
            "avg_model_chance": round(sum(f["P"] for f in done) / len(done), 3) if done else None,
            "side_flags": len(side), "side_scored": len(side_wins), "updated": _now()}


def save(log):
    log["summary"] = summary(log["flags"])
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)


def resolve(flag, key):
    """Look at the finished/elapsed match and decide win or loss from the goal events in the window."""
    r = fetch.api_get("fixtures", {"id": flag["id"]}, key).get("response") or []
    if not r:
        return False
    f = r[0]
    el = (f["fixture"]["status"].get("elapsed") or 0)
    fin = f["fixture"]["status"]["short"] in ("FT", "AET", "PEN", "AWD", "WO", "CANC", "ABD", "PST")
    if not fin and el < flag["min"] + WINDOW:
        return False
    home_id = f["teams"]["home"]["id"]
    goals = []
    for e in f.get("events") or []:
        if e.get("type") != "Goal" or e.get("detail") == "Missed Penalty":
            continue
        m = (e["time"]["elapsed"] or 0) + ((e["time"].get("extra") or 0) / 100)
        if flag["min"] < m <= flag["min"] + WINDOW + 0.99:
            home_team = (e.get("team") or {}).get("id") == home_id
            scorer = ("home" if home_team else "away") if e.get("detail") != "Own Goal" else ("away" if home_team else "home")
            goals.append({"min": e["time"]["elapsed"], "side": scorer, "player": (e.get("player") or {}).get("name"), "own": e.get("detail") == "Own Goal"})
    # goals that were cancelled by VAR stay in the event list sometimes: never count more than the score allows
    allowed = (f["goals"]["home"] or 0) + (f["goals"]["away"] or 0) - flag["sh"] - flag["sa"]
    goals = goals[:max(allowed, 0)]
    flag["goals"] = goals
    flag["result"] = "win" if goals else "loss"
    flag["by_flagged_side"] = bool(goals) and flag["who"] != "both sides" and any(g["side"] == flag["who"] for g in goals)
    flag["resolved_at"] = _now()
    return True


def poll(log, key, picks, hist):
    now = time.time()
    live = fetch.api_get("fixtures", {"live": LEAGUES}, key).get("response") or []
    matches = {}
    for f in live:
        st = f["fixture"]["status"]["short"]
        matches[f["fixture"]["id"]] = {
            "id": f["fixture"]["id"], "lg": f["league"]["id"], "home": f["teams"]["home"]["name"], "away": f["teams"]["away"]["name"],
            "hg": f["goals"]["home"] or 0, "ag": f["goals"]["away"] or 0, "st": st, "el": f["fixture"]["status"].get("elapsed"),
            "sx": None, "live": st in ("1H", "2H", "ET")}
    ids = [i for i, m in matches.items() if m["live"]]
    for i in range(0, len(ids), 20):
        for f in fetch.api_get("fixtures", {"ids": "-".join(map(str, ids[i:i + 20]))}, key).get("response") or []:
            m = matches.get(f["fixture"]["id"])
            if m:
                m["sx"] = stats_of(f)
    flags = log["flags"]
    n_new = 0
    for m in matches.values():
        if not m["live"] or not m["sx"]:
            continue
        h = hist.setdefault(m["id"], [])
        pk = picks.get(str(m["id"])) or {}
        bx = (pk["xh"], pk["xa"]) if pk.get("xh") is not None else (1.4, 1.15)
        res = model(m, bx, h, now)
        if not h or now - h[-1]["t"] >= 40:
            h.append({"t": now, "h": pack(m["sx"]["h"]), "a": pack(m["sx"]["a"])})
        while h and now - h[0]["t"] > 25 * 60:
            h.pop(0)
        if not res or res[0] != "high":
            continue
        last = [f for f in flags if f["id"] == m["id"]]
        if last and (m["el"] or 0) - last[-1]["min"] < COOLDOWN and last[-1]["min"] <= (m["el"] or 0):
            continue
        s = m["sx"]
        flags.append({"id": m["id"], "lg": m["lg"], "home": m["home"], "away": m["away"], "date": _now()[:10], "at": _now(),
                      "min": m["el"] or 0, "sh": m["hg"], "sa": m["ag"], "who": {"home": "home", "away": "away"}.get(res[2], "both sides"),
                      "who_name": m["home"] if res[2] == "home" else m["away"] if res[2] == "away" else "both sides",
                      "ratio": round(res[1], 2), "P": round(res[3], 3),
                      "stats": {"h": pack(s["h"]), "a": pack(s["a"])}, "result": "open"})
        n_new += 1
        print(f"  FLAG {m['home']} v {m['away']} {m['el']}' ratio {res[1]:.2f} ({flags[-1]['who_name']})", flush=True)
    n_res = 0
    for f in flags:
        if f["result"] == "open" and f["id"] in matches and matches[f["id"]]["live"] and (matches[f["id"]]["el"] or 0) < f["min"] + WINDOW:
            continue
        if f["result"] == "open":
            try:
                if resolve(f, key):
                    n_res += 1
                    print(f"  RESULT {f['home']} v {f['away']} flag {f['min']}': {f['result'].upper()}", flush=True)
            except Exception:
                traceback.print_exc()
    return len(matches), n_new, n_res


def main(argv):
    key = os.environ.get("API_FOOTBALL_KEY", "")
    if not key:
        sys.exit("API_FOOTBALL_KEY not set")
    minutes = float(argv[0]) if argv else 5
    end = time.time() + minutes * 60
    log = _load(LOG, {"flags": []})
    picks = _load(PICKS, {})
    hist = {}
    while True:
        try:
            n, new, res = poll(log, key, picks, hist)
            print(f"{_now()}: {n} live, {new} new flags, {res} resolved", flush=True)
            if new or res:
                save(log)
        except Exception:
            traceback.print_exc()
        if time.time() + POLL > end:
            break
        time.sleep(POLL)
    save(log)


if __name__ == "__main__":
    main(sys.argv[1:])
