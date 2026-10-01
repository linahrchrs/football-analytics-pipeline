"""Step 2a: load current-season fixtures and results from the football-data.org API.

One request per competition returns every match of the current season: finished
ones with their score, upcoming ones with their date. Rows are upserted on the
API's match id, so scores, statuses and rescheduled dates stay up to date.

Usage:
    python -m src.ingestion.fetch_api_matches                 # all leagues
    python -m src.ingestion.fetch_api_matches --leagues E0    # only some leagues
"""
from __future__ import annotations

import argparse
import logging
import os
import time

import pandas as pd
import requests
from sqlalchemy import types as sqltypes
from sqlalchemy.engine import Engine

from src.config import API_BASE_URL, API_COMPETITIONS, API_SECONDS_BETWEEN_CALLS, LEAGUES, season_label
from src.db import get_engine, init_schema

log = logging.getLogger("api")

DB_COLUMNS = [
    "match_id", "league_code", "competition_code", "season", "matchday", "utc_kickoff", "match_date",
    "status", "home_team_id", "home_team_name", "home_team_short", "away_team_id", "away_team_name",
    "away_team_short", "home_goals", "away_goals", "home_goals_ht", "away_goals_ht", "winner", "api_last_updated",
]
SQL_TYPES = {
    "match_id": sqltypes.BigInteger(), "matchday": sqltypes.SmallInteger(),
    "utc_kickoff": sqltypes.DateTime(timezone=True), "match_date": sqltypes.Date(),
    "api_last_updated": sqltypes.DateTime(timezone=True),
    "home_team_id": sqltypes.Integer(), "away_team_id": sqltypes.Integer(),
    **{c: sqltypes.SmallInteger() for c in ("home_goals", "away_goals", "home_goals_ht", "away_goals_ht")},
    **{c: sqltypes.Text() for c in ("league_code", "competition_code", "season", "status", "home_team_name",
                                    "home_team_short", "away_team_name", "away_team_short", "winner")},
}


class ApiError(RuntimeError):
    pass


def get_api_key() -> str:
    key = os.getenv("FOOTBALL_DATA_API_KEY", "").strip()
    if not key or key == "your-key-here":
        raise ApiError("FOOTBALL_DATA_API_KEY is missing: add your football-data.org token to .env")
    return key


def fetch_competition(competition: str, api_key: str, session: requests.Session | None = None) -> dict:
    """GET /competitions/{code}/matches for the current season, with retries on rate limits."""
    session = session or requests.Session()
    url = f"{API_BASE_URL}/competitions/{competition}/matches"
    for attempt in range(4):
        resp = session.get(url, headers={"X-Auth-Token": api_key}, timeout=30)
        if resp.status_code == 429:  # rate limit hit: the API says how long to wait
            wait = int(resp.headers.get("X-RequestCounter-Reset", 60)) + 1
            log.warning("Rate limit reached, waiting %ss", wait)
            time.sleep(wait)
            continue
        if resp.status_code in (401, 403):
            raise ApiError(f"Access refused for {competition} ({resp.status_code}): check your API key and plan")
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise ApiError(f"Could not fetch {competition} after several attempts")


def parse_matches(payload: dict, league_code: str) -> pd.DataFrame:
    """Turn the API's nested JSON into one flat row per match."""
    rows = []
    for m in payload.get("matches", []):
        if not (m.get("homeTeam") or {}).get("id") or not (m.get("awayTeam") or {}).get("id"):
            continue  # fixture whose teams are not known yet
        score = m.get("score") or {}
        full, half = score.get("fullTime") or {}, score.get("halfTime") or {}
        season_start = int(((m.get("season") or {}).get("startDate") or str(payload["filters"]["season"]))[:4])
        rows.append({
            "match_id": m["id"],
            "league_code": league_code,
            "competition_code": (m.get("competition") or payload.get("competition") or {}).get("code"),
            "season": season_label(season_start),
            "matchday": m.get("matchday"),
            "utc_kickoff": m["utcDate"],
            "status": m["status"],
            "home_team_id": m["homeTeam"]["id"],
            "home_team_name": m["homeTeam"]["name"],
            "home_team_short": m["homeTeam"].get("shortName"),
            "away_team_id": m["awayTeam"]["id"],
            "away_team_name": m["awayTeam"]["name"],
            "away_team_short": m["awayTeam"].get("shortName"),
            "home_goals": full.get("home"),
            "away_goals": full.get("away"),
            "home_goals_ht": half.get("home"),
            "away_goals_ht": half.get("away"),
            "winner": score.get("winner"),
            "api_last_updated": m.get("lastUpdated"),
        })
    df = pd.DataFrame(rows, columns=[c for c in DB_COLUMNS if c != "match_date"])
    if df.empty:
        return pd.DataFrame(columns=DB_COLUMNS)

    df["utc_kickoff"] = pd.to_datetime(df["utc_kickoff"], utc=True)
    df["api_last_updated"] = pd.to_datetime(df["api_last_updated"], utc=True, errors="coerce")
    df["match_date"] = df["utc_kickoff"].dt.date
    for col in ("matchday", "home_goals", "away_goals", "home_goals_ht", "away_goals_ht"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    df = df[DB_COLUMNS]
    return df.astype(object).where(df.notna(), None)


UPSERT_SQL = f"""
INSERT INTO raw.api_matches ({", ".join(DB_COLUMNS)})
SELECT {", ".join(DB_COLUMNS)} FROM tmp_api_matches
ON CONFLICT (match_id) DO UPDATE SET
    {", ".join(f"{c} = EXCLUDED.{c}" for c in DB_COLUMNS if c != "match_id")},
    loaded_at = now();
"""


def upsert(engine: Engine, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TEMP TABLE tmp_api_matches (LIKE raw.api_matches INCLUDING DEFAULTS) ON COMMIT DROP")
        df.to_sql("tmp_api_matches", conn, if_exists="append", index=False, method="multi", chunksize=500, dtype=SQL_TYPES)
        conn.exec_driver_sql(UPSERT_SQL)
    return len(df)


def run(leagues: list[str], engine: Engine | None = None, session: requests.Session | None = None) -> int:
    engine = engine or get_engine()
    init_schema(engine)
    api_key = get_api_key()
    total = 0
    for i, league in enumerate(leagues):
        if i:
            time.sleep(API_SECONDS_BETWEEN_CALLS)
        payload = fetch_competition(API_COMPETITIONS[league], api_key, session=session)
        df = parse_matches(payload, league)
        n = upsert(engine, df)
        total += n
        finished = int((df["status"] == "FINISHED").sum()) if n else 0
        log.info("%-4s %s  %3d matches (%d finished, %d to play)", league, LEAGUES[league], n, finished, n - finished)
    log.info("Done: %d matches loaded or updated", total)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch current-season matches from football-data.org")
    parser.add_argument("--leagues", nargs="+", default=list(API_COMPETITIONS), choices=list(API_COMPETITIONS))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    run(args.leagues)


if __name__ == "__main__":
    main()