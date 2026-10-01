"""Tests for the historical backfill.

Parsing tests run anywhere. Database tests run only when PostgreSQL is reachable
(start it with `docker compose up -d`), otherwise they are skipped.
"""
from datetime import date, time
from pathlib import Path

import pytest
from sqlalchemy import text

from src.config import season_code, season_label
from src.db import get_engine, init_schema
from src.ingestion.backfill_history import current_season_start, read_raw_csv, standardize, upsert

FIXTURES = Path(__file__).parent / "fixtures"


def load(name, league, year):
    return standardize(read_raw_csv(FIXTURES / name), league, year, source_file=name)


def test_season_helpers():
    assert season_code(2023) == "2324"
    assert season_code(1999) == "9900"
    assert season_label(2023) == "2023-24"
    assert current_season_start(date(2026, 9, 30)) == 2026
    assert current_season_start(date(2027, 3, 1)) == 2026


def test_modern_file_utf8_with_bom_time_and_referee():
    df = load("E0_2324.csv", "E0", 2023)
    assert len(df) == 2                                   # empty trailing row dropped
    first = df.iloc[0]
    assert first["match_date"] == date(2023, 8, 11)
    assert first["kickoff_time"] == time(20, 0)
    assert first["home_team"] == "Burnley" and first["away_team"] == "Man City"
    assert (first["home_goals"], first["away_goals"], first["result"]) == (0, 3, "A")
    assert first["referee"] == "C Pawson"
    assert first["odds_away"] == pytest.approx(1.33)
    assert df.iloc[1]["away_team"] == "Nott'm Forest"


def test_old_file_latin1_short_dates_missing_columns_and_duplicates():
    df = load("SP1_1516.csv", "SP1", 2015)
    assert len(df) == 2                                   # duplicate fixture removed
    assert df.iloc[0]["home_team"] == "Málaga"           # latin-1 decoded correctly
    assert df.iloc[0]["match_date"] == date(2015, 8, 21)  # dd/mm/yy parsed
    assert df.iloc[0]["kickoff_time"] is None             # no Time column in old seasons
    assert df.iloc[0]["referee"] is None
    assert df.iloc[0]["season"] == "2015-16"


def db_available():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not db_available(), reason="PostgreSQL not running")
def test_upsert_is_idempotent_and_updates():
    engine = get_engine()
    init_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM raw.historical_matches WHERE source_file LIKE '%.csv' AND league_code IN ('E0','SP1') AND season IN ('2023-24','2015-16')"))

    df = load("E0_2324.csv", "E0", 2023)
    upsert(engine, df)
    upsert(engine, df)                                    # running twice must not duplicate
    df.loc[df.index[0], "home_goals"] = 1                 # a corrected score gets updated
    upsert(engine, df)

    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM raw.historical_matches WHERE league_code='E0' AND season='2023-24'")).scalar()
        goals = conn.execute(text("SELECT home_goals FROM raw.historical_matches WHERE home_team='Burnley' AND match_date='2023-08-11'")).scalar()
    assert n == 2
    assert goals == 1