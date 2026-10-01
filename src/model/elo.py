"""Elo ratings for football teams.

Each team starts at 1500. After every match, the winner takes rating points from
the loser: more points for an unexpected result and for a wide margin. Ratings
carry over between seasons (pulled a little toward the average), and between
divisions, so a promoted Championship team keeps its rating in the Premier League.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

INITIAL_RATING = 1500.0


@dataclass(frozen=True)
class EloParams:
    k: float = 20.0                  # how fast ratings move
    home_advantage: float = 60.0     # rating points added to the home team when computing expectations
    season_regression: float = 0.2   # share of the gap to 1500 removed at the start of each season


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability-like expected score of A against B (1 = win, 0.5 = draw, 0 = loss)."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))


def margin_multiplier(goal_difference: int) -> float:
    """Bigger wins move ratings more (World Football Elo convention)."""
    gd = abs(goal_difference)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8


def compute_elo(matches: pd.DataFrame, params: EloParams = EloParams()) -> pd.DataFrame:
    """Replay every played match in date order and return one row per team per match.

    `matches` needs: match_key, league_code, season, match_date, home_team, away_team,
    home_goals, away_goals. Returns rating_before / rating_after for both teams.
    """
    ratings: dict[str, float] = {}
    last_season: dict[str, str] = {}
    rows = []

    ordered = matches.sort_values(["match_date", "league_code", "match_key"])
    for m in ordered.itertuples(index=False):
        for team in (m.home_team, m.away_team):
            if team not in ratings:
                ratings[team] = INITIAL_RATING
            elif last_season.get(team) != m.season:
                ratings[team] += params.season_regression * (INITIAL_RATING - ratings[team])
            last_season[team] = m.season

        home_before, away_before = ratings[m.home_team], ratings[m.away_team]
        expected_home = expected_score(home_before + params.home_advantage, away_before)
        actual_home = 1.0 if m.home_goals > m.away_goals else 0.5 if m.home_goals == m.away_goals else 0.0
        change = params.k * margin_multiplier(m.home_goals - m.away_goals) * (actual_home - expected_home)

        ratings[m.home_team] = home_before + change
        ratings[m.away_team] = away_before - change
        common = {"match_key": m.match_key, "league_code": m.league_code, "season": m.season, "match_date": m.match_date}
        rows.append({**common, "team": m.home_team, "opponent": m.away_team, "is_home": True,
                     "rating_before": round(home_before, 1), "rating_after": round(ratings[m.home_team], 1)})
        rows.append({**common, "team": m.away_team, "opponent": m.home_team, "is_home": False,
                     "rating_before": round(away_before, 1), "rating_after": round(ratings[m.away_team], 1)})

    return pd.DataFrame(rows)


def current_ratings(elo_history: pd.DataFrame, upcoming_season: str | None = None,
                    params: EloParams = EloParams()) -> dict[str, float]:
    """Latest rating of every team, with the new-season adjustment applied if needed."""
    latest = elo_history.sort_values(["match_date", "match_key"]).groupby("team").tail(1)
    ratings = {}
    for r in latest.itertuples(index=False):
        rating = float(r.rating_after)
        if upcoming_season and r.season != upcoming_season:
            rating += params.season_regression * (INITIAL_RATING - rating)
        ratings[r.team] = rating
    return ratings
