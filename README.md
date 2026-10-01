# Football Analytics Pipeline & Match Predictor

[![CI](https://github.com/linahrchrs/football-analytics-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/linahrchrs/football-analytics-pipeline/actions/workflows/ci.yml)
[![Daily pipeline](https://github.com/linahrchrs/football-analytics-pipeline/actions/workflows/daily-pipeline.yml/badge.svg)](https://github.com/linahrchrs/football-analytics-pipeline/actions/workflows/daily-pipeline.yml)

An end-to-end data pipeline for European football: historical and daily match data loaded into PostgreSQL, modelled with dbt, used to predict upcoming matches, and published on a live dashboard that tracks the model's real accuracy.

> 🚧 Work in progress. Steps 1 to 5 are done: the pipeline now runs by itself every day. Next: the live dashboard.

## Architecture

```
football-data.co.uk (CSV, history) ──┐
                                     ├──► Python ingestion ──► PostgreSQL (raw)
football-data.org (API, daily) ──────┘                               │
                                                        dbt: staging ──► marts
                                                                     │
                            Elo + Poisson model ──► predictions ◄────┘
                                                         │
                          GitHub Actions (daily) · Streamlit dashboard
```

## Leagues

Premier League, Championship, La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie and Primeira Liga, from the 2015-16 season onwards.

## Roadmap

- [x] **Step 1:** historical backfill from football-data.co.uk
- [x] **Step 2:** current-season updates from the football-data.org API, with automatic team-name mapping between the two sources
- [x] **Step 3:** dbt models: unified matches, standings, form, home advantage, with data tests
- [x] **Step 4:** Elo ratings and prediction model (Elo + Poisson), benchmarked against bookmaker odds
- [x] **Step 5:** GitHub Actions automation: daily pipeline on a cloud PostgreSQL database (Neon), tests on every push
- [ ] **Step 6:** live Streamlit dashboard

## Getting started

Requirements: Python 3.10+ and Docker.

```bash
git clone https://github.com/linahrchrs/football-analytics-pipeline.git
cd football-analytics-pipeline
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

docker compose up -d                                  # starts PostgreSQL on localhost:5432
python -m src.ingestion.backfill_history              # loads every league since 2015-16
```

On Windows PowerShell, activate the environment with `.\venv\Scripts\Activate.ps1` and create the env file with `Copy-Item .env.example .env`.

## Current season (step 2)

Add your free [football-data.org](https://www.football-data.org) token to `.env` (`FOOTBALL_DATA_API_KEY=...`), then:

```bash
python -m src.ingestion.backfill_history --first 2026 --last 2026   # current-season CSV files
python -m src.ingestion.fetch_api_matches                          # fixtures and results from the API
python -m src.ingestion.build_team_map                             # learns the team-name mapping
```

The API returns every match of the current season: results for finished matches and dates for upcoming ones, which the model will predict in step 4. The free tier allows 10 requests per minute, so the script pauses between leagues and waits automatically if the limit is reached.

### Team-name mapping

The two sources name teams differently ("Manchester United FC" vs "Man United", "Club Atlético de Madrid" vs "Ath Madrid"). Rather than a hand-written list, `build_team_map` learns the mapping from the data: a finished match appears in both sources with the same league, date and score, so every match is a vote that API team X is CSV team Y. Teams without enough votes fall back to fuzzy name matching, and anything uncertain is printed as a warning.

The result is saved to `dbt/seeds/team_name_map.csv`. Review it once, fix any line flagged in the warnings, and commit it.

The full backfill downloads about 90 files and takes a few minutes. Files are cached in `data/raw/`, so re-running the script is fast and safe: existing matches are updated, never duplicated.

Useful options:

```bash
python -m src.ingestion.backfill_history --leagues E0 SP1          # only some leagues
python -m src.ingestion.backfill_history --first 2020 --last 2024  # only some seasons
python -m src.ingestion.backfill_history --refresh                 # re-download cached files
```

## Data models (step 3)

```bash
cd dbt
dbt build --profiles-dir . --exclude tag:predictions   # seeds, models and tests
```

The `predictions` models read the model's output, so they are built after step 4.

By default dbt connects to the local Docker database (port 5433). To use another database, set `DBT_HOST`, `DBT_PORT`, `DBT_USER`, `DBT_PASSWORD`, `DBT_DBNAME` and `DBT_SSLMODE`.

| Layer | Model | What it contains |
|---|---|---|
| staging | `stg_historical_matches` | Played matches from football-data.co.uk |
| staging | `stg_api_matches` | Current-season matches from the API, with canonical team names |
| intermediate | `int_matches_unified` | One row per match from both sources: the CSV is the reference for played matches, the API adds the latest results and every upcoming fixture |
| intermediate | `int_team_matches` | One row per team per match, which makes team statistics simple aggregations |
| marts | `fct_matches` | Every match, played or upcoming, with bookmaker probabilities (margin removed) as a benchmark |
| marts | `fct_standings` | League table for every league and season |
| marts | `fct_team_form` | Each team's form going into every match, using only earlier matches so it is safe as a model feature |
| marts | `fct_league_seasons` | Home win rate, draw rate and goals per league and season |
| marts | `dim_teams` | Teams with the leagues and seasons they played in |

Besides standard tests (unique keys, accepted values, relationships), custom tests check the football logic: points always equal 3 × wins + draws, goals scored equal goals conceded in every league season, and no team plays twice on the same day, which would reveal a duplicate between the two sources.

To browse the models and their lineage graph: `dbt docs generate --profiles-dir .` then `dbt docs serve --profiles-dir .`

## Prediction model (step 4)

```bash
python -m src.model.run all                              # Elo ratings, backtest, predictions
cd dbt && dbt build --profiles-dir . --select tag:predictions && cd ..
```

**Elo ratings.** Every team starts at 1500 and gains or loses points after each match, more for an unexpected result or a wide margin. Ratings carry over between seasons (pulled slightly toward the average) and between divisions, so a promoted team keeps its strength. Elo is computed in Python because each rating depends on the previous one, which is natural in a loop and awkward in SQL.

**Goals model.** Two Poisson regressions predict each team's expected goals from the Elo difference (with home advantage), both teams' form over their last 5 matches, and the league's average goals the previous season. The two expected-goal values give the probability of every scoreline, which add up to home win, draw and away win probabilities. Every feature uses only information available before kickoff.

**Evaluation.** A walk-forward backtest trains on earlier seasons and scores the next one, for the last 3 completed seasons. The model is compared with a naive baseline (historical home/draw/away rates) and with bookmaker odds, using accuracy, log loss, Brier score and the ranked probability score (RPS), the standard metric for football predictions. Bookmakers are a very strong benchmark: getting close to them is the realistic goal.

**Track record.** Predictions are stored forever in `model.match_predictions` and never overwritten. `fct_prediction_results` takes the last prediction made before each match and compares it with the result, so the dashboard can show how the model actually performs on matches it had not seen.

| Table | Contents |
|---|---|
| `model.elo_ratings` | Each team's rating before and after every match |
| `model.backtest_results` | Backtest scores for the model, bookmakers and the baseline |
| `model.match_predictions` | Every prediction ever made |
| `marts.fct_prediction_results` | Last prediction before each match, with the result and its score |
| `marts.fct_team_ratings` | Current Elo rating and league rank of every team |

## Automation (step 5)

Two GitHub Actions workflows:

- **CI** (`.github/workflows/ci.yml`) runs the test suite on every push, against a throwaway PostgreSQL service.
- **Daily pipeline** (`.github/workflows/daily-pipeline.yml`) runs every day at 05:00 UTC, before the day's matches: current-season CSV files → API fixtures and results → dbt models and data tests → predictions → track-record models. It can also be started by hand from the Actions tab.

The daily pipeline writes to a free [Neon](https://neon.tech) PostgreSQL database, which the dashboard will read. It needs two repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `DATABASE_URL` | Neon connection string, starting with `postgresql+psycopg://` |
| `FOOTBALL_DATA_API_KEY` | football-data.org token |

dbt reads its connection from `DBT_*` variables, which `python -m src.dbt_env` derives from `DATABASE_URL`, so the connection string is stored only once.

## Checking the data

```sql
SELECT league_code, season, COUNT(*) AS matches
FROM raw.historical_matches
GROUP BY league_code, season
ORDER BY league_code, season;
```

A complete Premier League season has 380 matches.

## Tests

```bash
pytest
```

Database tests run in a separate `football_test` database created automatically, so they never touch the pipeline's data. They are skipped when PostgreSQL is not running.

## Project structure

```
├── src/
│   ├── config.py                    # leagues, seasons, source URLs
│   ├── db.py                        # database connection and schema setup
│   └── ingestion/
│       ├── backfill_history.py      # step 1: historical CSV files
│       ├── fetch_api_matches.py     # step 2: current season from the API
│       └── build_team_map.py        # step 2: team-name mapping between sources
│   └── model/
│       ├── elo.py                   # step 4: Elo ratings
│       ├── poisson_model.py         # step 4: features, goals model, metrics
│       └── run.py                   # step 4: backtest and predictions
├── .github/workflows/               # step 5: CI and daily pipeline
├── sql/init/                        # raw and model schemas, also run by Docker on first start
├── tests/                           # pytest tests and sample CSV files
├── dbt/                             # step 3: dbt project
│   ├── models/staging/              # cleaned sources
│   ├── models/intermediate/         # unified matches, one row per team per match
│   ├── models/marts/                # standings, form, league stats
│   ├── models/predictions/          # track record and current ratings (step 4)
│   ├── seeds/                       # team_name_map.csv (step 2), leagues.csv
│   └── tests/                       # football logic tests
├── dashboard/                       # step 6
└── docker-compose.yml
```

## Data sources

- [football-data.co.uk](https://www.football-data.co.uk): historical results, match statistics and betting odds (free CSV files).
- [football-data.org](https://www.football-data.org): current-season fixtures and results through a free API.
