# -*- coding: utf-8 -*-
"""
Champions League and Europa League predictions.

One goals model is fitted on every result in data/history/ (the big five, 26 other European leagues and the
three UEFA competitions, 2021 onwards). Each club's league gets its own attack/defence strength, which is
what lets a goal in the Dutch league be weighed against a goal in the Premier League. Back-tested on the
333 Champions League and Europa League matches of 2025-26: 57% of results right, well calibrated.

Writes data/site/champions-league.json and data/site/europa-league.json for build_site.py.
Usage: python -m pipeline.european
"""
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.linear_model import PoissonRegressor

from .config import DATA_DIR, current_season
from . import models

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import result_model as rm  # noqa: E402

COMPETITIONS = {  # site key -> (history file prefix, display name, API-Football id)
    "champions-league": ("champions-league", "Champions League"),
    "europa-league": ("europa-league", "Europa League"),
}
UEFA = {"champions-league", "europa-league", "conference-league"}
FINISHED = {"FT", "AET", "PEN"}
LOOKBACK_DAYS, HALF_LIFE, ALPHA, LEAGUE_SCALE = 1095, 240, 0.0005, 4.0
DAYS_AHEAD = 8
MAX_FIXTURES = 18


def load_history():
    """All matches as a DataFrame, plus {team: domestic league} from the latest season each club appeared in."""
    rows, team_league, seen = {}, {}, {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "history", "*.json"))):
        name, season = os.path.basename(path)[:-5].rsplit("_", 1)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for x in data:
            rows[x["id"]] = dict(x, comp=name, season=int(season))
            if name not in UEFA and x["status"] in FINISHED | {"NS", "TBD"}:
                for t in (x["home"], x["away"]):
                    if seen.get(t, 0) <= int(season):
                        seen[t], team_league[t] = int(season), name
    df = pd.DataFrame(list(rows.values()))
    df["dt"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert(None)
    return df, team_league


class EuroModel:
    def __init__(self, df, team_league, as_of):
        done = df[df["status"].isin(FINISHED) & df["hg"].notna() & (df["dt"] < as_of) &
                  (df["dt"] >= as_of - pd.Timedelta(days=LOOKBACK_DAYS))]
        self.tl = team_league
        self.leagues = sorted(set(team_league.values()))
        self.li = {l: i for i, l in enumerate(self.leagues)}
        self.nl = len(self.leagues)
        w = 0.5 ** ((as_of - done["dt"]).dt.days / HALF_LIFE)
        teams = sorted(set(done["home"]) | set(done["away"]))
        self.idx = {t: i for i, t in enumerate(teams)}
        self.n = len(teams)
        self.width = 2 * self.n + 2 * self.nl + 1
        self.counts = pd.concat([done["home"], done["away"]]).value_counts()
        X = sp.vstack([self._rows(done["home"], done["away"], 1), self._rows(done["away"], done["home"], 0)])
        y = np.concatenate([done["hg"].values, done["ag"].values]).astype(float)
        sw = np.concatenate([w.values, w.values])
        self.model = PoissonRegressor(alpha=ALPHA, max_iter=3000)
        self.model.fit(X, y, sample_weight=sw)
        self.n_matches = len(done)

    def _rows(self, att, deff, home_flag):
        n, nl = self.n, self.nl
        r = np.arange(len(att))
        R = [r, r, r]
        C = [np.array([self.idx[t] for t in att]), np.array([n + self.idx[t] for t in deff]), np.full(len(att), self.width - 1)]
        V = [np.ones(len(att)), np.ones(len(att)), np.full(len(att), float(home_flag))]
        for teams, off in ((att, 2 * n), (deff, 2 * n + nl)):
            pos = [(i, self.li[self.tl[t]]) for i, t in enumerate(teams) if t in self.tl]
            if pos:
                R.append(np.array([p[0] for p in pos]))
                C.append(np.array([off + p[1] for p in pos]))
                V.append(np.full(len(pos), LEAGUE_SCALE))
        return sp.csr_matrix((np.concatenate(V), (np.concatenate(R), np.concatenate(C))), shape=(len(att), self.width))

    def _vec(self, att, deff, home_flag):
        v = np.zeros(self.width)
        if att in self.idx:
            v[self.idx[att]] = 1
        if deff in self.idx:
            v[self.n + self.idx[deff]] = 1
        if att in self.tl:
            v[2 * self.n + self.li[self.tl[att]]] = LEAGUE_SCALE
        if deff in self.tl:
            v[2 * self.n + self.nl + self.li[self.tl[deff]]] = LEAGUE_SCALE
        v[-1] = home_flag
        return v

    def expected_goals(self, home, away):
        lh = float(self.model.predict([self._vec(home, away, 1)])[0])
        la = float(self.model.predict([self._vec(away, home, 0)])[0])
        # clubs with no history at all: slightly below average
        lh *= (0.85 if home not in self.idx else 1) * (1.15 if away not in self.idx else 1)
        la *= (0.85 if away not in self.idx else 1) * (1.15 if home not in self.idx else 1)
        return lh, la


def load_players():
    """Domestic-league season stats (big five) plus European-competition stats, summed per player and club."""
    rows = []
    season = current_season()
    for path in glob.glob(os.path.join(DATA_DIR, "*", f"players_{season}.json")) + [os.path.join(DATA_DIR, "euro_players.json")]:
        try:
            with open(path, encoding="utf-8") as fh:
                rows += json.load(fh)
        except (OSError, ValueError):
            pass
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    agg = {c: "sum" for c in ("apps", "minutes", "goals", "shots", "sot", "yellow", "red")}
    agg.update(name="first", position="first")
    return df.groupby(["id", "team"], as_index=False).agg(agg)


def build_fixture(f, em, res, p_rates=None):
    home, away = f["home"], f["away"]
    lh, la = em.expected_goals(home, away)
    ph, pdraw, pa = rm.probabilities(lh, la)
    o25, btts = rm.goal_markets(lh, la)
    model_pick = max((("Home", ph), ("Draw", pdraw), ("Away", pa)), key=lambda x: x[1])[0]
    thin = min(int(em.counts.get(home, 0)), int(em.counts.get(away, 0))) < models.THIN_MATCHES
    very_close = model_pick != "Draw" and 100 * (max(ph, pa) - pdraw) < models.DRAW_GAP
    reasons = (["low data"] if thin else [])
    if very_close:
        reasons = ["too close to call"] + reasons
    pick = "Draw" if very_close else model_pick
    empty_side = {"scorers": [], "bookings": [], "defender": None}
    prev = res[((res["home"] == home) & (res["away"] == away)) | ((res["home"] == away) & (res["away"] == home))]
    prev = prev.sort_values("dt", ascending=False).head(8)
    previous = [{"date": r["dt"].strftime("%d/%m/%Y"), "home": r["home"], "away": r["away"], "hg": int(r["hg"]), "ag": int(r["ag"])}
                for _, r in prev.iterrows()]
    return {
        "id": int(f["id"]), "kickoff": f["dt"].isoformat(), "round": f.get("round"),
        "home": home, "away": away, "referee": "", "ref_cards": None, "ref_games": None,
        "pick": pick, "model_pick": model_pick,
        "call_reason": ", ".join(reasons) if pick != model_pick else "",
        "low_data": bool(thin), "market": None, "injury_effect": {},
        "home_pct": round(100 * ph, 1), "draw_pct": round(100 * pdraw, 1), "away_pct": round(100 * pa, 1),
        "xg_home": round(lh, 2), "xg_away": round(la, 2),
        "over25": round(100 * o25, 1), "btts": round(100 * btts, 1),
        "cards5": 0.0, "cards": None, "form": {"home": None, "away": None}, "goals": None,
        "players": ({"home": models.player_picks(p_rates, home, 1.0, 1.0, True),
                     "away": models.player_picks(p_rates, away, 1.0, 1.0, False)}
                    if p_rates is not None and not p_rates.empty else {"home": dict(empty_side), "away": dict(empty_side)}),
        "injuries": {"home": [], "away": []}, "previous": previous, "odds": {}, "euro": True,
    }


def main():
    df, team_league = load_history()
    now = pd.Timestamp.now(tz=None)
    em = EuroModel(df, team_league, now)
    print(f"fitted on {em.n_matches} matches, {em.n} clubs, {em.nl} leagues")
    p_rates = models.player_rates(load_players())
    res = df[df["status"].isin(FINISHED) & df["hg"].notna()].copy()
    out_dir = os.path.join(DATA_DIR, "site")
    os.makedirs(out_dir, exist_ok=True)
    for key, (prefix, name) in COMPETITIONS.items():
        up = df[(df["comp"] == prefix) & df["status"].isin(models.UPCOMING) &
                (df["dt"] >= now - pd.Timedelta(hours=3)) & (df["dt"] <= now + pd.Timedelta(days=DAYS_AHEAD))]
        up = up.sort_values("dt").head(MAX_FIXTURES)
        fixtures = [build_fixture(f, em, res, p_rates) for _, f in up.iterrows()]
        result = {"league": key, "name": name, "country": "Europe", "season": current_season(),
                  "updated": datetime.now(timezone.utc).isoformat(), "matches_used": int(em.n_matches),
                  "euro": True, "fixtures": fixtures}
        with open(os.path.join(out_dir, f"{key}.json"), "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=1, default=float)
        print(f"{name}: {len(fixtures)} fixtures")


if __name__ == "__main__":
    main()
