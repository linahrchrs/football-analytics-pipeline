"""Database access for the dashboard. Every query is cached for an hour:
the pipeline only updates the data once a day."""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

LOCAL_URL = "postgresql+psycopg://football:football@localhost:5433/football"


def _database_url() -> str:
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:  # no secrets file when running locally
        pass
    load_dotenv()
    return os.getenv("DATABASE_URL", LOCAL_URL)


@st.cache_resource
def engine():
    return create_engine(_database_url(), pool_pre_ping=True)


@st.cache_data(ttl=3600, show_spinner=False)
def query(sql: str, **params) -> pd.DataFrame:
    with engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def leagues() -> pd.DataFrame:
    return query("""
        select league_code, league_name, country from seeds.leagues
        order by array_position(array['E0','SP1','D1','I1','F1','E1','N1','P1'], league_code::text)""")


def upcoming_predictions(league_code: str | None) -> pd.DataFrame:
    return query("""
        select * from marts.fct_prediction_results
        where not coalesce(is_played, false) and match_date >= current_date
          and (cast(:lg as text) is null or league_code = :lg)
        order by match_date, league_code, home_team""", lg=league_code)


def finished_predictions() -> pd.DataFrame:
    return query("""
        select * from marts.fct_prediction_results
        where is_played order by match_date desc, league_code""")


def backtest() -> pd.DataFrame:
    return query("""
        select test_season, predictor, matches, accuracy, log_loss, brier_score, rps
        from model.backtest_results
        where run_at = (select max(run_at) from model.backtest_results)
        order by test_season, predictor""")


def seasons(league_code: str) -> list[str]:
    df = query("select distinct season from marts.fct_standings where league_code = :lg order by season desc",
               lg=league_code)
    return df["season"].tolist()


def standings(league_code: str, season: str) -> pd.DataFrame:
    return query("""
        select s.position, s.team, s.played, s.won, s.drawn, s.lost, s.goals_for, s.goals_against,
               s.goal_difference, s.points, r.rating as elo
        from marts.fct_standings s
        left join marts.fct_team_ratings r on r.team = s.team
        where s.league_code = :lg and s.season = :season
        order by s.position, s.team""", lg=league_code, season=season)


def recent_form(league_code: str, season: str) -> pd.DataFrame:
    return query("""
        select team, string_agg(outcome, '' order by match_date) as form
        from (
            select team, outcome, match_date,
                   row_number() over (partition by team order by match_date desc) as rn
            from intermediate.int_team_matches
            where league_code = :lg and season = :season
        ) t
        where rn <= 5
        group by team""", lg=league_code, season=season)


def league_seasons(league_code: str) -> pd.DataFrame:
    return query("select * from marts.fct_league_seasons where league_code = :lg order by season", lg=league_code)


def team_ratings(league_code: str) -> pd.DataFrame:
    return query("""
        select team, rating, league_rank, change_last_5, last_match_date
        from marts.fct_team_ratings where league_code = :lg order by league_rank""", lg=league_code)


def teams(league_code: str) -> list[str]:
    return team_ratings(league_code)["team"].tolist()


def elo_history(team: str) -> pd.DataFrame:
    return query("""
        select match_date, season, league_code, opponent, is_home, rating_before, rating_after
        from model.elo_ratings where team = :team order by match_date""", team=team)


def team_matches(team: str, limit: int = 10) -> pd.DataFrame:
    return query("""
        select match_date, season, league_name, home_team, away_team, home_goals, away_goals, result, is_played
        from marts.fct_matches
        where (home_team = :team or away_team = :team) and is_played
        order by match_date desc limit :limit""", team=team, limit=limit)


def team_seasons(team: str) -> pd.DataFrame:
    return query("""
        select season, league_code, position, played, won, drawn, lost, goals_for, goals_against, points
        from marts.fct_standings where team = :team order by season desc""", team=team)


def last_update() -> pd.Timestamp | None:
    df = query("select max(loaded_at) as t from raw.api_matches")
    return df["t"].iloc[0] if not df.empty else None
