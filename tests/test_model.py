"""Tests for the Elo ratings and the Poisson model (no database needed)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.model.elo import EloParams, compute_elo, current_ratings, expected_score, margin_multiplier
from src.model.poisson_model import GoalsModel, add_league_averages, outcome_probabilities, score_predictions


def make_matches(rows):
    return pd.DataFrame(rows, columns=["match_key", "league_code", "season", "match_date",
                                       "home_team", "away_team", "home_goals", "away_goals"])


def test_expected_score_is_symmetric():
    assert expected_score(1500, 1500) == pytest.approx(0.5)
    assert expected_score(1600, 1500) + expected_score(1500, 1600) == pytest.approx(1)
    assert expected_score(1900, 1500) > 0.9


def test_margin_multiplier():
    assert margin_multiplier(1) == 1 and margin_multiplier(-1) == 1
    assert margin_multiplier(2) == 1.5
    assert margin_multiplier(4) == pytest.approx(15 / 8)


def test_elo_is_zero_sum_and_rewards_the_winner():
    elo = compute_elo(make_matches([("m1", "E0", "2024-25", date(2024, 8, 10), "A", "B", 2, 0)]))
    a, b = elo.set_index("team").loc["A"], elo.set_index("team").loc["B"]
    assert a["rating_before"] == b["rating_before"] == 1500
    assert a["rating_after"] > 1500 > b["rating_after"]
    assert (a["rating_after"] - 1500) == pytest.approx(1500 - b["rating_after"], abs=0.1)


def test_elo_uses_only_past_matches():
    elo = compute_elo(make_matches([
        ("m1", "E0", "2024-25", date(2024, 8, 10), "A", "B", 3, 0),
        ("m2", "E0", "2024-25", date(2024, 8, 17), "A", "C", 0, 0),
    ]))
    m2_a = elo[(elo["match_key"] == "m2") & (elo["team"] == "A")].iloc[0]
    m1_a = elo[(elo["match_key"] == "m1") & (elo["team"] == "A")].iloc[0]
    assert m2_a["rating_before"] == m1_a["rating_after"]     # rating going into m2 = rating after m1


def test_new_season_pulls_ratings_toward_average():
    params = EloParams(season_regression=0.5)
    elo = compute_elo(make_matches([
        ("m1", "E0", "2024-25", date(2025, 5, 1), "A", "B", 5, 0),
        ("m2", "E0", "2025-26", date(2025, 8, 10), "A", "B", 0, 0),
    ]), params)
    after_m1 = elo[(elo["match_key"] == "m1") & (elo["team"] == "A")]["rating_after"].iloc[0]
    before_m2 = elo[(elo["match_key"] == "m2") & (elo["team"] == "A")]["rating_before"].iloc[0]
    assert before_m2 == pytest.approx(1500 + 0.5 * (after_m1 - 1500), abs=0.1)
    ratings = current_ratings(elo, upcoming_season="2026-27", params=params)
    assert abs(ratings["A"] - 1500) < abs(elo[elo["team"] == "A"]["rating_after"].iloc[-1] - 1500)


def test_outcome_probabilities_sum_to_one_and_follow_strength():
    probs, scores = outcome_probabilities(np.array([2.5, 1.0, 0.5]), np.array([0.5, 1.0, 2.5]))
    assert np.allclose(probs.sum(axis=1), 1)
    assert probs[0, 0] > 0.7 and probs[2, 2] > 0.7
    assert probs[1, 0] == pytest.approx(probs[1, 2])          # equal teams: home and away equally likely
    assert scores[0] == "2-0"


def test_scores_reward_better_predictions():
    results = pd.Series(["H", "D", "A"])
    perfect = score_predictions(np.eye(3), results)
    uniform = score_predictions(np.full((3, 3), 1 / 3), results)
    assert perfect["accuracy"] == 1 and perfect["rps"] == pytest.approx(0, abs=1e-6)
    assert uniform["rps"] > perfect["rps"] and uniform["log_loss"] > perfect["log_loss"]


def test_league_averages_come_from_the_previous_season():
    league_seasons = pd.DataFrame({"league_code": ["E0", "E0"], "season": ["2023-24", "2024-25"],
                                   "avg_home_goals": [1.5, 1.7], "avg_away_goals": [1.2, 1.3]})
    matches = pd.DataFrame({"league_code": ["E0", "E0", "E0"], "season": ["2023-24", "2024-25", "2025-26"]})
    out = add_league_averages(matches, league_seasons).set_index("season")
    assert out.loc["2024-25", "league_home_goals"] == 1.5      # previous season, not its own
    assert out.loc["2025-26", "league_home_goals"] == 1.7      # season with no data yet: latest available
    assert out.loc["2023-24", "league_home_goals"] == pytest.approx(1.6)  # first season: overall average


def test_model_learns_that_stronger_teams_score_more():
    rng = np.random.default_rng(0)
    n = 3000
    diff = rng.normal(0, 150, n)
    df = pd.DataFrame({"home_elo": 1500 + diff / 2, "away_elo": 1500 - diff / 2,
                       "home_form": 7.0, "away_form": 7.0, "league_home_goals": 1.5, "league_away_goals": 1.2})
    df["home_goals"] = rng.poisson(np.exp(0.35 + (diff + 60) / 400))
    df["away_goals"] = rng.poisson(np.exp(0.15 - (diff + 60) / 400))
    model = GoalsModel().fit(df)
    test = df.iloc[:2].copy()
    test[["home_elo", "away_elo"]] = [[1700, 1400], [1400, 1700]]
    pred = model.predict(test)
    assert pred.iloc[0]["prob_home"] > 0.6 > pred.iloc[1]["prob_home"]
    assert pred.iloc[0]["expected_home_goals"] > pred.iloc[1]["expected_home_goals"]
