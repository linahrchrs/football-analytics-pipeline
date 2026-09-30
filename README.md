# Football Analytics Pipeline & Match Predictor

An end-to-end data pipeline for European football: historical and daily match data loaded into PostgreSQL, modelled with dbt, used to predict upcoming matches, and published on a live dashboard that tracks the model's real accuracy.

> 🚧 Work in progress. Step 1 (historical backfill) is done.

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
- [ ] **Step 2:** daily updates from the football-data.org API, with team-name mapping between the two sources
- [ ] **Step 3:** dbt models: standings, form, home advantage, Elo ratings, with tests
- [ ] **Step 4:** prediction model (Elo + Poisson), benchmarked against bookmaker odds
- [ ] **Step 5:** GitHub Actions automation
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

The full backfill downloads about 90 files and takes a few minutes. Files are cached in `data/raw/`, so re-running the script is fast and safe: existing matches are updated, never duplicated.

Useful options:

```bash
python -m src.ingestion.backfill_history --leagues E0 SP1          # only some leagues
python -m src.ingestion.backfill_history --first 2020 --last 2024  # only some seasons
python -m src.ingestion.backfill_history --refresh                 # re-download cached files
```

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

Parsing tests always run. Database tests run when PostgreSQL is up and are skipped otherwise.

## Project structure

```
├── src/
│   ├── config.py                    # leagues, seasons, source URLs
│   ├── db.py                        # database connection and schema setup
│   └── ingestion/
│       └── backfill_history.py      # step 1
├── sql/init/                        # raw schema, also run by Docker on first start
├── tests/                           # pytest tests and sample CSV files
├── dbt/                             # step 3
├── dashboard/                       # step 6
└── docker-compose.yml
```

## Data sources

- [football-data.co.uk](https://www.football-data.co.uk): historical results, match statistics and betting odds (free CSV files).
- [football-data.org](https://www.football-data.org): fixtures and results through a free API (from step 2).
