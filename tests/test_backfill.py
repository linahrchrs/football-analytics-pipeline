"""Tests for the historical backfill.

Parsing tests run anywhere. Database tests use a separate test database (see
conftest.py) and are skipped when PostgreSQL is not running.
"""
from datetime import date, time
from pathlib import Path

import pytest
from sqlalchemy import text

from src.config import season_code, season_label
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


def test_upsert_is_idempotent_and_updates(test_engine):
    df = load("E0_2324.csv", "E0", 2023)
    upsert(test_engine, df)
    upsert(test_engine, df)                               # running twice must not duplicate
    df.loc[df.index[0], "home_goals"] = 1                 # a corrected score gets updated
    upsert(test_engine, df)

    with test_engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM raw.historical_matches WHERE league_code='E0' AND season='2023-24'")).scalar()
        goals = conn.execute(text("SELECT home_goals FROM raw.historical_matches WHERE home_team='Burnley' AND match_date='2023-08-11'")).scalar()
    assert n == 2
    assert goals == 1
