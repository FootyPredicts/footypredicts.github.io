# FootyPredicts

Match predictions for the Premier League, La Liga, Bundesliga, Serie A and Ligue 1,
published with GitHub Pages (the address is shown under Settings > Pages)

## How it runs

Every morning GitHub Actions (`.github/workflows/update-predictions.yml`):
1. `python -m pipeline.run` – for each league, downloads new data from API-Football into
   `data/<league>/` and writes predictions to `data/site/<league>.json`.
   Each league only uses its own data.
2. `python build_site.py` – builds `docs/` (front page and one page per league).
4. Saves the new data to the repo and publishes the site.

Odds: best price per selection across bookmakers (`/odds?fixture=`), shown as clickable prices that build a bet slip (kept in the visitor's browser only).

Run it yourself any time: **Actions → Update predictions → Run workflow**.
Needs the repository secret `API_FOOTBALL_KEY` (paid plan recommended; the free plan's
100 requests/day only covers one league).

Add a league: one line in `pipeline/config.py` (`LEAGUES`) and in `build_site.py` (`LEAGUE_ORDER`).

## How the predictions work (`pipeline/models.py`)

- **Result + win %** (`result_model.py`): each team's attack/defence strength from the last
  3 seasons of results (recent games weigh more) + home advantage → expected goals →
  home/draw/away %. Backtest (PL, 533 matches): 50.5% correct, well calibrated.
- **Over 2.5 / BTTS**: from the same expected-goals score grid.
- **5+ cards**: referee's average cards per game (shrunk towards the league average) blended
  with both teams' card averages.
- **Scorers / bookings**: goals (+ shots on target) and cards per 90, adjusted for position,
  expected minutes, opponent defence and referee.
- **Defender shot on target**: shots on target ×2 + shots ×0.6.
- **Draw risk**: shown when the draw is within 8 points of the favourite.

## Running on your laptop

Create `.env` in this folder (never uploaded – see `.gitignore`):
```
API_FOOTBALL_KEY=your-key-here
```
then `pip install -r requirements-pipeline.txt` and `python -m pipeline.run` and `python build_site.py`.

## Older Premier League scripts

The original scripts (`premier_league_pipeline_2026_27 (2).py`, `Premier_league_predicted_results_only.py`,
`app.py`, `legacy_build_site_pl.py` …) are kept for reference but no longer run automatically.
