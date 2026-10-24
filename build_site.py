# -*- coding: utf-8 -*-
"""
Build the FootyPredicts website (docs/, served by GitHub Pages) from the
per-league prediction files in data/site/<league>.json.

    python build_site.py

Pages:
  docs/index.html            this week across all leagues
  docs/<league>/index.html   one page per league, one panel per match
"""
import json
import os
from datetime import datetime, timezone
from html import escape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# The public "How we did" page lists each match with a tick or cross but shows NO accuracy percentages or totals.
# Run locally with SHOW_TRACK_RECORD=1 to build the full version (percentages, markets, leagues) for yourself only.
SHOW_TRACK_RECORD = os.environ.get("SHOW_TRACK_RECORD") == "1"
SITE_DATA = os.path.join(BASE_DIR, "data", "site")
OUT_DIR = os.path.join(BASE_DIR, "docs")
DRAW_RISK_GAP = 8   # draw within this many points of the favourite -> "Draw risk"
LEAGUE_ORDER = ["premier-league", "la-liga", "bundesliga", "serie-a", "ligue-1"]


# ---------------------------------------------------------------- helpers

def esc(v):
    return escape("" if v is None else str(v))


def pct(v):
    return "—" if v is None else f"{v:.0f}%"


def short(name):
    n = str(name).replace("Manchester", "Man")
    return n if len(n) <= 16 else " ".join(n.split()[:2])


def kickoff(f):
    dt = datetime.fromisoformat(f["kickoff"]).replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        dt = dt.astimezone(ZoneInfo("Europe/London"))
    except Exception:
        pass
    return dt.strftime("%a %d %b"), dt.strftime("%H:%M"), dt


def most_likely(f):
    if f["pick"] == "Home":
        return f["home"], f["home_pct"], "chance to win"
    if f["pick"] == "Away":
        return f["away"], f["away_pct"], "chance to win"
    return "Draw", f["draw_pct"], "chance of a draw"


def draw_risk(f):
    return f["pick"] != "Draw" and max(f["home_pct"], f["away_pct"]) - f["draw_pct"] < DRAW_RISK_GAP


def sel(f, group, key, label, price, prob, text=None):
    """A clickable price that adds a selection to the bet slip.
    group = one choice per group (e.g. home/draw/away of one match)."""
    shown = label if text is None else text
    if not price:
        return f'<span class="sel none-price">{esc(shown)} <small>no price</small></span>' if shown else ""
    match = f"{f['home']} v {f['away']}"
    return (f'<button type="button" class="sel" aria-pressed="false" data-key="{f["id"]}-{key}" '
            f'data-group="{f["id"]}-{group}" data-fid="{f["id"]}" data-label="{esc(label)}" data-match="{esc(match)}" '
            f'data-odd="{price["odd"]:.2f}" data-bookie="{esc(price["bookie"])}" data-p="{prob:.4f}" '
            f'data-best-odd="{price["odd"]:.2f}" data-best-bookie="{esc(price["bookie"])}" '
            f'data-books="{esc(json.dumps(price.get("books") or {}))}" '
            f'title="Best price {price["odd"]:.2f} at {esc(price["bookie"])} (implies {100 / price["odd"]:.0f}%)">'
            + (f'<span class="sel-l">{esc(shown)}</span>' if shown else '') + f'<b>{price["odd"]:.2f}</b><small>{esc(price["bookie"])}</small></button>')


def odds_of(f, k):
    return (f.get("odds") or {}).get(k)


def meter(label, value, buttons=""):
    w = 0 if value is None else max(0, min(100, value))
    return f"""
        <div class="meter">
          <div class="meter-top"><span>{label}</span><b>{pct(value)}</b></div>
          <div class="meter-track"><div class="meter-fill" style="width:{w:.0f}%"></div></div>
          {f'<div class="meter-sel">{buttons}</div>' if buttons else ''}
        </div>"""


def names(f, lst, team, kind):
    if not lst:
        return '<span class="none">No pick</span>'
    out = []
    for x in lst:
        what = "to score" if kind == "scorer" else "to be booked"
        price = x.get("price")
        if price:
            out.append(f'<span class="pl">{esc(x["name"])} <small>{x["p"]:.0f}%</small> '
                       + sel(f, f"{kind}-{x.get('id', x['name'])}", f"{kind}-{x.get('id', x['name'])}",
                             f"{x['name']} ({team}) {what}", price, x["p"] / 100, text="") + "</span>")
        else:
            out.append(f'<span class="pl">{esc(x["name"])} <small>{x["p"]:.0f}%</small></span>')
    return "".join(out)


def cards_block(f):
    c = f.get("cards")
    if not c:   # older prediction files
        return meter("5+ cards", f["cards5"])
    co = (f.get("odds") or {}).get("cards") or {}

    def line(l):
        p = c["over"][l]
        pr = co.get(l) or {}
        btns = (sel(f, f"cards{l}", f"cards_over{l}", f"Over {l} cards", pr.get("over"), p / 100, "Over")
                + sel(f, f"cards{l}", f"cards_under{l}", f"Under {l} cards", pr.get("under"), 1 - p / 100, "Under"))
        btns = btns if (pr.get("over") or pr.get("under")) else ""
        return meter(f"Over {l} cards", p, btns)

    return f"""
        <div class="cards-box">
          <div class="meter-top"><span>Cards expected</span><b>{c['exp']:.1f}</b></div>
          <div class="cards-split"><span>{esc(short(f['home']))} {c['home']:.1f}</span><span>{esc(short(f['away']))} {c['away']:.1f}</span></div>
          {line("3.5")}
          {line("4.5")}
        </div>"""


DECOR_DEFS = """<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>
  <linearGradient id="fp-ring-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5a4300"/><stop offset=".5" stop-color="#2a2300"/><stop offset="1" stop-color="#0f3d2e"/></linearGradient>
  <radialGradient id="fp-dial-g" cx=".35" cy=".3" r=".9"><stop offset="0" stop-color="#fff6c2"/><stop offset=".55" stop-color="#f6d33b"/><stop offset="1" stop-color="#d9b21c"/></radialGradient>
  <radialGradient id="fp-ball-g" cx=".35" cy=".3" r=".85"><stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#e6ebe7"/><stop offset="1" stop-color="#aab5ae"/></radialGradient>
  <linearGradient id="fp-post-g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#b9c3bd"/></linearGradient>
  <symbol id="fp-ball" viewBox="0 0 100 100">
    <circle cx="50" cy="50" r="47" fill="url(#fp-ball-g)" stroke="#8d9a92" stroke-width="1.5"/>
    <polygon points="50,33 66,45 60,64 40,64 34,45" fill="#1d2a24"/>
    <g stroke="#1d2a24" stroke-width="2" fill="none" stroke-linecap="round">
      <path d="M50 33 L50 12"/><path d="M66 45 L86 38"/><path d="M60 64 L73 82"/><path d="M40 64 L27 82"/><path d="M34 45 L14 38"/></g>
    <g fill="#1d2a24"><polygon points="50,3 62,9 58,20 42,20 38,9"/><polygon points="93,38 95,53 85,58 79,45 86,36"/>
      <polygon points="7,38 14,36 21,45 15,58 5,53"/><polygon points="76,86 66,95 54,91 55,78 68,76"/><polygon points="24,86 32,76 45,78 46,91 34,95"/></g>
    <ellipse cx="36" cy="26" rx="16" ry="9" fill="#fff" opacity=".35" transform="rotate(-30 36 26)"/>
  </symbol>
  <symbol id="fp-flag" viewBox="0 0 80 120">
    <ellipse cx="22" cy="113" rx="16" ry="4" fill="#000" opacity=".18"/>
    <rect x="20" y="8" width="4" height="104" rx="2" fill="url(#fp-post-g)" stroke="#8d9a92" stroke-width=".8"/>
    <path d="M24 10 L70 24 L24 40 Z" fill="#f6d33b" stroke="#c9a227" stroke-width="1.2"/>
    <path d="M24 10 L70 24 L24 40 Z" fill="#fff" opacity=".18" transform="translate(0 -2)"/>
  </symbol>
  <symbol id="fp-kicker" viewBox="0 0 220 200">
    <ellipse cx="100" cy="190" rx="70" ry="6" fill="#000" opacity=".16"/>
    <g fill="none" stroke-linecap="round" stroke-linejoin="round">
      <path d="M96 112 L100 152 L96 184" stroke="#1d2a24" stroke-width="15"/>
      <path d="M96 184 L112 186" stroke="#f6d33b" stroke-width="12"/>
      <path d="M88 112 L122 138 L158 126" stroke="#2c3a33" stroke-width="15"/>
      <path d="M158 126 L170 122" stroke="#f6d33b" stroke-width="12"/>
      <path d="M92 82 L62 100 L44 88" stroke="#2c3a33" stroke-width="10"/>
      <path d="M96 80 L128 74 L146 58" stroke="#1d2a24" stroke-width="10"/>
      <path d="M90 118 L86 80" stroke="#f6d33b" stroke-width="30"/>
      <path d="M88 118 L100 116" stroke="#ffffff" stroke-width="26"/>
    </g>
    <circle cx="94" cy="56" r="14" fill="#1d2a24"/>
    <path d="M82 54 Q94 36 108 52" fill="none" stroke="#0f1814" stroke-width="5" stroke-linecap="round"/>
    <text x="86" y="104" font-family="Barlow Condensed,sans-serif" font-weight="800" font-size="22" fill="#145039" text-anchor="middle" transform="rotate(-4 86 100)">9</text>
    <use href="#fp-ball" x="170" y="104" width="38" height="38"/>
    <g stroke="#9db0a6" stroke-width="3" stroke-linecap="round" opacity=".8"><path d="M200 94 L214 88"/><path d="M204 150 L216 156"/><path d="M148 156 L130 164"/></g>
  </symbol>
  <symbol id="fp-goal" viewBox="0 0 140 100">
    <g stroke="#9db0a6" stroke-width="1" opacity=".9">
      <path d="M18 14 H122 M18 28 H122 M18 42 H122 M18 56 H122 M18 70 H122"/>
      <path d="M32 14 V86 M46 14 V86 M60 14 V86 M74 14 V86 M88 14 V86 M102 14 V86 M116 14 V86"/></g>
    <path d="M8 90 V10 Q8 6 12 6 H128 Q132 6 132 10 V90" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round"/>
    <path d="M8 90 V10 Q8 6 12 6 H128 Q132 6 132 10 V90" fill="none" stroke="#b9c3bd" stroke-width="1.5" transform="translate(1.5 1.5)" opacity=".7"/>
  </symbol>
</defs></svg>"""

DECOR = DECOR_DEFS + """
<div class="decor decor-l" aria-hidden="true">
  <svg class="d-ball d1"><use href="#fp-ball"/></svg>
  <svg class="d-flag"><use href="#fp-flag"/></svg>
  <svg class="d-ball d2"><use href="#fp-ball"/></svg>
</div>
<div class="decor decor-r" aria-hidden="true">
  <svg class="d-goal"><use href="#fp-goal"/></svg>
  <svg class="d-ball d3"><use href="#fp-ball"/></svg>
  <svg class="d-ball d4"><use href="#fp-ball"/></svg>
</div>"""


TEAM_COLOURS = {
 # Premier League
 "Arsenal":"#EF0107","Aston Villa":"#7B003C","Bournemouth":"#DA291C","Brentford":"#E30613","Brighton":"#0057B8",
 "Chelsea":"#034694","Coventry":"#5BC2E7","Crystal Palace":"#1B458F","Everton":"#003399","Fulham":"#2b2b2b",
 "Hull City":"#F5A12D","Ipswich":"#3A64A3","Leeds":"#FFCD00","Liverpool":"#C8102E","Manchester City":"#6CABDD",
 "Manchester United":"#DA291C","Newcastle":"#2b2b2b","Nottingham Forest":"#DD0000","Sunderland":"#EB172B","Tottenham":"#132257",
 # La Liga
 "Alaves":"#0761AF","Athletic Club":"#EE2523","Atletico Madrid":"#CB3524","Barcelona":"#A50044","Celta Vigo":"#8AC3EE",
 "Deportivo La Coruna":"#0A5DAB","Elche":"#00873E","Espanyol":"#007FC8","Getafe":"#005999","Levante":"#B4053F",
 "Malaga":"#0077C8","Osasuna":"#D91A21","Racing Santander":"#00A650","Rayo Vallecano":"#E53027","Real Betis":"#00954C",
 "Real Madrid":"#FEBE10","Real Sociedad":"#0067B1","Sevilla":"#D4021D","Valencia":"#F18A00","Villarreal":"#FBE122",
 # Bundesliga
 "1. FC Köln":"#ED1C24","1899 Hoffenheim":"#1961B5","Bayer Leverkusen":"#E32221","Bayern München":"#DC052D",
 "Borussia Dortmund":"#FDE100","Borussia Mönchengladbach":"#00A651","Eintracht Frankfurt":"#E1000F","FC Augsburg":"#BA3733",
 "FC Schalke 04":"#004D9D","FSV Mainz 05":"#C3141E","Hamburger SV":"#005CA9","RB Leipzig":"#DD0741","SC Freiburg":"#D6001C",
 "SC Paderborn 07":"#004B93","SV Elversberg":"#2b2b2b","Union Berlin":"#EB1923","VfB Stuttgart":"#E32219","Werder Bremen":"#1D9053",
 # Serie A
 "AC Milan":"#FB090B","AS Roma":"#8E1F2F","Atalanta":"#1E71B8","Bologna":"#1A2F48","Cagliari":"#A6192E","Como":"#0B4EA2",
 "Fiorentina":"#5D2E8C","Frosinone":"#F2B705","Genoa":"#B1102F","Inter":"#0068A8","Juventus":"#2b2b2b","Lazio":"#7ABBE6",
 "Lecce":"#F9D923","Monza":"#E4002B","Napoli":"#12A0D7","Parma":"#FFD700","Sassuolo":"#00A859","Torino":"#8B1A1A",
 "Udinese":"#3a3a3a","Venezia":"#F26B1D",
 # Ligue 1
 "Angers":"#2b2b2b","Auxerre":"#0B5EA8","Estac Troyes":"#0F3E91","Le Havre":"#6DB1E3","Le Mans":"#F8C300","Lens":"#E5A800",
 "Lille":"#E01E13","Lorient":"#F26A21","Lyon":"#1B3F94","Marseille":"#2FAEE0","Monaco":"#E41B17","Nice":"#B3001B",
 "Paris FC":"#1A3A8A","Paris Saint Germain":"#004170","Rennes":"#E13327","Stade Brestois 29":"#E30613","Strasbourg":"#0066B3",
 "Toulouse":"#5E2B7E",
}
DEFAULT_RING = "#F6D33B"    # gold, used for a draw or an unknown club
DRAW_RING = "#9AA7A0"


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in c)


def _mix(c, other, t):
    return tuple(a + (b - a) * t for a, b in zip(c, other))


def _lum(c):
    r, g, b = (v / 255 for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def team_colour(team):
    return TEAM_COLOURS.get(team) or (DRAW_RING if team == "Draw" else DEFAULT_RING)


def ring(p, team="", uid=0):
    """Percentage dial coloured in the favoured club's colours."""
    base = _rgb(team_colour(team))
    light, dark = _mix(base, (255, 255, 255), .55), _mix(base, (0, 0, 0), .28)
    bright = _lum(base) > .42
    ink = "#1a1a14" if bright else "#ffffff"
    arc = _hex(_mix(base, (0, 0, 0), .62)) if bright else "#ffffff"
    gid = f"rg{uid}"
    r_arc = 2 * 3.14159 * 38
    return (f'<span class="stub-pct ring" role="img" aria-label="{p:.0f} percent"><svg viewBox="0 0 100 100">'
            f'<defs><radialGradient id="{gid}" cx=".35" cy=".3" r=".9"><stop offset="0" stop-color="{_hex(light)}"/>'
            f'<stop offset=".55" stop-color="{_hex(base)}"/><stop offset="1" stop-color="{_hex(dark)}"/></radialGradient></defs>'
            f'<circle class="r-shadow" cx="50" cy="54" r="44" style="fill:{_hex(_mix(base, (0, 0, 0), .55))};fill-opacity:.35"/>'
            f'<circle class="r-dial" cx="50" cy="50" r="46" style="fill:url(#{gid})"/>'
            f'<circle class="r-bg" cx="50" cy="50" r="38" style="stroke:{arc};stroke-opacity:.22"/>'
            f'<circle class="r-fg" cx="50" cy="50" r="38" stroke-dasharray="{r_arc * p / 100:.1f} {r_arc:.1f}" '
            f'transform="rotate(-90 50 50)" style="stroke:{arc}"/>'
            f'<text x="50" y="50" dominant-baseline="central" text-anchor="middle" style="fill:{ink}">{p:.0f}<tspan dy="-12" font-size="20">%</tspan></text>'
            f'</svg></span>')


def injury_list(items):
    items = [x for x in (items or []) if x.get("name")]
    if not items:
        return '<span class="none">None reported</span>'
    out = []
    for x in items:
        doubtful = "missing" not in (x.get("type") or "").lower()
        tag = "Doubtful" if doubtful else "Out"
        why = f" · {esc(x['reason'])}" if x.get("reason") else ""
        out.append(f'<span class="inj {"inj-q" if doubtful else "inj-out"}">{esc(x["name"])} <small>{tag}{why}</small></span>')
    return "".join(out)


def view_block(f):
    """Model v bookmakers, plus the reasons behind close calls and injury adjustments."""
    mk = f.get("market")
    notes = []
    if f.get("call_reason") and f["pick"] == "Draw":
        notes.append(f"<b>Called a draw:</b> the match is too close to separate and there is a warning sign ({esc(f['call_reason'])}).")
    elif f.get("low_data"):
        notes.append("<b>Low data:</b> one of these teams has fewer than 15 matches of recent league history, so its rating is a rough guess.")
    ie = f.get("injury_effect") or {}
    for side, team in (("home", f["home"]), ("away", f["away"])):
        e = ie.get(side) or {}
        bits = []
        if e.get("goals_lost_pct", 0) >= 1:
            bits.append(f"scoring cut by about {e['goals_lost_pct']:.0f}%")
        if e.get("defence_hit_pct", 0) >= 1:
            bits.append(f"opponent's goals up about {e['defence_hit_pct']:.0f}% (defence/keeper out)")
        if bits:
            who = f" – key absentees: {esc(', '.join(e['key_out']))}" if e.get("key_out") else ""
            notes.append(f"<b>{esc(team)}:</b> injuries and suspensions counted in the model, {'; '.join(bits)}{who}.")
    if not mk and not notes:
        return ""
    table = ""
    if mk:
        def r(label, h, d, a):
            return f'<tr><th>{label}</th><td>{h:.0f}%</td><td>{d:.0f}%</td><td>{a:.0f}%</td></tr>'
        table = (f'<table class="bk vm"><tr><th></th><th>{esc(short(f["home"]))}</th><th>Draw</th><th>{esc(short(f["away"]))}</th></tr>'
                 + r("Our model", f["home_pct"], f["draw_pct"], f["away_pct"])
                 + r("Bookmakers (average, margin removed)", mk["home"], mk["draw"], mk["away"]) + '</table>')
    note_html = "".join(f"<p class='vm-note'>{n}</p>" for n in notes)
    return f"""
      <section class="block">
        <h3>Model v bookmakers <span class="sub">where we agree and disagree</span></h3>
        {table}{note_html}
      </section>"""


BOOK_ORDER = ["William Hill", "Bet365", "BetVictor", "Betfair"]


def bookie_table(f):
    """1X2 prices from each bookmaker with a link to bet with them."""
    o = f.get("odds") or {}
    cols = [("home", f["home"]), ("draw", "Draw"), ("away", f["away"])]
    if not any((o.get(k) or {}).get("books") for k, _ in cols):
        return ""
    cfg = affiliate_config()
    best = {k: max(((o.get(k) or {}).get("books") or {"": 0}).values()) for k, _ in cols}
    rows = []
    for bk in BOOK_ORDER:
        prices = [((o.get(k) or {}).get("books") or {}).get(bk) for k, _ in cols]
        if not any(prices):
            continue
        cells = "".join(
            f'<td class="bk-p{" bk-best" if v and v >= best[k] else ""}">{f"{v:.2f}" if v else "–"}</td>'
            for (k, _), v in zip(cols, prices))
        c = cfg.get(bk) or {}
        link = (f'<a class="bk-go" href="{esc(c["url"])}" target="_blank" rel="{"sponsored " if c.get("aff") else ""}noopener nofollow">Bet</a>'
                if c.get("url") else "")
        rows.append(f'<tr><th>{esc(bk)}</th>{cells}<td>{link}</td></tr>')
    if not rows:
        return ""
    head = "".join(f"<th>{esc(short(n))}</th>" for _, n in cols)
    return f"""
      <section class="block bk-block">
        <h3>Compare bookmakers <span class="sub">match result prices · best price highlighted</span></h3>
        <table class="bk"><tr><th></th>{head}<th></th></tr>{''.join(rows)}</table>
        <p class="halves">Prices change often, so check the final price with the bookmaker. Links open the bookmaker's site and may be affiliate links. 18+ · <a href="{{prefix}}responsible-gambling/">Gamble responsibly</a></p>
      </section>"""


def mirror(rows):
    return "".join(f"<tr><td>{a}</td><th>{lbl}</th><td>{b}</td></tr>" for lbl, a, b in rows)


# ---------------------------------------------------------------- match panel

def render_match(f, i):
    day, time_, _ = kickoff(f)
    home, away = f["home"], f["away"]
    team, p, cap = most_likely(f)
    risk = (f'<span class="stub-risk">Draw risk · draw {f["draw_pct"]:.0f}%</span>' if draw_risk(f) else "")

    if f.get("referee"):
        avg = (f' <span class="ref-avg">({f["ref_cards"]:.1f} cards per game, {f["ref_games"]} games)</span>'
               if f.get("ref_cards") is not None else ' <span class="ref-avg">(no card history yet)</span>')
        ref = f'<p class="ref">Referee <b>{esc(f["referee"])}</b>{avg}</p>'
    else:
        ref = '<p class="ref">Referee <b>to be confirmed</b></p>'

    pl = f["players"]
    def dfd(side):
        d = pl[side].get("defender")
        return f"<span>{esc(d['name'])} <small>{d['sot']} on target</small></span>" if d else '<span class="none">No pick</span>'
    players = mirror([
        ("To score", names(f, pl["home"]["scorers"], home, "scorer"), names(f, pl["away"]["scorers"], away, "scorer")),
        ("To be booked", names(f, pl["home"]["bookings"], home, "booked"), names(f, pl["away"]["bookings"], away, "booked")),
        ("Defender shot on target", dfd("home"), dfd("away")),
    ])

    inj = f.get("injuries") or {"home": [], "away": []}
    inj_block = f"""
      <section class="block">
        <h3>Injuries &amp; suspensions <span class="sub">players ruled out are left out of the picks above</span></h3>
        <table class="mirror players"><tr class="names"><td>{esc(home)}</td><th></th><td>{esc(away)}</td></tr>{mirror([("Not available", injury_list(inj["home"]), injury_list(inj["away"]))])}</table>
      </section>"""

    g = f["goals"]
    goals = mirror([
        ("To score", pct(g["home"]["any"]), pct(g["away"]["any"])),
        ("Score in 1st half", pct(g["home"]["fh"]), pct(g["away"]["fh"])),
        ("Score in 2nd half", pct(g["home"]["sh"]), pct(g["away"]["sh"])),
        ("Expected goals", f"{f['xg_home']:.1f}", f"{f['xg_away']:.1f}"),
    ])

    fh, fa = f["form"]["home"], f["form"]["away"]
    def fv(s, k):
        return "—" if not s else (str(s["played"]) if k == "played" else pct(s[k]))
    form = mirror([("Played", fv(fh, "played"), fv(fa, "played")), ("Win", fv(fh, "win"), fv(fa, "win")),
                   ("Over 2.5 goals", fv(fh, "over25"), fv(fa, "over25")), ("Both teams scored", fv(fh, "btts"), fv(fa, "btts"))])
    small = [s["played"] for s in (fh, fa) if s]
    form_note = ('<p class="halves">Early-season sample: percentages are based on only a few games '
                 'and will settle as more are played.</p>') if small and min(small) < 5 else ""

    prev = "".join(f"""<tr><td class="pm-date">{esc(m['date'])}</td><td class="pm-h">{esc(m['home'])}</td>
          <td class="pm-score">{m['hg']}–{m['ag']}</td><td class="pm-a">{esc(m['away'])}</td></tr>""" for m in f["previous"])
    prev_block = f"""
      <section class="block"><h3>Last meetings</h3><table class="pm">{prev}</table></section>""" if prev else ""

    return f"""
    <article id="m{i}" class="match" role="tabpanel" hidden>
      <header class="match-head">
        <div class="kick">{esc(day)} · {esc(time_)}</div>
        <h2 class="fixture"><span>{esc(home)}</span><span class="vs">v</span><span>{esc(away)}</span></h2>
        {ref}
        <div class="threeway" aria-label="Result chances">
          <div class="tw-bar"><span class="tw-h" style="flex:{f['home_pct']}"></span><span class="tw-d" style="flex:{f['draw_pct']}"></span><span class="tw-a" style="flex:{f['away_pct']}"></span></div>
          <div class="tw-legend"><span>Home {f['home_pct']:.0f}%</span><span>Draw {f['draw_pct']:.0f}%</span><span>Away {f['away_pct']:.0f}%</span></div>
          <div class="picks3">
            {sel(f, "1x2", "home", f"{home} to win", odds_of(f, "home"), f["home_pct"] / 100, text=short(home))}
            {sel(f, "1x2", "draw", "Draw", odds_of(f, "draw"), f["draw_pct"] / 100)}
            {sel(f, "1x2", "away", f"{away} to win", odds_of(f, "away"), f["away_pct"] / 100, text=short(away))}
          </div>
        </div>
        <div class="markets">
          {meter("Over 2.5 goals", f["over25"],
                 sel(f, "ou25", "over25", "Over 2.5 goals", odds_of(f, "over25"), f["over25"] / 100, "Over")
                 + sel(f, "ou25", "under25", "Under 2.5 goals", odds_of(f, "under25"), 1 - f["over25"] / 100, "Under"))}
          {meter("Both teams to score", f["btts"],
                 sel(f, "btts", "btts_yes", "Both teams to score", odds_of(f, "btts_yes"), f["btts"] / 100, "Yes")
                 + sel(f, "btts", "btts_no", "Both teams to score - No", odds_of(f, "btts_no"), 1 - f["btts"] / 100, "No"))}
          {cards_block(f)}
        </div>
        <div class="stub">
          <span class="stub-label" style="background:{_hex(_mix(_rgb(team_colour(team)), (0, 0, 0), .5))}">Favoured</span>
          {risk}
          <span class="stub-team">{esc(team)}</span>
          {ring(p, team, f["id"])}
          <span class="stub-cap">{cap}</span>
        </div>
      </header>
      {view_block(f)}
      <section class="block">
        <h3>Players to watch</h3>
        <table class="mirror players"><tr class="names"><td>{esc(home)}</td><th></th><td>{esc(away)}</td></tr>{players}</table>
      </section>
      {bookie_table(f)}
      {inj_block}
      <section class="block">
        <h3>Goals</h3>
        <table class="mirror">{goals}</table>
        <p class="halves">Chance of a goal in the 1st half <b>{pct(g['match_fh'])}</b> · 2nd half <b>{pct(g['match_sh'])}</b></p>
      </section>
      <section class="block">
        <h3>This season <span class="sub">home record v away record</span></h3>
        <table class="mirror">{form}</table>{form_note}
      </section>
      {prev_block}
    </article>"""


def chip(f, i, href="#"):
    day, time_, _ = kickoff(f)
    team, p, _ = most_likely(f)
    risk = " · draw risk" if draw_risk(f) else ""
    tag = "a" if href != "#" else "button"
    attr = (f'href="{href}#m{i}"' if href != "#" else f'role="tab" data-tab="m{i}" aria-controls="m{i}" aria-selected="false"')
    return f"""
      <{tag} class="chip" {attr}>
        <span class="chip-when">{esc(day)} {esc(time_)}</span>
        <span class="chip-teams">{esc(short(f['home']))} <i>v</i> {esc(short(f['away']))}</span>
        <span class="chip-pick">{esc(short(team))} {p:.0f}%{risk}</span>
      </{tag}>"""


# ---------------------------------------------------------------- pages

def league_nav(leagues, current, prefix):
    links = [f'<a href="{prefix}" class="lg{" on" if current is None else ""}">All leagues</a>']
    for d in leagues:
        on = " on" if current == d["league"] else ""
        links.append(f'<a href="{prefix}{d["league"]}/" class="lg{on}">{esc(d["name"])}</a>')
    links.append(f'<a href="{prefix}track-record/" class="lg lg-tr{" on" if current == "track-record" else ""}">How we did</a>')
    return '<nav class="leagues" aria-label="Leagues">' + "".join(links) + "</nav>"


def track_record_page(leagues, upd):
    tr = os.path.join(BASE_DIR, "data", "track_record")
    try:
        with open(os.path.join(tr, "matches.json"), encoding="utf-8") as fh:
            matches = json.load(fh)
    except (FileNotFoundError, ValueError):
        matches = []
    summary = {"overall": {"matches": 0}, "leagues": {}}
    if SHOW_TRACK_RECORD:       # totals and percentages: private, only when you build it on your own computer
        try:
            with open(os.path.join(tr, "summary.json"), encoding="utf-8") as fh:
                summary = json.load(fh)
        except (FileNotFoundError, ValueError):
            pass
    o = summary["overall"]
    n = len(matches)

    def rate(a, b):
        return f"{a} of {b} <small>({100 * a / b:.0f}%)</small>" if b else "—"

    if not n:
        body = '<section class="block"><p>No finished matches yet. Results appear here the morning after each game.</p></section>'
    else:
        first = min(m["kickoff"] for m in matches)[:10]
        since = datetime.fromisoformat(first).strftime("%d %b %Y")
        private = ""
        if SHOW_TRACK_RECORD:
            hero = f"""
      <section class="tr-hero">
        <div class="tr-big"><b>{100 * o['result_correct'] / n:.0f}%</b><span>of match results called right<br>{o['result_correct']} of {n} matches since {since}</span></div>
        <p class="tr-calib">Our picks carried an average chance of <b>{o['avg_pick_pct']:.0f}%</b>. Over many games a well-calibrated model lands close to that figure; good weeks and bad weeks even out.</p>
      </section>"""
            mk = [
                ("Over 2.5 goals", o.get("over25_expected"), o.get("over25_happened"), rate(o.get("over25_correct", 0), n), n),
                ("Both teams to score", o.get("btts_expected"), o.get("btts_happened"), rate(o.get("btts_correct", 0), n), n),
                ("Over 4.5 cards", o.get("cards5_expected"), o.get("cards5_happened"), rate(o.get("cards5_correct", 0), o.get("cards_matches", 0)), o.get("cards_matches", 0)),
                *([("Cards per match <small>(average)</small>", o["cards_exp_avg"], o["cards_actual_avg"],
                    f"typical miss ±{o['cards_mae']:.1f}", None)] if o.get("cards_exp_avg") is not None else []),
                ("Players to score", o.get("scorers_expected"), o.get("scorers_hits"), f"{o.get('scorers_picks', 0)} picks", None),
                ("Players to be booked", o.get("bookings_expected"), o.get("bookings_hits"), f"{o.get('bookings_picks', 0)} picks", None),
            ]
            mk_rows = "".join(f"<tr><th>{a}</th><td>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d, _ in mk)
            markets = f"""
      <section class="block"><h3>Markets <span class="sub">how often it happened v how often the model expected it</span></h3>
        <table class="tr-table"><tr><th></th><td>Model expected</td><td>Happened</td><td>Calls right</td></tr>{mk_rows}</table></section>"""
            lg_rows = "".join(
                f"<tr><th><a href='../{k}/'>{esc(v['name'])}</a></th><td>{v['matches']}</td><td>{rate(v['result_correct'], v['matches'])}</td>"
                f"<td>{v['scorers_hits']} of {v['scorers_picks']}</td></tr>"
                for k, v in sorted(summary["leagues"].items(), key=lambda kv: LEAGUE_ORDER.index(kv[0]) if kv[0] in LEAGUE_ORDER else 99))
            by_league = f"""
      <section class="block"><h3>By league</h3>
        <table class="tr-table"><tr><th></th><td>Matches</td><td>Results right</td><td>Scorer picks</td></tr>{lg_rows}</table></section>"""
            private = hero + markets + by_league
        mrows = []
        for m in matches[:60 if SHOW_TRACK_RECORD else 200]:
            d = datetime.fromisoformat(m["kickoff"][:19]).strftime("%d %b")
            mark = '<span class="ok">✓</span>' if m["correct"] else '<span class="no">✗</span>'
            pick = "Draw" if m["pick"] == "Draw" else (m["home"] if m["pick"] == "Home" else m["away"])
            sc = ", ".join(("<b>" if x["hit"] else "") + esc(x["name"]) + ("</b>" if x["hit"] else "") for x in m["scorers"])
            mrows.append(f"""<tr><td class="pm-date">{d}</td><td>{esc(m['league_name'])}</td>
              <td class="tr-m">{esc(m['home'])} <b>{m['score']}</b> {esc(m['away'])}</td>
              <td>{esc(short(pick))} {m['pick_pct']:.0f}% {mark}</td><td class="tr-sc">{sc}</td></tr>""")
        recent = f"""
      <section class="block"><h3>Every match <span class="sub">our pick and the result (&#10003; right, &#10007; wrong), with scorer picks (bold = scored)</span></h3>
        <div class="tr-scroll"><table class="tr-list">{''.join(mrows)}</table></div></section>"""
        body = private + recent
    body += """
      <section class="block tr-method"><h3>How this is checked</h3>
        <p>Only predictions published before kick-off count, and each match uses the last version published before it started.
        Every prediction is saved in the site's public history, so nothing can be changed afterwards.
        Results, scorers and bookings come from API-Football and are checked automatically each morning.</p>
        <p><b>Model change, 23 Oct 2026:</b> predictions now take injuries and suspensions into account, flag teams with little recent league history,
        and call a close match a draw when there is a warning sign (low data, or the bookmakers disagree). Matches before this date used the earlier model.</p></section>"""
    return page("How we did – FootyPredicts",
                "Our published picks next to the results.",
                league_nav(leagues, "track-record", "../"), f"Results · updated {upd}", "", body, "../")


def affiliate_config():
    try:
        with open(os.path.join(BASE_DIR, "affiliates.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        raw = {}
    return {k: {"url": v.get("tracking_url") or v.get("url") or "", "aff": bool(v.get("tracking_url"))}
            for k, v in raw.items() if isinstance(v, dict)}


def responsible_page(leagues):
    body = """
      <section class="block"><h3>Responsible gambling</h3>
        <p><b>You must be 18 or over to gamble.</b> FootyPredicts shows football predictions and prices from bookmakers.
        We do not take bets, hold money or run an account for you.</p>
        <p>Predictions are probabilities. Even a good model is wrong often, and bookmakers build a margin into every price,
        so most people who bet lose money over time. Never bet money you need for rent, bills or food, and never chase losses.</p>
        <p>Set a deposit limit with your bookmaker, take regular breaks, and stop if it stops being fun.</p></section>
      <section class="block"><h3>Free, confidential help</h3>
        <ul>
          <li><a href="https://www.begambleaware.org" rel="noopener">BeGambleAware.org</a> – advice and support</li>
          <li>National Gambling Helpline – <b>0808 8020 133</b> (free, 24 hours)</li>
          <li><a href="https://www.gamstop.co.uk" rel="noopener">GAMSTOP</a> – block yourself from UK online gambling sites</li>
          <li><a href="https://www.gamcare.org.uk" rel="noopener">GamCare</a> – support and live chat</li>
        </ul></section>
      <section class="block"><h3>How this site is funded</h3>
        <p>Where we link to a bookmaker, the link may be an <b>affiliate link</b>: if you sign up through it, we may earn a commission.
        Links do not change our predictions, and the results page shows how our picks turned out.</p></section>"""
    return page("Responsible gambling – FootyPredicts",
                "Help with gambling, how FootyPredicts is funded, and an 18+ reminder.",
                league_nav(leagues, None, "../"), "Responsible gambling", "", body, "../")


def page(title, desc, nav, sub, chips, body, prefix):
    html = PAGE.format(title=esc(title), desc=esc(desc), nav=nav, sub=sub, chips=chips, body=body,
                       css=CSS, extra_css=EXTRA_CSS, prefix=prefix)
    html = html.replace("{prefix}", prefix)
    html = html.replace("__DECOR__", DECOR_DEFS)
    return html.replace("__BOOKIES__", json.dumps(affiliate_config()).replace("</", "<\\/"))


def build():
    leagues = []
    for key in LEAGUE_ORDER:
        path = os.path.join(SITE_DATA, f"{key}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("fixtures"):
                leagues.append(d)
    if not leagues:
        raise SystemExit("No prediction files in data/site/ - run: python -m pipeline.run")
    updated = max(datetime.fromisoformat(d["updated"]) for d in leagues).astimezone()
    upd = updated.strftime("%d %b, %H:%M")

    # league pages
    for d in leagues:
        fx = d["fixtures"]
        first, last = kickoff(fx[0])[2], kickoff(fx[-1])[2]
        sub = f"{esc(d['name'])} · {first:%d %b} – {last:%d %b %Y} · updated {upd}"
        html = page(f"{d['name']} predictions – FootyPredicts",
                    f"{d['name']} match predictions: result chances, goals, cards and players for every fixture.",
                    league_nav(leagues, d["league"], "../"), sub,
                    '<nav class="chips" role="tablist" aria-label="Fixtures">' + "".join(chip(f, i) for i, f in enumerate(fx)) + "</nav>",
                    "".join(render_match(f, i) for i, f in enumerate(fx)), "../")
        os.makedirs(os.path.join(OUT_DIR, d["league"]), exist_ok=True)
        with open(os.path.join(OUT_DIR, d["league"], "index.html"), "w", encoding="utf-8") as fh:
            fh.write(html)

    # front page: every league's upcoming matches
    sections = []
    for d in leagues:
        rows = []
        for i, f in enumerate(d["fixtures"]):
            day, time_, _ = kickoff(f)
            team, p, _ = most_likely(f)
            rows.append(f"""
          <a class="row" href="{d['league']}/#m{i}">
            <span class="row-when">{esc(day)} {esc(time_)}</span>
            <span class="row-teams">{esc(f['home'])} <i>v</i> {esc(f['away'])}</span>
            <span class="row-bar"><span class="tw-h" style="flex:{f['home_pct']}"></span><span class="tw-d" style="flex:{f['draw_pct']}"></span><span class="tw-a" style="flex:{f['away_pct']}"></span></span>
            <span class="row-pick">{esc(short(team))} <b>{p:.0f}%</b>{'<em>draw risk</em>' if draw_risk(f) else ''}</span>
          </a>""")
        sections.append(f"""
      <section class="league-block">
        <h2><a href="{d['league']}/">{esc(d['name'])}</a> <span class="sub">{esc(d['country'])}</span></h2>
        <div class="rows">{''.join(rows)}</div>
      </section>""")
    html = page("FootyPredicts – football predictions for Europe's top leagues",
                "Match-by-match predictions for the Premier League, La Liga, Bundesliga, Serie A and Ligue 1.",
                league_nav(leagues, None, ""), f"Upcoming matches in Europe's top five leagues · updated {upd}",
                "", "".join(sections), "")
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    os.makedirs(os.path.join(OUT_DIR, "track-record"), exist_ok=True)
    with open(os.path.join(OUT_DIR, "track-record", "index.html"), "w", encoding="utf-8") as fh:
        fh.write(track_record_page(leagues, upd))
    os.makedirs(os.path.join(OUT_DIR, "responsible-gambling"), exist_ok=True)
    with open(os.path.join(OUT_DIR, "responsible-gambling", "index.html"), "w", encoding="utf-8") as fh:
        fh.write(responsible_page(leagues))
    open(os.path.join(OUT_DIR, ".nojekyll"), "w").close()
    print(f"Built site: {len(leagues)} leagues, {sum(len(d['fixtures']) for d in leagues)} fixtures")


CSS = r""":root {
  --pitch:#0f3d2e; --pitch-2:#145039; --chalk:#f6f7f2; --paper:#ffffff;
  --ink:#14211b; --muted:#5d6b64; --line:#dfe5df; --flood:#f6d33b; --flood-ink:#2a2300;
  --home:#145039; --draw:#9aa7a0; --away:#c9a227;
}
* { box-sizing:border-box; }
html { background:var(--chalk); }
body { margin:0; font:16px/1.5 Barlow,system-ui,sans-serif; color:var(--ink); background:var(--chalk); }
.cond { font-family:"Barlow Condensed",Barlow,sans-serif; }

/* top bar */
.top { background:var(--pitch); color:#fff; padding:22px 16px 0; position:relative; overflow:hidden; }
.top::after { content:""; position:absolute; inset:auto -10% -140px auto; width:420px; height:420px;
  border:2px solid rgba(255,255,255,.08); border-radius:50%; pointer-events:none; }
.top-in { max-width:960px; margin:0 auto; position:relative; z-index:1; }
.brand { display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.brand h1 { margin:0; font:800 clamp(30px,6vw,44px)/1 "Barlow Condensed",sans-serif; letter-spacing:.01em; }
.brand h1 span { color:var(--flood); }
.brand p { margin:0; color:rgba(255,255,255,.72); font-size:14px; }

/* fixture chips */
.chips { display:flex; gap:8px; overflow-x:auto; padding:18px 0 16px; scroll-snap-type:x proximity; scrollbar-width:thin; }
.chip { flex:0 0 auto; scroll-snap-align:start; display:grid; gap:1px; text-align:left; cursor:pointer;
  padding:9px 12px 10px; border-radius:10px; border:1px solid rgba(255,255,255,.16);
  background:rgba(255,255,255,.06); color:#fff; font:inherit; }
.chip:hover { background:rgba(255,255,255,.12); }
.chip[aria-selected="true"] { background:#fff; color:var(--ink); border-color:#fff; }
.chip:focus-visible, .match :focus-visible { outline:3px solid var(--flood); outline-offset:2px; }
.chip-when { font-size:12px; opacity:.75; }
.chip-teams { font:700 17px/1.15 "Barlow Condensed",sans-serif; white-space:nowrap; }
.chip-teams i { font-style:normal; opacity:.55; font-weight:500; }
.chip-pick { font-size:12px; font-weight:600; color:var(--flood); }
.chip[aria-selected="true"] .chip-pick { color:#8a6d00; }

/* match */
main { max-width:960px; margin:0 auto; padding:20px 16px 56px; }
.match-head { position:relative; background:var(--paper); border-radius:18px; padding:22px 22px 26px;
  border:1px solid var(--line); overflow:hidden; }
.kick { color:var(--muted); font-size:14px; }
.fixture { margin:6px 0 16px; display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 12px;
  font:800 clamp(30px,6.4vw,52px)/1 "Barlow Condensed",sans-serif; letter-spacing:-.005em; padding-right:6px; }
.ref { margin:-6px 0 16px; font-size:19px; color:var(--ink); }
.ref b { font:700 24px/1.1 "Barlow Condensed",sans-serif; }
.ref-avg { color:var(--muted); font-size:16px; }
.fixture .vs { font-weight:500; color:var(--muted); font-size:.6em; }

.threeway { margin:0 0 18px; max-width:520px; }
.tw-bar { display:flex; height:10px; border-radius:6px; overflow:hidden; gap:2px; }
.tw-h { background:var(--home); } .tw-d { background:var(--draw); } .tw-a { background:var(--away); }
.tw-legend { display:flex; justify-content:space-between; font-size:13px; color:var(--muted); margin-top:5px; }

.markets { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px 20px; max-width:620px; }
.meter-top { display:flex; justify-content:space-between; gap:8px; font-size:14px; color:var(--muted); }
.meter-top b { color:var(--ink); font:700 22px/1 "Barlow Condensed",sans-serif; }
.meter-track { height:6px; background:#edf1ed; border-radius:4px; margin-top:6px; overflow:hidden; }
.meter-fill { height:100%; background:var(--pitch-2); border-radius:4px; }
.meter-note { font-size:12px; color:var(--muted); margin-top:3px; }
.meter-note.is-value { color:#7a5d00; font-weight:600; }
.halves { margin:10px 2px 0; font-size:14px; color:var(--muted); }
.halves b { color:var(--ink); }

/* the "back" stub - bottom right */
.stub { position:absolute; right:0; bottom:0; display:grid; justify-items:end; gap:0;
  background:var(--flood); color:var(--flood-ink); padding:14px 20px 14px 26px; min-width:190px;
  border-top-left-radius:16px; }
.stub { background:linear-gradient(155deg,#ffe56b 0%,#f6d33b 45%,#dcb41d 100%);
  box-shadow:-6px -6px 18px rgba(255,255,255,.7) inset, 6px 8px 14px rgba(120,90,0,.25) inset, -10px -6px 24px rgba(15,61,46,.18); }
.stub::before { content:""; position:absolute; left:-1px; top:12px; bottom:12px; width:0;
  border-left:3px dotted rgba(42,35,0,.35); }
.stub-label { font-size:13px; font-weight:600; }
.stub-team { font:800 24px/1.05 "Barlow Condensed",sans-serif; text-align:right; max-width:230px; }
.stub-pct { font:800 46px/.95 "Barlow Condensed",sans-serif; margin-top:2px; }
.stub-pct small { font-size:.5em; margin-left:1px; }
.stub-cap { font-size:12px; opacity:.8; }
.stub-risk { font-size:12px; font-weight:700; background:var(--flood-ink); color:var(--flood);
  padding:2px 8px; border-radius:999px; margin:2px 0 4px; }
.match-head { padding-bottom:26px; }
.markets { margin-right:220px; }

/* blocks */
.block { margin-top:26px; }
.block h3 { margin:0 0 10px; font:700 22px/1.1 "Barlow Condensed",sans-serif; }
.block h3 .sub { font:400 14px Barlow,sans-serif; color:var(--muted); margin-left:6px; }
.mirror { width:100%; border-collapse:collapse; background:var(--paper); border:1px solid var(--line); border-radius:14px; overflow:hidden; }
.mirror td, .mirror th { padding:10px 14px; border-top:1px solid var(--line); vertical-align:top; }
.mirror tr:first-child td, .mirror tr:first-child th { border-top:0; }
.mirror td { width:40%; }
.mirror td:last-child { text-align:right; }
.mirror th { width:20%; text-align:center; font-weight:500; color:var(--muted); font-size:13px; }
.players td span { display:block; font-weight:600; }
.players td small { font-weight:400; color:var(--muted); margin-left:4px; }
.players .names td { font:700 18px/1.2 "Barlow Condensed",sans-serif; background:#f1f4f0; }
.players .names th { background:#f1f4f0; }
.bk-pick { max-width:960px; margin:0 auto; padding:10px 16px 0; font-size:14px; }
.bk-pick select { font:inherit; padding:6px 10px; border-radius:8px; border:1px solid var(--line); background:var(--paper); margin-left:6px; }
button.sel.na { opacity:.45; cursor:not-allowed; }
.betwith { display:block; text-align:center; margin:10px 0 4px; padding:12px 16px; border-radius:10px; background:var(--flood); color:var(--flood-ink); font:700 18px "Barlow Condensed",sans-serif; text-decoration:none; }
.inj-out small { color:#b3261e; }
.inj-q small { color:#9a6700; }
.none { color:var(--muted); font-weight:400 !important; }
.mirror:not(.players) td { font:700 20px/1 "Barlow Condensed",sans-serif; }

.pm { width:100%; border-collapse:collapse; font-size:15px; }
.pm td { padding:8px 6px; border-bottom:1px solid var(--line); }
.pm-date { color:var(--muted); white-space:nowrap; font-size:13px; width:1%; padding-right:14px !important; }
.pm-h { text-align:right; }
.pm-score { text-align:center; font:700 18px/1 "Barlow Condensed",sans-serif; width:64px; white-space:nowrap; }

.foot a { color:inherit; }
.foot p { margin:0 0 8px; }
.foot { max-width:960px; margin:0 auto; padding:0 16px 40px; color:var(--muted); font-size:13px; }

@media (max-width:700px) {
  .match-head { padding:18px 16px 0; }
  .markets { grid-template-columns:1fr; margin-right:0; max-width:none; }
  .stub { position:relative; margin:20px -16px 0; border-radius:0; border-top-left-radius:0;
    grid-template-columns:auto 1fr auto; align-items:end; justify-items:start; gap:2px 12px; padding:14px 16px; min-width:0; }
  .stub::before { display:none; }
  .stub-label { grid-column:1; grid-row:1; }
  .stub-team { grid-column:1 / 3; grid-row:2; text-align:left; }
  .stub-pct { grid-column:3; grid-row:1 / 3; align-self:center; }
  .stub-cap { grid-column:1 / 4; grid-row:3; }
  .stub-risk { grid-column:1 / 4; grid-row:4; justify-self:start; margin-top:6px; }
  .mirror tr { display:grid; grid-template-columns:1fr 1fr; border-top:1px solid var(--line); }
  .mirror tr:first-child { border-top:0; }
  .mirror td, .mirror th { display:block; width:auto; border-top:0; padding:8px 12px; }
  .mirror th { grid-column:1 / 3; grid-row:1; text-align:center; font-size:12px; padding:8px 12px 0; }
  .mirror .names th { display:none; }
  .players td small { display:block; margin-left:0; }
  .pm-date { display:none; }
}
@media (prefers-reduced-motion:no-preference) {
  .meter-fill { transition:width .5s ease; }
}"""

EXTRA_CSS = r"""
/* motion when a match opens */
@media (prefers-reduced-motion:no-preference) {
  .match.play .r-fg { animation:fp-sweep 1.1s cubic-bezier(.2,.8,.2,1) both; }
  .match.play .ring svg { animation:fp-pop .7s cubic-bezier(.2,1.4,.4,1) both; transform-origin:50% 50%; }
  .match.play .tw-bar { animation:fp-grow .8s cubic-bezier(.2,.8,.2,1) both; transform-origin:left center; }
  .match.play .meter-fill { animation:fp-bar .9s cubic-bezier(.2,.8,.2,1) .15s both; }
  .match.play .stub-team { animation:fp-slide .6s cubic-bezier(.2,.8,.2,1) .15s both; }
  .match.play .stub-label { animation:fp-slide .6s cubic-bezier(.2,.8,.2,1) both; }
  .match.play .picks3 .sel, .match.play .meter-sel .sel { animation:fp-rise .5s ease both; }
  .match.play .picks3 .sel:nth-child(2) { animation-delay:.08s; } .match.play .picks3 .sel:nth-child(3) { animation-delay:.16s; }
  .match.play .block { animation:fp-rise .6s ease both; }
  .match.play .block:nth-of-type(1) { animation-delay:.25s; } .match.play .block:nth-of-type(2) { animation-delay:.35s; }
  .match.play .block:nth-of-type(3) { animation-delay:.45s; } .match.play .block:nth-of-type(n+4) { animation-delay:.55s; }
  @keyframes fp-sweep { from { stroke-dasharray:0 240; } }
  @keyframes fp-pop { from { transform:scale(.6) rotate(-25deg); opacity:0; } }
  @keyframes fp-grow { from { transform:scaleX(0); } }
  @keyframes fp-bar { from { width:0; } }
  @keyframes fp-slide { from { opacity:0; transform:translateX(26px); } }
  @keyframes fp-rise { from { opacity:0; transform:translateY(14px); } }
}
.vm th:first-child { max-width:200px; }
.vm td { font:700 20px/1 "Barlow Condensed",sans-serif; }
.vm-note { margin:10px 0 0; font-size:15px; color:var(--ink); }
/* depth + football decoration */
.bk { width:100%; border-collapse:collapse; background:var(--paper); border:1px solid var(--line); border-radius:14px; overflow:hidden; box-shadow:0 8px 16px -10px rgba(15,61,46,.3); }
.bk th, .bk td { padding:10px 12px; border-top:1px solid var(--line); text-align:center; }
.bk tr:first-child th { border-top:0; font-size:13px; color:var(--muted); font-weight:600; background:#f1f4f0; }
.bk th:first-child { text-align:left; font-weight:700; }
.bk-p { font:700 20px/1 "Barlow Condensed",sans-serif; }
.bk-best { color:#0f3d2e; background:linear-gradient(180deg,#fff7c9,#f6e27a); border-radius:8px; box-shadow:inset 0 1px 0 #fff; }
.bk-go { display:inline-block; padding:7px 18px; border-radius:999px; background:var(--pitch); color:#fff; text-decoration:none; font:700 16px "Barlow Condensed",sans-serif; letter-spacing:.06em; box-shadow:0 3px 0 #0a2a20; }
.bk-go:hover { transform:translateY(-1px); }
.bk-block .halves a { color:inherit; }
.head-kicker { position:absolute; left:8px; bottom:4px; width:260px; height:236px; pointer-events:none; z-index:0;
  filter:drop-shadow(0 10px 8px rgba(15,61,46,.28)); }
@media (max-width:900px) { .head-kicker { display:none; } }
.stub { min-width:250px !important; padding:0 26px 22px 0 !important; gap:2px !important; }
.stub-label { background:var(--pitch); color:#fff; font:700 14px "Barlow Condensed",sans-serif !important; letter-spacing:.14em; text-transform:uppercase;
  padding:5px 14px; border-radius:999px; box-shadow:0 3px 0 #0a2a20, 0 6px 10px -3px rgba(15,61,46,.5); }
.stub-team { font-size:44px !important; line-height:1 !important; margin-top:10px; text-shadow:0 6px 10px rgba(15,61,46,.2); max-width:300px !important; }
.stub .ring { margin:8px 0 4px !important; }
.stub .ring svg { width:176px !important; height:176px !important; filter:drop-shadow(0 12px 12px rgba(15,61,46,.35)); }
.stub .ring text { font-size:36px !important; }
.stub-cap { font-size:14px !important; font-weight:600; opacity:1 !important; color:var(--muted); letter-spacing:.04em; }
.markets { margin-right:290px !important; }
@media (max-width:900px) { .markets { margin-right:0 !important; } .stub { position:relative !important; margin:18px 0 0 !important; min-width:0 !important; padding:0 !important; } }
@media (max-width:700px) { .stub-team { font-size:34px !important; } .stub .ring svg { width:132px !important; height:132px !important; } }
.stub { background:none !important; box-shadow:none !important; border-radius:0 !important; padding-right:22px !important; padding-bottom:18px !important; }
.stub::before { display:none !important; }
@media (max-width:700px) { .stub { margin:14px 0 0 !important; padding:0 0 4px !important; } }
.match-head { box-shadow:0 1px 0 #fff inset, 0 2px 0 rgba(15,61,46,.06), 0 10px 22px -8px rgba(15,61,46,.28), 0 28px 44px -26px rgba(15,61,46,.35);
  background:linear-gradient(180deg,#ffffff 0%,#f7faf6 100%); }
.head-ball { position:absolute; top:-26px; right:-22px; width:128px; height:128px; opacity:.95; pointer-events:none;
  filter:drop-shadow(0 12px 8px rgba(15,61,46,.3)); transform:rotate(18deg); }
.fixture, .kick, .ref, .threeway, .markets { position:relative; z-index:1; }
.threeway .tw-bar { height:12px; box-shadow:inset 0 2px 3px rgba(0,0,0,.25), 0 1px 0 #fff; }
.tw-h, .tw-d, .tw-a { background-image:linear-gradient(180deg,rgba(255,255,255,.35),rgba(0,0,0,.12)); }
.meter-track { box-shadow:inset 0 1px 3px rgba(0,0,0,.2); height:8px; }
.meter-fill { background-image:linear-gradient(180deg,#2b7a57,#0f3d2e); box-shadow:0 1px 2px rgba(0,0,0,.3), inset 0 1px 0 rgba(255,255,255,.35); }
button.sel { box-shadow:0 2px 0 rgba(15,61,46,.18), 0 5px 8px -3px rgba(15,61,46,.25), inset 0 1px 0 rgba(255,255,255,.8);
  transition:transform .12s ease, box-shadow .12s ease; }
button.sel:hover:not(:disabled) { transform:translateY(-1px); box-shadow:0 3px 0 rgba(15,61,46,.2), 0 9px 12px -4px rgba(15,61,46,.3), inset 0 1px 0 #fff; }
button.sel:active:not(:disabled), button.sel[aria-pressed="true"] { transform:translateY(1px); box-shadow:inset 0 2px 4px rgba(0,0,0,.25); }
.mirror, .tr-hero, .row { box-shadow:0 1px 0 #fff inset, 0 8px 16px -10px rgba(15,61,46,.3); }
.decor { position:fixed; top:110px; bottom:0; width:calc((100vw - 960px) / 2 - 24px); max-width:240px; pointer-events:none; display:none; z-index:0; }
.decor-l { left:12px; } .decor-r { right:12px; }
.decor svg { position:absolute; filter:drop-shadow(0 14px 10px rgba(15,61,46,.28)); }
.d-ball { width:84px; height:84px; } .d-flag { width:78px; height:117px; left:50%; top:34%; margin-left:-30px; }
.d-goal { width:170px; height:121px; right:0; top:8%; }
.d1 { left:30%; top:12%; transform:rotate(-20deg); } .d2 { left:8%; top:68%; width:62px; height:62px; transform:rotate(40deg); }
.d3 { right:34%; top:46%; width:96px; height:96px; transform:rotate(25deg); } .d4 { right:10%; top:78%; width:58px; height:58px; }
main, .top, .foot { position:relative; z-index:1; }

@media (prefers-reduced-motion:no-preference) {
  .d1, .d3 { animation:fp-float 7s ease-in-out infinite; } .d2, .d4 { animation:fp-float 9s ease-in-out -3s infinite; }
  @keyframes fp-float { 0%,100% { translate:0 0; } 50% { translate:0 -12px; } }
}
@media (max-width:700px) { .head-ball { width:64px; height:64px; top:-16px; right:-18px; opacity:.85; } }

/* cards */
.cards-box .meter-top b { font-size:26px; }
.cards-split { display:flex; justify-content:space-between; font-size:13px; color:var(--muted); margin:2px 0 8px; }
.cards-box .meter { margin-top:8px; }
.cards-box .meter .meter-top b { font-size:18px; }

/* track record */
.lg-tr { border-style:dashed; }
.tr-hero { background:var(--paper); border:1px solid var(--line); border-radius:18px; padding:22px; display:grid; gap:10px; }
.tr-big { display:flex; align-items:center; gap:18px; }
.tr-big b { font:800 clamp(56px,10vw,84px)/1 "Barlow Condensed",sans-serif; color:var(--pitch); }
.tr-big span { font-size:17px; line-height:1.35; }
.tr-calib { margin:0; color:var(--muted); max-width:62ch; }
.tr-calib b { color:var(--ink); }
.tr-table { width:100%; border-collapse:collapse; background:var(--paper); border:1px solid var(--line); border-radius:14px; overflow:hidden; }
.tr-table th, .tr-table td { padding:10px 14px; border-top:1px solid var(--line); text-align:left; }
.tr-table tr:first-child td { color:var(--muted); font-size:13px; border-top:0; }
.tr-table tr:first-child th { border-top:0; }
.tr-table td { font:700 19px/1.1 "Barlow Condensed",sans-serif; }
.tr-table td small { font:400 13px Barlow,sans-serif; color:var(--muted); }
.tr-table th a { color:var(--ink); }
.tr-scroll { overflow-x:auto; }
.tr-list { width:100%; border-collapse:collapse; font-size:14px; }
.tr-list td { padding:8px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
.tr-list .tr-m { white-space:nowrap; }
.tr-list .tr-sc { color:var(--muted); font-size:13px; }
.tr-list .tr-sc b { color:var(--ink); }
.ok { color:#1d7a46; font-weight:800; }
.no { color:#b3261e; font-weight:800; }
.tr-method p { color:var(--muted); max-width:70ch; }
@media (max-width:700px) { .tr-big { flex-direction:column; align-items:flex-start; gap:6px; } .tr-table th, .tr-table td { padding:8px 10px; } }

/* clickable prices */
.picks3 { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; margin-top:10px; }
.meter-sel { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.sel { display:inline-flex; align-items:baseline; gap:6px; font:inherit; font-size:13px; color:var(--ink);
  background:#fff; border:1px solid var(--line); border-radius:9px; padding:6px 9px; cursor:pointer; text-align:left; }
button.sel:hover { border-color:var(--pitch-2); }
.sel b { font:700 18px/1 "Barlow Condensed",sans-serif; }
.sel small { color:var(--muted); font-size:11px; }
.sel[aria-pressed="true"] { background:var(--pitch); color:#fff; border-color:var(--pitch); }
.sel[aria-pressed="true"] small { color:rgba(255,255,255,.75); }
.picks3 .sel { justify-content:space-between; flex-wrap:wrap; }
.picks3 .sel-l { font-weight:600; flex:1 1 100%; }
.none-price { cursor:default; color:var(--muted); border-style:dashed; }
.pl { display:block; margin:2px 0; }
.pl .sel { padding:3px 7px; margin-left:4px; vertical-align:middle; }
.pl .sel b { font-size:15px; }
.mirror td:last-child .pl { text-align:right; }
.markets { margin-right:220px; }

/* ring */
.ring svg { width:96px; height:96px; display:block; }
.ring .r-shadow { fill:rgba(42,35,0,.28); filter:blur(2.5px); }
.ring .r-dial { fill:url(#fp-dial-g); stroke:rgba(255,255,255,.55); stroke-width:1.2; }
.ring .r-bg { fill:none; stroke:rgba(42,35,0,.2); stroke-width:9; }
.ring .r-fg { fill:none; stroke:url(#fp-ring-g); stroke-width:9; stroke-linecap:round; filter:drop-shadow(0 1.5px 1px rgba(0,0,0,.35)); }
.ring text { font:800 34px "Barlow Condensed",sans-serif; fill:var(--flood-ink); }
.stub .ring { margin:4px 0 2px; }

/* bet slip */
.slip { position:fixed; right:16px; bottom:16px; z-index:20; width:min(360px, calc(100vw - 32px));
  background:var(--paper); border:1px solid var(--line); border-radius:16px;
  box-shadow:0 12px 34px rgba(15,61,46,.22); overflow:hidden; }
.slip[hidden] { display:none; }
.slip-head { width:100%; display:flex; justify-content:space-between; align-items:center; gap:10px; cursor:pointer;
  background:var(--pitch); color:#fff; border:0; padding:12px 16px; font:700 18px "Barlow Condensed",sans-serif; }
.slip-head b { color:var(--flood); }
.slip-body { padding:10px 16px 14px; max-height:55vh; overflow:auto; }
.slip.closed .slip-body { display:none; }
.slip-item { display:grid; grid-template-columns:1fr auto auto; gap:4px 10px; align-items:center; padding:8px 0; border-bottom:1px solid var(--line); }
.slip-item .what { font-weight:600; font-size:14px; }
.slip-item .m { grid-column:1; color:var(--muted); font-size:12px; }
.slip-item .o { font:700 18px "Barlow Condensed",sans-serif; grid-row:1 / 3; grid-column:2; }
.slip-item .x { grid-row:1 / 3; grid-column:3; border:0; background:none; font-size:20px; cursor:pointer; color:var(--muted); }
.slip-tot { display:flex; justify-content:space-between; margin-top:10px; font-size:14px; }
.slip-tot b { font:800 22px "Barlow Condensed",sans-serif; }
.slip-note { font-size:12px; color:var(--muted); margin:6px 0 0; }
.slip-actions { display:flex; gap:8px; margin-top:12px; }
.slip-actions button { flex:1; font:600 14px Barlow,sans-serif; padding:9px; border-radius:10px; cursor:pointer;
  border:1px solid var(--pitch); background:var(--pitch); color:#fff; }
.slip-actions .ghost { background:#fff; color:var(--pitch); }
.sel:focus-visible, .slip button:focus-visible { outline:3px solid var(--flood); outline-offset:2px; }
@media (max-width:700px) {
  .markets { margin-right:0; }
  .picks3 { gap:6px; }
  .picks3 .sel { padding:6px 7px; }
  .stub .ring { grid-column:3; grid-row:1 / 3; align-self:center; }
  .ring svg { width:76px; height:76px; }
  .slip { right:8px; left:8px; bottom:8px; width:auto; }
  main { padding-bottom:90px; }
}

/* league menu */
.leagues { display:flex; gap:6px; overflow-x:auto; padding:14px 0 2px; scrollbar-width:thin; }
.lg { flex:0 0 auto; color:rgba(255,255,255,.78); text-decoration:none; font:600 15px/1 Barlow,sans-serif;
  padding:8px 12px; border-radius:999px; border:1px solid rgba(255,255,255,.18); }
.lg:hover { color:#fff; border-color:rgba(255,255,255,.4); }
.lg.on { background:var(--flood); color:var(--flood-ink); border-color:var(--flood); }
.lg:focus-visible, .row:focus-visible, .chip:focus-visible { outline:3px solid var(--flood); outline-offset:2px; }
a.chip { text-decoration:none; }
.top-pad { padding-bottom:18px; }

/* front page */
.league-block { margin-top:28px; }
.league-block:first-child { margin-top:4px; }
.league-block h2 { margin:0 0 10px; font:800 30px/1 "Barlow Condensed",sans-serif; }
.league-block h2 a { color:var(--ink); text-decoration:none; }
.league-block h2 a:hover { text-decoration:underline; }
.league-block h2 .sub { font:400 15px Barlow,sans-serif; color:var(--muted); margin-left:6px; }
.rows { background:var(--paper); border:1px solid var(--line); border-radius:14px; overflow:hidden; }
.row { display:grid; grid-template-columns:120px 1fr 140px 170px; align-items:center; gap:14px;
  padding:11px 16px; border-top:1px solid var(--line); color:var(--ink); text-decoration:none; }
.row:first-child { border-top:0; }
.row:hover { background:#f6f8f5; }
.row-when { color:var(--muted); font-size:13px; }
.row-teams { font:700 19px/1.15 "Barlow Condensed",sans-serif; }
.row-teams i { font-style:normal; color:var(--muted); font-weight:500; }
.row-bar { display:flex; height:8px; border-radius:5px; overflow:hidden; gap:2px; }
.row-pick { text-align:right; font-size:14px; }
.row-pick b { font:800 20px/1 "Barlow Condensed",sans-serif; margin-left:4px; }
.row-pick em { display:block; font-style:normal; font-size:12px; font-weight:700; color:#7a5d00; }
@media (max-width:700px) {
  .row { grid-template-columns:1fr auto; gap:4px 10px; padding:10px 14px; }
  .row-when { grid-column:1 / 3; }
  .row-teams { grid-column:1; }
  .row-pick { grid-column:2; grid-row:2; }
  .row-bar { grid-column:1 / 3; }
}
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>{css}{extra_css}</style>
</head>
<body>
__DECOR__
<header class="top top-pad">
  <div class="top-in">
    <div class="brand">
      <h1><a href="{prefix}" style="color:inherit;text-decoration:none">Footy<span>Predicts</span></a></h1>
      <p>{sub}</p>
    </div>
    {nav}
    {chips}
  </div>
</header>
<main>{body}
</main>
<footer class="foot">
<p><b>18+ only.</b> Gambling can be addictive. Please gamble responsibly and only with money you can afford to lose. Free, confidential help: <a href="https://www.begambleaware.org" rel="noopener">BeGambleAware.org</a> · National Gambling Helpline 0808 8020 133 · <a href="https://www.gamstop.co.uk" rel="noopener">GAMSTOP</a> · <a href="{prefix}responsible-gambling/">Responsible gambling and how this site is funded</a></p>
<p>Predictions come from statistical models trained on past matches. They are probabilities, not guarantees, and are not betting advice. Past results do not predict future results. Odds are the best price found across bookmakers at the last update and change often.</p>
<p>FootyPredicts does not take bets. If we link to a bookmaker, that link may be an affiliate link and we may be paid if you sign up. This never changes our predictions.</p>
</footer>
<script>
(function () {
  var chips = document.querySelectorAll('button.chip');
  if (!chips.length) return;
  function play(id) {
    var m = document.getElementById(id); if (!m) return;
    m.classList.remove('play'); void m.offsetWidth; m.classList.add('play');
    var t = m.querySelector('.ring text');
    if (!t || !t.firstChild || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var target = parseFloat(t.firstChild.nodeValue) || 0, start = null;
    (function step(ts) {
      if (start === null) start = ts;
      var k = Math.min(1, (ts - start) / 1000), e = 1 - Math.pow(1 - k, 3);
      t.firstChild.nodeValue = Math.round(target * e);
      if (k < 1) requestAnimationFrame(step);
    })(performance.now());
  }
  function show(id) {
    document.querySelectorAll('.match').forEach(function (m) { m.hidden = m.id !== id; });
    play(id);
    chips.forEach(function (c) { c.setAttribute('aria-selected', c.dataset.tab === id ? 'true' : 'false'); });
    try { history.replaceState(null, '', '#' + id); } catch (e) {}
  }
  chips.forEach(function (c) { c.addEventListener('click', function () { show(c.dataset.tab); }); });
  var h = location.hash.slice(1);
  show(h && document.getElementById(h) ? h : chips[0].dataset.tab);
})();
</script>
<script>
/* Bet slip: picks are kept in this browser only (localStorage). */
(function () {
  var KEY = 'fp-slip-v1', BKEY = 'fp-book-v1', picks = [];
  var BOOKIES = __BOOKIES__, book = 'best';
  try { book = localStorage.getItem(BKEY) || 'best'; } catch (e) {}
  if (book !== 'best' && !BOOKIES[book]) book = 'best';
  try { picks = JSON.parse(localStorage.getItem(KEY) || '[]') || []; } catch (e) { picks = []; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(picks)); } catch (e) {} }
  var slip = document.createElement('aside');
  slip.className = 'slip closed'; slip.setAttribute('aria-label', 'Bet slip'); slip.hidden = true;
  document.body.appendChild(slip);
  function fmt(n) { return n >= 100 ? n.toFixed(0) : n.toFixed(2); }
  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  /* Show every price at the chosen bookmaker (or the best price found). */
  function priceFor(books, best, bestBk) {
    if (book === 'best') return { odd: best, bookie: bestBk };
    var o = books && books[book];
    return o ? { odd: o, bookie: book } : null;
  }
  function applyBook() {
    document.querySelectorAll('button.sel').forEach(function (b) {
      var books = {}; try { books = JSON.parse(b.dataset.books || '{}'); } catch (e) {}
      var pr = priceFor(books, parseFloat(b.dataset.bestOdd), b.dataset.bestBookie);
      var bEl = b.querySelector('b'), sm = b.querySelector('small');
      if (pr) { b.dataset.odd = pr.odd.toFixed(2); b.dataset.bookie = pr.bookie; b.disabled = false; b.classList.remove('na');
                bEl.textContent = pr.odd.toFixed(2); if (sm) sm.textContent = pr.bookie; }
      else { b.dataset.odd = ''; b.disabled = true; b.classList.add('na'); bEl.textContent = '\u2013'; if (sm) sm.textContent = 'not at ' + book; }
    });
    picks.forEach(function (p) {
      var pr = priceFor(p.books, p.bestOdd, p.bestBookie);
      p.odd = pr ? pr.odd : null; p.bookie = pr ? pr.bookie : null;
    });
  }
  var bar = document.createElement('div');
  bar.className = 'bk-pick';
  bar.innerHTML = '<label>Show prices from <select>' + '<option value="best">Best price found</option>' +
    Object.keys(BOOKIES).map(function (k) { return '<option value="' + esc(k) + '">' + esc(k) + '</option>'; }).join('') +
    '</select></label>';
  var mainEl = document.querySelector('main');
  if (mainEl && document.querySelector('button.sel')) mainEl.insertBefore(bar, mainEl.firstChild);
  var selEl = bar.querySelector('select'); selEl.value = book;
  selEl.addEventListener('change', function () {
    book = selEl.value; try { localStorage.setItem(BKEY, book); } catch (e) {}
    applyBook(); save(); render();
  });
  function render() {
    document.querySelectorAll('button.sel').forEach(function (b) {
      b.setAttribute('aria-pressed', picks.some(function (p) { return p.key === b.dataset.key; }) ? 'true' : 'false');
    });
    if (!picks.length) { slip.hidden = true; return; }
    slip.hidden = false;
    var priced = picks.filter(function (p) { return p.odd; }), missing = picks.length - priced.length;
    var odds = priced.reduce(function (a, p) { return a * p.odd; }, 1);
    var chance = picks.reduce(function (a, p) { return a * p.p; }, 1);
    var fids = picks.map(function (p) { return p.fid; });
    var sameMatch = fids.some(function (f, i) { return fids.indexOf(f) !== i; });
    var items = picks.map(function (p, i) {
      return '<div class="slip-item"><span class="what">' + esc(p.label) + '</span>' +
        '<span class="m">' + esc(p.match) + ' · ' + (p.odd ? esc(p.bookie) : 'not at ' + esc(book)) + '</span>' +
        '<span class="o">' + (p.odd ? p.odd.toFixed(2) : '\u2013') + '</span>' +
        '<button class="x" data-i="' + i + '" aria-label="Remove ' + esc(p.label) + '">×</button></div>';
    }).join('');
    slip.innerHTML =
      '<button class="slip-head" aria-expanded="' + (!slip.classList.contains('closed')) + '">' +
      '<span>Bet slip (' + picks.length + ')</span><span>' + (picks.length > 1 ? 'Combined odds ' : 'Odds ') + '<b>' + fmt(odds) + '</b></span></button>' +
      '<div class="slip-body">' + items +
      '<div class="slip-tot"><span>' + (picks.length > 1 ? 'Combined odds' : 'Odds') + '</span><b>' + fmt(odds) + '</b></div>' +
      '<div class="slip-tot"><span>Our model\u2019s chance' + (picks.length > 1 ? ' of all landing' : '') + '</span><b>' + (100 * chance).toFixed(chance < 0.1 ? 1 : 0) + '%</b></div>' +
      (sameMatch ? '<p class="slip-note">Picks from the same match are linked, so bookmakers price them differently from these simple combined odds.</p>' : '') +
      (picks.length > 1 && book === 'best' ? '<p class="slip-note">Prices are the best found for each pick, which may be at different bookmakers. Choose a bookmaker above to see all prices from one place.</p>' : '') +
      (missing ? '<p class="slip-note">' + missing + ' pick(s) are not offered by ' + esc(book) + ' and are left out of the odds.</p>' : '') +
      betLink() +
      '<div class="slip-actions"><button class="copy">Copy slip</button><button class="ghost clear">Clear</button></div>' +
      '<p class="slip-note">Odds change. Check the price with the bookmaker. 18+ · BeGambleAware.org</p></div>';
  }
  function betLink() {
    if (book === 'best') return '<p class="slip-note">Choose a bookmaker in \u201cShow prices from\u201d to get a link to bet with them.</p>';
    var c = BOOKIES[book]; if (!c || !c.url) return '';
    return '<a class="betwith" href="' + esc(c.url) + '" target="_blank" rel="' + (c.aff ? 'sponsored ' : '') + 'noopener nofollow">Bet with ' + esc(book) + ' \u2192</a>' +
      '<p class="slip-note">' + (c.aff ? 'Affiliate link: we may earn a commission if you sign up. ' : '') +
      'This opens ' + esc(book) + '\u2019s site \u2013 add your picks there and check the final price. 18+ only.</p>';
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('button.sel');
    if (b) {
      var k = b.dataset.key, i = picks.findIndex(function (p) { return p.key === k; });
      if (i >= 0) picks.splice(i, 1);
      else {
        picks = picks.filter(function (p) { return p.group !== b.dataset.group; });
        picks.push({ key: k, group: b.dataset.group, fid: b.dataset.fid, label: b.dataset.label, match: b.dataset.match,
                     odd: parseFloat(b.dataset.odd), bookie: b.dataset.bookie, p: parseFloat(b.dataset.p),
                     bestOdd: parseFloat(b.dataset.bestOdd), bestBookie: b.dataset.bestBookie,
                     books: JSON.parse(b.dataset.books || '{}') });
        if (picks.length === 1 && window.innerWidth > 700) slip.classList.remove('closed');
      }
      save(); render(); return;
    }
    if (e.target.closest('.slip-head')) { slip.classList.toggle('closed'); render(); return; }
    var x = e.target.closest('.slip .x');
    if (x) { picks.splice(+x.dataset.i, 1); save(); render(); return; }
    if (e.target.closest('.slip .clear')) { picks = []; save(); render(); return; }
    var c = e.target.closest('.slip .copy');
    if (c) {
      var odds = picks.filter(function (p) { return p.odd; }).reduce(function (a, p) { return a * p.odd; }, 1);
      var text = picks.map(function (p) { return p.match + ': ' + p.label + (p.odd ? ' @ ' + p.odd.toFixed(2) + ' (' + p.bookie + ')' : ' (not at ' + book + ')'); }).join('\n') +
        '\nCombined odds: ' + fmt(odds) + '\nfrom FootyPredicts';
      var done = function () { c.textContent = 'Copied'; setTimeout(function () { c.textContent = 'Copy slip'; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {}); else done();
    }
  });
  applyBook(); save(); render();
})();
</script>
</body>
</html>
""".replace("{", "{{").replace("}", "}}")
for _k in ("title", "desc", "css", "extra_css", "prefix", "sub", "nav", "chips", "body"):
    PAGE = PAGE.replace("{{" + _k + "}}", "{" + _k + "}")


if __name__ == "__main__":
    build()
