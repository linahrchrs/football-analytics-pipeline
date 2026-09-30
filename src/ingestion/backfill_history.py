"""Step 1: load historical match results from football-data.co.uk into PostgreSQL.

Downloads one CSV per league and season, standardizes the columns, and upserts
the rows into raw.historical_matches. Downloaded files are cached in data/raw/
so re-running the script does not hit the website again.

Usage:
    python -m src.ingestion.backfill_history                      # all leagues, 2015-16 to last season
    python -m src.ingestion.backfill_history --leagues E0 SP1     # only some leagues
    python -m src.ingestion.backfill_history --first 2020 --last 2025
    python -m src.ingestion.backfill_history --refresh            # re-download cached files
"""
from __future__ import annotations

import argparse
import io
import logging
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import types as sqltypes
from sqlalchemy.engine import Engine

from src.config import FIRST_SEASON, HISTORY_URL, LEAGUES, season_code, season_label
from src.db import ROOT, get_engine, init_schema

log = logging.getLogger("backfill")

CACHE_DIR = ROOT / "data" / "raw" / "football-data-co-uk"

# Source column -> database column
COLUMN_MAP = {
    "Date": "match_date",
    "Time": "kickoff_time",
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG": "home_goals",
    "FTAG": "away_goals",
    "FTR": "result",
    "HTHG": "home_goals_ht",
    "HTAG": "away_goals_ht",
    "HTR": "result_ht",
    "Referee": "referee",
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_on_target",
    "AST": "away_shots_on_target",
    "HF": "home_fouls",
    "AF": "away_fouls",
    "HC": "home_corners",
    "AC": "away_corners",
    "HY": "home_yellow_cards",
    "AY": "away_yellow_cards",
    "HR": "home_red_cards",
    "AR": "away_red_cards",
    "B365H": "odds_home",
    "B365D": "odds_draw",
    "B365A": "odds_away",
}
INT_COLUMNS = [c for c in COLUMN_MAP.values() if c.startswith(("home_", "away_")) and c not in ("home_team", "away_team")]
ODDS_COLUMNS = ["odds_home", "odds_draw", "odds_away"]
DB_COLUMNS = ["league_code", "season", *COLUMN_MAP.values(), "source_file"]

# Explicit SQL types, so columns that are empty in a file (e.g. no kickoff times
# in old seasons) are still sent with the right type.
SQL_TYPES = {c: sqltypes.SmallInteger() for c in INT_COLUMNS}
SQL_TYPES.update({c: sqltypes.Numeric(6, 2) for c in ODDS_COLUMNS})
SQL_TYPES.update({"match_date": sqltypes.Date(), "kickoff_time": sqltypes.Time()})
SQL_TYPES.update({c: sqltypes.Text() for c in ("league_code", "season", "home_team", "away_team", "result", "result_ht", "referee", "source_file")})


def current_season_start(today: date | None = None) -> int:
    """European seasons start in August: in Sept 2026 the current season is 2026-27."""
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


# ---------------------------------------------------------------- download

def download_csv(league: str, start_year: int, refresh: bool = False) -> Path | None:
    """Download one season file (or reuse the cached copy). Returns None if unavailable."""
    code = season_code(start_year)
    path = CACHE_DIR / code / f"{league}.csv"
    if path.exists() and not refresh:
        return path

    url = HISTORY_URL.format(code=code, league=league)
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": "football-analytics-pipeline"})
            if resp.status_code == 404:
                log.warning("Not available: %s", url)
                return None
            resp.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)
            time.sleep(1)  # be polite to a free, volunteer-run website
            return path
        except requests.RequestException as exc:
            wait = 2 ** attempt
            log.warning("Download failed (%s), retrying in %ss: %s", exc.__class__.__name__, wait, url)
            time.sleep(wait)
    log.error("Giving up on %s", url)
    return None


# ------------------------------------------------------------------ parsing

def read_raw_csv(path: Path) -> pd.DataFrame:
    """Read a football-data.co.uk CSV, handling the encodings used across seasons."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=encoding, on_bad_lines="skip", low_memory=False)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {path}")


def parse_dates(values: pd.Series) -> pd.Series:
    """Dates are dd/mm/yyyy in recent seasons and dd/mm/yy in older ones."""
    values = values.astype(str).str.strip()
    long_fmt = pd.to_datetime(values, format="%d/%m/%Y", errors="coerce")
    short_fmt = pd.to_datetime(values, format="%d/%m/%y", errors="coerce")
    return long_fmt.fillna(short_fmt).dt.date


def standardize(df: pd.DataFrame, league: str, start_year: int, source_file: str) -> pd.DataFrame:
    """Keep the columns we need, rename them and fix their types."""
    if "HomeTeam" not in df.columns or "AwayTeam" not in df.columns:
        return pd.DataFrame(columns=DB_COLUMNS)
    df = df.dropna(how="all")
    df = df[df["HomeTeam"].notna() & df["AwayTeam"].notna()]

    out = pd.DataFrame(index=df.index)
    for src, dst in COLUMN_MAP.items():
        out[dst] = df[src] if src in df.columns else None  # older seasons lack some columns

    out["match_date"] = parse_dates(out["match_date"])
    out["kickoff_time"] = pd.to_datetime(out["kickoff_time"], format="%H:%M", errors="coerce").dt.time
    out["home_team"] = out["home_team"].astype(str).str.strip()
    out["away_team"] = out["away_team"].astype(str).str.strip()
    for col in INT_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    for col in ODDS_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    for col in ("result", "result_ht", "referee"):
        out[col] = out[col].where(out[col].notna(), None)

    out.insert(0, "season", season_label(start_year))
    out.insert(0, "league_code", league)
    out["source_file"] = source_file

    out = out[out["match_date"].notna()]
    # A few old files contain the same fixture twice; keep the last version.
    out = out.drop_duplicates(subset=["league_code", "match_date", "home_team", "away_team"], keep="last")
    return out[DB_COLUMNS].astype(object).where(out[DB_COLUMNS].notna(), None)


# ------------------------------------------------------------------ loading

UPSERT_SQL = f"""
INSERT INTO raw.historical_matches ({", ".join(DB_COLUMNS)})
SELECT {", ".join(DB_COLUMNS)} FROM tmp_matches
ON CONFLICT (league_code, match_date, home_team, away_team) DO UPDATE SET
    {", ".join(f"{c} = EXCLUDED.{c}" for c in DB_COLUMNS if c not in ("league_code", "match_date", "home_team", "away_team"))},
    loaded_at = now();
"""


def upsert(engine: Engine, df: pd.DataFrame) -> int:
    """Insert new rows and update existing ones (safe to re-run)."""
    if df.empty:
        return 0
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TEMP TABLE tmp_matches (LIKE raw.historical_matches INCLUDING DEFAULTS) ON COMMIT DROP")
        df.to_sql("tmp_matches", conn, if_exists="append", index=False, method="multi", chunksize=500, dtype=SQL_TYPES)
        conn.exec_driver_sql(UPSERT_SQL)
    return len(df)


# --------------------------------------------------------------------- main

def run(leagues: list[str], first: int, last: int, refresh: bool = False, engine: Engine | None = None) -> int:
    engine = engine or get_engine()
    init_schema(engine)
    total = 0
    for league in leagues:
        for start_year in range(first, last + 1):
            path = download_csv(league, start_year, refresh=refresh)
            if path is None:
                continue
            df = standardize(read_raw_csv(path), league, start_year, source_file=f"{season_code(start_year)}/{league}.csv")
            n = upsert(engine, df)
            total += n
            log.info("%-4s %s  %4d matches", league, season_label(start_year), n)
    log.info("Done: %d matches loaded or updated", total)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical matches from football-data.co.uk")
    parser.add_argument("--leagues", nargs="+", default=list(LEAGUES), choices=list(LEAGUES))
    parser.add_argument("--first", type=int, default=FIRST_SEASON, help="first season start year (default: %(default)s)")
    parser.add_argument("--last", type=int, default=current_season_start() - 1, help="last season start year (default: last completed season)")
    parser.add_argument("--refresh", action="store_true", help="re-download files already in the cache")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    run(args.leagues, args.first, args.last, refresh=args.refresh)


if __name__ == "__main__":
    main()