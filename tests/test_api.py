"""Tests for the football-data.org ingestion and the team-name mapping.

The API is never called: requests are answered from tests/fixtures/api_PL_matches.json.
Database tests run only when PostgreSQL is reachable.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from src.db import get_engine, init_schema
from src.ingestion import fetch_api_matches as api
from src.ingestion.backfill_history import read_raw_csv, standardize
from src.ingestion.backfill_history import upsert as upsert_history
from src.ingestion.build_team_map import VOTES_SQL, build_mapping, similarity

FIXTURES = Path(__file__).parent / "fixtures"
PAYLOAD = json.loads((FIXTURES / "api_PL_matches.json").read_text())


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code, self._payload, self.headers = status, payload, headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    """Returns a 429 (rate limit) first, then the fixture payload."""
    def __init__(self):
        self.calls = []
        self.responses = [FakeResponse(429, headers={"X-RequestCounter-Reset": "0"}), FakeResponse(200, PAYLOAD)]

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return self.responses.pop(0)


def test_parse_matches_flattens_finished_and_upcoming():
    df = api.parse_matches(PAYLOAD, "E0")
    assert len(df) == 4
    first = df.iloc[0]
    assert first["match_id"] == 435943
    assert first["season"] == "2023-24"
    assert first["match_date"] == date(2023, 8, 11)
    assert (first["home_team_name"], first["home_goals"], first["away_goals"]) == ("Burnley FC", 0, 3)
    upcoming = df.iloc[3]
    assert upcoming["status"] == "TIMED"
    assert upcoming["home_goals"] is None


def test_fetch_retries_after_rate_limit_and_sends_token(monkeypatch):
    monkeypatch.setattr(api.time, "sleep", lambda s: None)
    session = FakeSession()
    payload = api.fetch_competition("PL", "secret-token", session=session)
    assert len(payload["matches"]) == 4
    assert len(session.calls) == 2
    assert session.calls[0][1] == {"X-Auth-Token": "secret-token"}
    assert session.calls[0][0].endswith("/competitions/PL/matches")


def test_missing_api_key_gives_clear_error(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "your-key-here")
    with pytest.raises(api.ApiError, match="missing"):
        api.get_api_key()


def test_fuzzy_similarity_handles_common_name_differences():
    assert similarity("Burnley FC", "Burnley") > 0.9
    assert similarity("1. FC Köln", "FC Koln") > 0.9
    assert similarity("Arsenal FC", "Burnley") < 0.5


def test_mapping_prefers_results_and_falls_back_to_fuzzy():
    votes = pd.DataFrame([
        ("E0", 76, "Wolverhampton Wanderers FC", "Wolverhampton", "Wolves", 5),
        ("E0", 76, "Wolverhampton Wanderers FC", "Wolverhampton", "Fulham", 1),   # coincidence: same date and score
        ("E0", 66, "Manchester United FC", "Man United", "Man United", 1),        # too few votes yet
    ], columns=["league_code", "api_team_id", "api_team_name", "api_team_short", "csv_team_name", "votes"])
    api_teams = pd.DataFrame([("E0", 76, "Wolverhampton Wanderers FC", "Wolverhampton"),
                              ("E0", 66, "Manchester United FC", "Man United")],
                             columns=["league_code", "api_team_id", "api_team_name", "api_team_short"])
    csv_teams = pd.DataFrame([("E0", "Wolves"), ("E0", "Man United"), ("E0", "Fulham")],
                             columns=["league_code", "csv_team_name"])
    m = build_mapping(votes, api_teams, csv_teams).set_index("api_team_id")
    assert m.loc[76, "csv_team_name"] == "Wolves" and m.loc[76, "method"] == "results"
    assert m.loc[66, "csv_team_name"] == "Man United" and m.loc[66, "method"] == "fuzzy"


def db_available():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not db_available(), reason="PostgreSQL not running")
def test_api_upsert_and_votes_against_history():
    engine = get_engine()
    init_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM raw.api_matches WHERE competition_code = 'PL' AND season = '2023-24'"))

    df = api.parse_matches(PAYLOAD, "E0")
    api.upsert(engine, df)
    api.upsert(engine, df)                       # idempotent
    upsert_history(engine, standardize(read_raw_csv(FIXTURES / "E0_2324.csv"), "E0", 2023, "E0_2324.csv"))

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM raw.api_matches WHERE season='2023-24' AND competition_code='PL'")).scalar() == 4
        votes = pd.read_sql(text(VOTES_SQL), conn)
    pairs = set(zip(votes["api_team_name"], votes["csv_team_name"]))
    assert ("Burnley FC", "Burnley") in pairs
    assert ("Manchester City FC", "Man City") in pairs
    assert ("Nottingham Forest FC", "Nott'm Forest") in pairs