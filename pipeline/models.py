# -*- coding: utf-8 -*-
"""
Predictions for one league, using only that league's own data in data/<league>/.

Produces data/site/<league>.json, which build_site.py turns into the web page.
"""
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

from .config import DATA_DIR, NEXT_FIXTURES, current_season

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import result_model as rm  # noqa: E402

FINISHED = {"FT", "AET", "PEN"}
UPCOMING = {"NS", "TBD"}


# ---------------------------------------------------------------- loading

def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def load_league(league):
    d = os.path.join(DATA_DIR, league)
    fx = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if name.startswith("fixtures_") and name.endswith(".json"):
            season = int(name[9:13])
            fx += [dict(x, season=season) for x in _load(os.path.join(d, name), [])]
    fixtures = pd.DataFrame(fx)
    if fixtures.empty:
        return None
    fixtures["dt"] = pd.to_datetime(fixtures["date"], utc=True, errors="coerce").dt.tz_convert(None)
    stats = _load(os.path.join(d, "match_stats.json"), {})
    players = pd.DataFrame(_load(os.path.join(d, f"players_{current_season()}.json"), []))

    def stat(fid, side, key):
        v = ((stats.get(str(fid)) or {}).get(side) or {}).get(key)
        return np.nan if v is None else float(v)

    res = fixtures[fixtures["status"].isin(FINISHED)].copy()
    for side in ("home", "away"):
        res[f"{side}_cards"] = [stat(i, side, "Yellow Cards") + (0 if np.isnan(stat(i, side, "Red Cards")) else stat(i, side, "Red Cards"))
                                for i in res["id"]]
        res[f"{side}_sot"] = [stat(i, side, "Shots on Goal") for i in res["id"]]
    res["cards"] = res["home_cards"] + res["away_cards"]
    res = res.sort_values("dt").reset_index(drop=True)

    now = pd.Timestamp.now(tz=None)
    upcoming = (fixtures[fixtures["status"].isin(UPCOMING) & (fixtures["dt"] >= now - pd.Timedelta(hours=3))]
                .sort_values("dt").head(NEXT_FIXTURES).reset_index(drop=True))
    return {"results": res, "upcoming": upcoming, "players": players}


# ---------------------------------------------------------------- pieces

def _hist_for_goals_model(res):
    return pd.DataFrame({
        "date": res["dt"].dt.strftime("%d/%m/%Y %H:%M:%S"),
        "home_team_name": res["home"], "away_team_name": res["away"],
        "home_goals": res["hg"], "away_goals": res["ag"],
    })


def referee_table(res):
    r = res.dropna(subset=["cards"])
    r = r[r["referee"].astype(str).str.len() > 0]
    r = r[r["dt"] >= r["dt"].max() - pd.Timedelta(days=3 * 365)] if len(r) else r
    g = r.groupby("referee")["cards"].agg(["mean", "count"])
    return g, (r["cards"].mean() if len(r) else 4.0)


def team_card_rates(res):
    r = res.dropna(subset=["cards"])
    r = r[r["dt"] >= r["dt"].max() - pd.Timedelta(days=365)] if len(r) else r
    games = pd.concat([r[["home", "cards"]].set_axis(["team", "cards"], axis=1),
                       r[["away", "cards"]].set_axis(["team", "cards"], axis=1)])
    return games.groupby("team")["cards"].mean()


def team_cards_received(res):
    """Average cards each team receives per game (last 12 months)."""
    r = res.dropna(subset=["home_cards", "away_cards"])
    r = r[r["dt"] >= r["dt"].max() - pd.Timedelta(days=365)] if len(r) else r
    games = pd.concat([r[["home", "home_cards"]].set_axis(["team", "c"], axis=1),
                       r[["away", "away_cards"]].set_axis(["team", "c"], axis=1)])
    g = games.groupby("team")["c"].agg(["sum", "count"])
    prior = games["c"].mean() if len(games) else 2.0
    return (g["sum"] + prior * 6) / (g["count"] + 6)      # few games -> closer to league average


def card_dispersion(res):
    """Negative-binomial 'size' for card counts (cards vary more than a Poisson)."""
    c = res["cards"].dropna()
    c = c.tail(1500)
    mu, var = c.mean(), c.var()
    return float(mu ** 2 / (var - mu)) if len(c) > 50 and var > mu else 50.0


def cards_prediction(ref, home, away, ref_tab, league_cards, team_cards, received, size):
    """Expected cards in the match, the split between the teams, and the
    chance of going over each common betting line."""
    _, ref_rate = cards_prob(ref, home, away, ref_tab, league_cards, team_cards)
    h = team_cards.get(home, league_cards)
    a = team_cards.get(away, league_cards)
    lam = 0.4 * ref_rate + 0.3 * h + 0.3 * a
    rh = received.get(home, league_cards / 2)
    ra = received.get(away, league_cards / 2)
    share_h = rh / (rh + ra) if (rh + ra) > 0 else 0.5
    over = {f"{k + 0.5}": round(100 * float(1 - nbinom.cdf(k, size, size / (size + lam))), 1) for k in range(2, 7)}
    return {"exp": round(lam, 2), "home": round(lam * share_h, 2), "away": round(lam * (1 - share_h), 2),
            "over": over}, ref_rate


def cards_prob(ref, home, away, ref_tab, league_cards, team_cards):
    """P(5+ cards in the match): blend of referee, home team and away team
    card averages (referee shrunk towards the league average)."""
    if ref and ref in ref_tab.index:
        m, n = ref_tab.loc[ref, "mean"], ref_tab.loc[ref, "count"]
        ref_rate = (m * n + league_cards * 8) / (n + 8)
    else:
        ref_rate = league_cards
    h = team_cards.get(home, league_cards)
    a = team_cards.get(away, league_cards)
    lam = 0.4 * ref_rate + 0.3 * h + 0.3 * a
    return float(1 - poisson.cdf(4, lam)), ref_rate


def form_table(res, season):
    r = res[res["season"] == season]
    out = {}
    for side, team_col in (("home", "home"), ("away", "away")):
        g = r.assign(win=(r["hg"] > r["ag"]) if side == "home" else (r["ag"] > r["hg"]),
                     o25=(r["hg"] + r["ag"]) > 2.5,
                     btts=(r["hg"] > 0) & (r["ag"] > 0)).groupby(team_col)
        out[side] = {t: {"played": int(len(x)), "win": 100 * x["win"].mean(),
                         "over25": 100 * x["o25"].mean(), "btts": 100 * x["btts"].mean()}
                     for t, x in g}
    return out


def half_rates(res):
    """Per team: goals scored / conceded per half (last 12 months, both venues)."""
    r = res.dropna(subset=["ht_h", "ht_a"])
    r = r[r["dt"] >= r["dt"].max() - pd.Timedelta(days=365)] if len(r) else r
    rows = []
    for _, m in r.iterrows():
        rows.append((m["home"], m["ht_h"], m["hg"] - m["ht_h"], m["ht_a"], m["ag"] - m["ht_a"]))
        rows.append((m["away"], m["ht_a"], m["ag"] - m["ht_a"], m["ht_h"], m["hg"] - m["ht_h"]))
    t = pd.DataFrame(rows, columns=["team", "fh_for", "sh_for", "fh_ag", "sh_ag"])
    return t.groupby("team").mean(), t[["fh_for", "sh_for"]].mean()


def goal_timing(home, away, rates, avg):
    def get(team):
        return rates.loc[team] if team in rates.index else pd.Series(
            {"fh_for": avg["fh_for"], "sh_for": avg["sh_for"], "fh_ag": avg["fh_for"], "sh_ag": avg["sh_for"]})
    h, a = get(home), get(away)

    def pct(att, opp):
        return 100 * (1 - np.exp(-(0.6 * att + 0.4 * opp)))
    out = {
        "home": {"fh": pct(h["fh_for"], a["fh_ag"]), "sh": pct(h["sh_for"], a["sh_ag"])},
        "away": {"fh": pct(a["fh_for"], h["fh_ag"]), "sh": pct(a["sh_for"], h["sh_ag"])},
    }
    for s in ("home", "away"):
        out[s]["any"] = 100 * (1 - (1 - out[s]["fh"] / 100) * (1 - out[s]["sh"] / 100))
    out["match_fh"] = 100 * (1 - (1 - out["home"]["fh"] / 100) * (1 - out["away"]["fh"] / 100))
    out["match_sh"] = 100 * (1 - (1 - out["home"]["sh"] / 100) * (1 - out["away"]["sh"] / 100))
    return out


GOAL_PRIOR = {"Attacker": 0.32, "Midfielder": 0.12, "Defender": 0.04}
CARD_PRIOR = {"Attacker": 0.10, "Midfielder": 0.17, "Defender": 0.17}


def player_rates(players):
    if players.empty:
        return players
    p = players.copy()
    p = p[p["position"] != "Goalkeeper"]
    n90 = p["minutes"] / 90.0
    est_goals = 0.5 * p["goals"] + 0.5 * 0.30 * p["sot"]
    p["goal90"] = (est_goals + p["position"].map(GOAL_PRIOR).fillna(0.10) * 4) / (n90 + 4)
    p["card90"] = (p["yellow"] + p["red"] + p["position"].map(CARD_PRIOR).fillna(0.14) * 4) / (n90 + 4)
    p["exp_min"] = (p["minutes"] / p["apps"].where(p["apps"] > 0)).clip(upper=90).fillna(0)
    team_games = p.groupby("team")["apps"].transform("max").replace(0, np.nan)
    p["involvement"] = (p["apps"] / team_games).fillna(0)
    return p[(p["exp_min"] >= 30) & (p["involvement"] >= 0.4)]


def player_picks(p, team, opp_factor, card_factor, home, out_ids=()):
    sq = p[p["team"] == team]
    if out_ids:   # ruled out of this match: never pick them
        sq = sq[~sq["id"].isin(out_ids)]
    if sq.empty:
        return {"scorers": [], "bookings": [], "defender": None}
    loc = 1.08 if home else 0.93
    share = sq["exp_min"] / 90
    g = 1 - np.exp(-sq["goal90"] * share * opp_factor * loc)
    c = 1 - np.exp(-sq["card90"] * share * card_factor)
    sc = sq.assign(p=g).sort_values("p", ascending=False).head(2)
    bk = sq.assign(p=c).sort_values("p", ascending=False).head(2)
    defs = sq[(sq["position"] == "Defender") & ((sq["shots"] > 0) | (sq["sot"] > 0))]
    defender = None
    if not defs.empty:
        best = defs.assign(score=defs["sot"] * 2 + defs["shots"] * 0.6).sort_values("score", ascending=False).iloc[0]
        defender = {"id": int(best["id"]), "name": best["name"], "sot": int(best["sot"])}
    return {
        "scorers": [{"id": int(r["id"]), "name": r["name"], "p": round(100 * r["p"], 1)} for _, r in sc.iterrows()],
        "bookings": [{"id": int(r["id"]), "name": r["name"], "p": round(100 * r["p"], 1)} for _, r in bk.iterrows()],
        "defender": defender,
    }


def previous_meetings(res, home, away, n=8):
    m = res[((res["home"] == home) & (res["away"] == away)) | ((res["home"] == away) & (res["away"] == home))]
    m = m.sort_values("dt", ascending=False).head(n)
    return [{"date": d.strftime("%d/%m/%Y"), "home": h, "away": a, "hg": int(hg), "ag": int(ag)}
            for d, h, a, hg, ag in zip(m["dt"], m["home"], m["away"], m["hg"], m["ag"])]


# ---------------------------------------------------------------- odds

def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]+", " ", s).split()


def _player_match(pick_name, sel_name):
    """'B. Saka' ~ 'Bukayo Saka', 'Kylian Mbappé' ~ 'K. Mbappe'."""
    a, b = _norm(pick_name), _norm(sel_name)
    if not a or not b:
        return False
    if a == b or sorted(a) == sorted(b):
        return True
    surname_a = [w for w in a if len(w) > 1]
    surname_b = [w for w in b if len(w) > 1]
    if not surname_a or not surname_b or surname_a[-1] != surname_b[-1]:
        return False
    return a[0][0] == b[0][0]      # same first initial


_BK = [{}]   # per-bookmaker prices of the fixture being processed (set in attach_odds)


def _price(m, market, sel):
    v = (m.get(market) or {}).get(sel)
    if not v:
        return None
    return {"odd": v["odd"], "bookie": v["bookie"], "books": (_BK[0].get(market) or {}).get(sel) or {}}


def _player_price(m, pick_name, kind):
    """Best price for a player market: anytime scorer, or to be booked."""
    names = list(m)
    if kind == "scorer":
        names = [n for n in names if "scorer" in n.lower() and not re.search(r"first|last|2 or more|hat", n, re.I)]
        names.sort(key=lambda n: "anytime" not in n.lower())   # anytime markets first
    else:
        names = [n for n in names if "booked" in n.lower() or ("card" in n.lower() and "player" in n.lower())]
    for mname in names:
        for sel, v in m[mname].items():
            if _player_match(pick_name, sel):
                return {"odd": v["odd"], "bookie": v["bookie"], "books": (_BK[0].get(mname) or {}).get(sel) or {}}
    return None


def attach_odds(fx, m, books=None):
    _BK[0] = books or {}
    if not m:
        fx["odds"] = None
        return
    fx["odds"] = {
        "home": _price(m, "Match Winner", "Home"), "draw": _price(m, "Match Winner", "Draw"),
        "away": _price(m, "Match Winner", "Away"),
        "over25": _price(m, "Goals Over/Under", "Over 2.5"), "under25": _price(m, "Goals Over/Under", "Under 2.5"),
        "btts_yes": _price(m, "Both Teams Score", "Yes"), "btts_no": _price(m, "Both Teams Score", "No"),
        "cards_over45": _price(m, "Cards Over/Under", "Over 4.5"),
        "cards": {line: {"over": _price(m, "Cards Over/Under", f"Over {line}"),
                         "under": _price(m, "Cards Over/Under", f"Under {line}")}
                  for line in ("2.5", "3.5", "4.5", "5.5", "6.5")},
    }
    for side in ("home", "away"):
        for s in fx["players"][side]["scorers"]:
            s["price"] = _player_price(m, s["name"], "scorer")
        for s in fx["players"][side]["bookings"]:
            s["price"] = _player_price(m, s["name"], "booked")


# ---------------------------------------------------------------- injuries, thin data, market

# Checked against ~1,850 matches with historical injury lists (Oct 2026): the attacking effect did not
# improve predictions (it got worse as it was scaled up), the defensive one was neutral to slightly
# positive. The attacking weight was therefore cut from 0.7 to 0.35 until more data is in.
INJURY_ATT_WEIGHT = 0.35   # losing X% of a team's expected goals cuts its goals by 0.35 * X%
INJURY_ATT_CAP = 0.30
DEF_PENALTY = {"Defender": 0.04, "Goalkeeper": 0.07}   # opponent scores this much more per missing regular
DEF_CAP = 0.15
DOUBTFUL_WEIGHT = 0.5       # a doubtful player counts as half a missing one
THIN_MATCHES = 15           # fewer matches of history than this = low data
CLOSE_GAP = 8               # draw within this many points of the favourite = close call


def injury_effect(players, p_rates, team, missing):
    """missing: {player_id: weight}. Returns (share of goals lost, extra goals for the opponent, key players out)."""
    if not missing or players is None or players.empty:
        return 0.0, 0.0, []
    sq = p_rates[p_rates["team"] == team] if not p_rates.empty else p_rates
    lost, total, key = 0.0, 0.0, []
    if not sq.empty:
        contrib = sq["goal90"] * sq["exp_min"] / 90.0
        total = float(contrib.sum())
        for pid, w in missing.items():
            c = float(contrib[sq["id"] == pid].sum())
            lost += c * w
            if total > 0 and c / total >= 0.10:
                key.append(str(sq.loc[sq["id"] == pid, "name"].iloc[0]))
    att = min(INJURY_ATT_CAP, INJURY_ATT_WEIGHT * lost / total) if total > 0 else 0.0
    raw = players[players["team"] == team]
    pen = 0.0
    if not raw.empty:
        games = float(raw["apps"].max() or 0)
        for pid, w in missing.items():
            r = raw[(raw["id"] == pid) & raw["position"].isin(DEF_PENALTY)]
            if r.empty or games <= 0:
                continue
            r = r.iloc[0]
            if r["apps"] / games >= 0.5 and r["apps"] > 0 and r["minutes"] / r["apps"] >= 60:
                pen += DEF_PENALTY[r["position"]] * w
                key.append(str(r["name"]))
    return att, min(DEF_CAP, pen), key


def market_probs(books):
    """Average bookmaker 1X2 prices -> chances with the bookmakers' margin removed."""
    mw = (books or {}).get("Match Winner") or {}
    out = {}
    for k, sel in (("home", "Home"), ("draw", "Draw"), ("away", "Away")):
        v = list((mw.get(sel) or {}).values())
        if not v:
            return None
        out[k] = 1.0 / (sum(v) / len(v))
    t = sum(out.values())
    return {k: round(100 * v / t, 1) for k, v in out.items()}


# ---------------------------------------------------------------- main

def predict_league(league, name, country):
    data = load_league(league)
    if data is None or data["upcoming"].empty:
        return None
    res, up, players = data["results"], data["upcoming"], data["players"]
    season = current_season()

    fitted = rm.fit(_hist_for_goals_model(res))
    ref_tab, league_cards = referee_table(res)
    team_cards = team_card_rates(res)
    received = team_cards_received(res)
    size = card_dispersion(res)
    form = form_table(res, season)
    rates, avg = half_rates(res)
    p_rates = player_rates(players)

    cur = res[res["season"] == season]
    if len(cur) < 30:
        cur = res[res["dt"] >= res["dt"].max() - pd.Timedelta(days=365)]
    conceded = pd.concat([cur[["home", "ag"]].set_axis(["t", "c"], axis=1),
                          cur[["away", "hg"]].set_axis(["t", "c"], axis=1)]).groupby("t")["c"].mean()
    league_conc = conceded.mean() if len(conceded) else 1.35

    def opp(team):
        v = conceded.get(team)
        return 1.0 if v is None or pd.isna(v) else float(np.clip(v / league_conc, 0.7, 1.4))

    hist = res[res["dt"] >= res["dt"].max() - pd.Timedelta(days=3 * 365)]
    n_hist = pd.concat([hist["home"], hist["away"]]).value_counts()
    odds = _load(os.path.join(DATA_DIR, league, "odds.json"), {})
    injuries = _load(os.path.join(DATA_DIR, league, "injuries.json"), {})
    out = []
    for _, f in up.iterrows():
        home, away, ref = f["home"], f["away"], f["referee"] or ""
        lh, la = rm.expected_goals(fitted, home, away)
        lh0, la0 = lh, la
        cards, ref_rate = cards_prediction(ref, home, away, ref_tab, league_cards, team_cards, received, size)
        inj_rows = (injuries.get(str(int(f["id"]))) or {}).get("players") or []
        inj = {"home": [], "away": []}
        for r in inj_rows:
            side = "home" if r["team"] == home else "away" if r["team"] == away else None
            if side and r.get("name"):
                inj[side].append({"id": r["id"], "name": r["name"], "type": r["type"], "reason": r["reason"]})
        out_ids = {side: {r["id"] for r in inj[side] if "missing" in r["type"].lower()} for side in inj}
        weights = {side: {r["id"]: (1.0 if "missing" in r["type"].lower() else DOUBTFUL_WEIGHT) for r in inj[side]} for side in inj}
        att_h, def_h, key_h = injury_effect(players, p_rates, home, weights["home"])
        att_a, def_a, key_a = injury_effect(players, p_rates, away, weights["away"])
        lh = lh * (1 - att_h) * (1 + def_a)
        la = la * (1 - att_a) * (1 + def_h)
        ph, pdraw, pa = rm.probabilities(lh, la)
        o25, btts = rm.goal_markets(lh, la)
        model_pick = max((("Home", ph), ("Draw", pdraw), ("Away", pa)), key=lambda x: x[1])[0]
        mkt = market_probs((odds.get(str(int(f["id"]))) or {}).get("books"))
        market_pick = None if not mkt else {"home": "Home", "draw": "Draw", "away": "Away"}[max(mkt, key=mkt.get)]
        thin = min(int(n_hist.get(home, 0)), int(n_hist.get(away, 0))) < THIN_MATCHES
        close = model_pick != "Draw" and 100 * (max(ph, pa) - pdraw) < CLOSE_GAP
        disagree = market_pick is not None and market_pick != model_pick
        reasons = (["low data"] if thin else []) + (["bookmakers disagree"] if disagree else [])
        pick = "Draw" if (close and reasons) else model_pick
        c5 = cards["over"]["4.5"] / 100
        card_factor = float(np.clip(ref_rate / league_cards, 0.8, 1.3)) if league_cards else 1.0
        ra = ref_tab.loc[ref] if ref in ref_tab.index else None
        out.append({
            "id": int(f["id"]),
            "kickoff": f["dt"].isoformat(),
            "round": f.get("round"),
            "home": home, "away": away,
            "referee": ref,
            "ref_cards": None if ra is None else round(float(ra["mean"]), 2),
            "ref_games": None if ra is None else int(ra["count"]),
            "pick": pick, "model_pick": model_pick,
            "call_reason": ", ".join(reasons) if pick != model_pick else "",
            "low_data": bool(thin), "market": mkt,
            "injury_effect": {"home": {"goals_lost_pct": round(100 * att_h, 1), "defence_hit_pct": round(100 * def_h, 1), "key_out": sorted(set(key_h))},
                              "away": {"goals_lost_pct": round(100 * att_a, 1), "defence_hit_pct": round(100 * def_a, 1), "key_out": sorted(set(key_a))}},
            "home_pct": round(100 * ph, 1), "draw_pct": round(100 * pdraw, 1), "away_pct": round(100 * pa, 1),
            "xg_home": round(lh, 2), "xg_away": round(la, 2),
            "over25": round(100 * o25, 1), "btts": round(100 * btts, 1), "cards5": round(100 * c5, 1), "cards": cards,
            "form": {"home": form["home"].get(home), "away": form["away"].get(away)},
            "goals": goal_timing(home, away, rates, avg),
            "players": {
                "home": player_picks(p_rates, home, opp(away), card_factor, True, out_ids["home"]),
                "away": player_picks(p_rates, away, opp(home), card_factor, False, out_ids["away"]),
            },
            "injuries": inj,
            "previous": previous_meetings(res, home, away),
        })
        attach_odds(out[-1], (odds.get(str(int(f["id"]))) or {}).get("markets"),
                    (odds.get(str(int(f["id"]))) or {}).get("books"))

    result = {
        "league": league, "name": name, "country": country,
        "season": season, "updated": datetime.now(timezone.utc).isoformat(),
        "matches_used": int(len(res)), "fixtures": out,
    }
    site_dir = os.path.join(DATA_DIR, "site")
    os.makedirs(site_dir, exist_ok=True)
    with open(os.path.join(site_dir, f"{league}.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1, default=float)
    return result
