"""Match outcome model: Elo ratings + Poisson goals.

Two Poisson regressions predict how many goals each team will score, from:
  * the Elo difference (who is stronger, including home advantage),
  * both teams' recent form (points from their last 5 matches),
  * how many goals home and away teams scored in that league the season before.

The two expected-goal numbers give the probability of every scoreline, and adding
those up gives the probabilities of a home win, a draw and an away win.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor

MAX_GOALS = 10                 # scorelines up to 10-10 cover virtually all the probability
DEFAULT_FORM_POINTS = 7.0      # average points from 5 matches, used when a team has no history yet
OUTCOMES = ["H", "D", "A"]


# ---------------------------------------------------------------- features

def add_league_averages(matches: pd.DataFrame, league_seasons: pd.DataFrame) -> pd.DataFrame:
    """Attach the PREVIOUS season's average home and away goals of each league.

    Using last season's averages (not the current one's) keeps the feature free of
    information from matches that had not been played yet.
    """
    ls = league_seasons[["league_code", "season", "avg_home_goals", "avg_away_goals"]].copy()
    ls[["avg_home_goals", "avg_away_goals"]] = ls[["avg_home_goals", "avg_away_goals"]].astype(float)
    ls = ls.sort_values(["league_code", "season"])
    ls["league_home_goals"] = ls.groupby("league_code")["avg_home_goals"].shift(1)
    ls["league_away_goals"] = ls.groupby("league_code")["avg_away_goals"].shift(1)

    out = matches.merge(ls[["league_code", "season", "league_home_goals", "league_away_goals"]],
                        on=["league_code", "season"], how="left")

    # A season with no played match yet: use the league's latest completed averages.
    latest = ls.groupby("league_code").tail(1).set_index("league_code")
    known = set(zip(ls["league_code"], ls["season"]))
    missing = out["league_home_goals"].isna() & np.array([(l, s) not in known for l, s in zip(out["league_code"], out["season"])], dtype=bool)
    out.loc[missing, "league_home_goals"] = out.loc[missing, "league_code"].map(latest["avg_home_goals"])
    out.loc[missing, "league_away_goals"] = out.loc[missing, "league_code"].map(latest["avg_away_goals"])

    # First season of the data: no previous season, use the overall average.
    out["league_home_goals"] = out["league_home_goals"].fillna(ls["avg_home_goals"].mean())
    out["league_away_goals"] = out["league_away_goals"].fillna(ls["avg_away_goals"].mean())
    return out


def home_features(df: pd.DataFrame, home_advantage: float) -> np.ndarray:
    return np.column_stack([
        (df["home_elo"] + home_advantage - df["away_elo"]) / 100,
        df["home_form"].fillna(DEFAULT_FORM_POINTS),
        df["away_form"].fillna(DEFAULT_FORM_POINTS),
        df["league_home_goals"],
    ])


def away_features(df: pd.DataFrame, home_advantage: float) -> np.ndarray:
    return np.column_stack([
        (df["away_elo"] - df["home_elo"] - home_advantage) / 100,
        df["away_form"].fillna(DEFAULT_FORM_POINTS),
        df["home_form"].fillna(DEFAULT_FORM_POINTS),
        df["league_away_goals"],
    ])


# ------------------------------------------------------------------- model

@dataclass
class GoalsModel:
    home_advantage: float = 60.0
    alpha: float = 1e-4

    def fit(self, train: pd.DataFrame) -> "GoalsModel":
        self.home_model = PoissonRegressor(alpha=self.alpha, max_iter=1000).fit(
            home_features(train, self.home_advantage), train["home_goals"].astype(float))
        self.away_model = PoissonRegressor(alpha=self.alpha, max_iter=1000).fit(
            away_features(train, self.home_advantage), train["away_goals"].astype(float))
        return self

    def expected_goals(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        return (self.home_model.predict(home_features(df, self.home_advantage)),
                self.away_model.predict(away_features(df, self.home_advantage)))

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Expected goals, outcome probabilities and the most likely score for each match."""
        lam_home, lam_away = self.expected_goals(df)
        probs, scores = outcome_probabilities(lam_home, lam_away)
        return pd.DataFrame({
            "expected_home_goals": lam_home.round(2),
            "expected_away_goals": lam_away.round(2),
            "prob_home": probs[:, 0].round(4),
            "prob_draw": probs[:, 1].round(4),
            "prob_away": probs[:, 2].round(4),
            "most_likely_score": scores,
        }, index=df.index)


def outcome_probabilities(lam_home: np.ndarray, lam_away: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Home/draw/away probabilities from two independent Poisson goal distributions."""
    goals = np.arange(MAX_GOALS + 1)
    p_home = poisson.pmf(goals[None, :], np.asarray(lam_home)[:, None])   # matches x goals
    p_away = poisson.pmf(goals[None, :], np.asarray(lam_away)[:, None])
    grid = p_home[:, :, None] * p_away[:, None, :]                         # matches x home goals x away goals
    grid /= grid.sum(axis=(1, 2), keepdims=True)

    home_win = np.tril(np.ones((MAX_GOALS + 1, MAX_GOALS + 1)), k=-1)     # home goals > away goals
    probs = np.column_stack([
        (grid * home_win).sum(axis=(1, 2)),
        np.trace(grid, axis1=1, axis2=2),
        (grid * home_win.T).sum(axis=(1, 2)),
    ])
    best = grid.reshape(len(grid), -1).argmax(axis=1)
    scores = [f"{i // (MAX_GOALS + 1)}-{i % (MAX_GOALS + 1)}" for i in best]
    return probs, scores


# ----------------------------------------------------------------- metrics

def one_hot(results: pd.Series) -> np.ndarray:
    return np.column_stack([(results == o).astype(float) for o in OUTCOMES])


def score_predictions(probs: np.ndarray, results: pd.Series) -> dict[str, float]:
    """Accuracy, log loss, Brier score and ranked probability score (lower is better except accuracy)."""
    probs = np.clip(np.asarray(probs, dtype=float), 1e-12, 1)
    probs = probs / probs.sum(axis=1, keepdims=True)
    actual = one_hot(results.reset_index(drop=True))
    cum_p, cum_a = np.cumsum(probs, axis=1)[:, :2], np.cumsum(actual, axis=1)[:, :2]
    return {
        "matches": int(len(actual)),
        "accuracy": float((probs.argmax(axis=1) == actual.argmax(axis=1)).mean()),
        "log_loss": float(-np.log((probs * actual).sum(axis=1)).mean()),
        "brier_score": float(((probs - actual) ** 2).sum(axis=1).mean()),
        "rps": float(((cum_p - cum_a) ** 2).sum(axis=1).mean() / 2),
    }
