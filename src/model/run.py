"""Step 4: Elo ratings, backtest and predictions for upcoming matches.

Reads the dbt marts (step 3) and writes three tables in the `model` schema:
  * model.elo_ratings        rating of every team before and after each match
  * model.backtest_results   how the model would have done on past seasons, vs bookmakers
  * model.match_predictions  probabilities for upcoming matches (kept forever, never overwritten)

Usage:
    python -m src.model.run elo          # rebuild Elo ratings
    python -m src.model.run backtest     # score the model on the last 3 completed seasons
    python -m src.model.run predict      # predict matches in the next 10 days
    python -m src.model.run all          # all three, in that order
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.db import get_engine, init_schema
from src.model.elo import EloParams, compute_elo, current_ratings
from src.model.poisson_model import GoalsModel, add_league_averages, score_predictions

log = logging.getLogger("model")

MODEL_VERSION = "elo-poisson-v1"
ELO = EloParams()
BURN_IN_SEASONS = 1        # Elo needs a season to settle, so the first one is not used for training
BACKTEST_SEASONS = 3
PREDICTION_HORIZON_DAYS = 10


# ------------------------------------------------------------------ loading

def load_data(engine: Engine) -> dict[str, pd.DataFrame]:
    with engine.connect() as conn:
        matches = pd.read_sql(text("""
            select match_key, league_code, season, match_date, is_played, home_team, away_team,
                   home_goals, away_goals, result, implied_prob_home, implied_prob_draw, implied_prob_away
            from marts.fct_matches"""), conn)
        form = pd.read_sql(text("""
            select match_key, team, form_points_last5 from marts.fct_team_form"""), conn)
        recent = pd.read_sql(text("""
            -- points from each team's last 5 played matches: form going into its next match
            select team, league_code, sum(points) as form_points_last5
            from (
                select team, league_code, points,
                       row_number() over (partition by league_code, team order by match_date desc, match_key desc) as rn
                from intermediate.int_team_matches
            ) t
            where rn <= 5
            group by team, league_code"""), conn)
        league_seasons = pd.read_sql(text("select * from marts.fct_league_seasons"), conn)
    matches["match_date"] = pd.to_datetime(matches["match_date"]).dt.date
    return {"matches": matches, "form": form, "recent_form": recent, "league_seasons": league_seasons}


def played(matches: pd.DataFrame) -> pd.DataFrame:
    return matches[matches["is_played"] & matches["home_goals"].notna()].copy()


# --------------------------------------------------------------------- elo

def build_elo(engine: Engine, data: dict) -> pd.DataFrame:
    elo = compute_elo(played(data["matches"]), ELO)
    with engine.begin() as conn:
        conn.exec_driver_sql("TRUNCATE model.elo_ratings")
        elo.to_sql("elo_ratings", conn, schema="model", if_exists="append", index=False, method="multi", chunksize=1000)
    top = elo.sort_values("match_date").groupby("team").tail(1).nlargest(5, "rating_after")
    log.info("Elo ratings computed for %d team-matches. Current top 5: %s", len(elo),
             ", ".join(f"{t} {r:.0f}" for t, r in zip(top["team"], top["rating_after"])))
    return elo


def training_frame(data: dict, elo: pd.DataFrame) -> pd.DataFrame:
    """Played matches with every feature as it was known BEFORE kickoff."""
    df = played(data["matches"])
    before = elo.set_index(["match_key", "team"])["rating_before"].astype(float)
    form = data["form"].set_index(["match_key", "team"])["form_points_last5"].astype(float)
    keys_home = list(zip(df["match_key"], df["home_team"]))
    keys_away = list(zip(df["match_key"], df["away_team"]))
    df["home_elo"] = before.reindex(keys_home).to_numpy()
    df["away_elo"] = before.reindex(keys_away).to_numpy()
    df["home_form"] = form.reindex(keys_home).to_numpy()
    df["away_form"] = form.reindex(keys_away).to_numpy()
    return add_league_averages(df, data["league_seasons"])


# ---------------------------------------------------------------- backtest

def backtest(engine: Engine, data: dict, elo: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward: for each test season, train only on earlier seasons."""
    df = training_frame(data, elo)
    seasons = sorted(df["season"].unique())
    current = max(seasons)
    completed = [s for s in seasons if s != current]
    test_seasons = completed[-BACKTEST_SEASONS:]

    rows = []
    for test_season in test_seasons:
        train = df[(df["season"] < test_season) & (df["season"] > seasons[BURN_IN_SEASONS - 1])]
        if train.empty:
            train = df[df["season"] < test_season]
        test = df[df["season"] == test_season].copy()
        if train.empty or test.empty:
            continue

        model = GoalsModel(home_advantage=ELO.home_advantage).fit(train)
        pred = model.predict(test)
        model_probs = pred[["prob_home", "prob_draw", "prob_away"]].to_numpy()

        # Compare on the matches that have bookmaker odds, so all three are scored on the same games.
        has_odds = test["implied_prob_home"].notna().to_numpy()
        base_rates = train["result"].value_counts(normalize=True).reindex(["H", "D", "A"]).fillna(0).to_numpy()
        predictors = {
            "model": model_probs[has_odds],
            "bookmaker": test.loc[has_odds, ["implied_prob_home", "implied_prob_draw", "implied_prob_away"]].astype(float).to_numpy(),
            "baseline": np.tile(base_rates, (int(has_odds.sum()), 1)),
        }
        if not has_odds.any():   # no odds at all: still score model and baseline on every match
            predictors = {"model": model_probs, "baseline": np.tile(base_rates, (len(test), 1))}
            has_odds = np.ones(len(test), dtype=bool)

        results = test.loc[has_odds, "result"]
        for name, probs in predictors.items():
            rows.append({"model_version": MODEL_VERSION, "test_season": test_season, "predictor": name,
                         **score_predictions(probs, results)})

    report = pd.DataFrame(rows)
    if report.empty:
        log.warning("Not enough seasons to backtest")
        return report
    with engine.begin() as conn:
        report.round(4).to_sql("backtest_results", conn, schema="model", if_exists="append", index=False)

    summary = report.groupby("predictor")[["accuracy", "log_loss", "rps"]].mean().sort_values("rps")
    log.info("Backtest on %s (lower RPS is better):\n%s", ", ".join(test_seasons), summary.round(4).to_string())
    return report


# ----------------------------------------------------------------- predict

def predict_upcoming(engine: Engine, data: dict, elo: pd.DataFrame, horizon_days: int = PREDICTION_HORIZON_DAYS,
                     today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    matches = data["matches"]
    upcoming = matches[~matches["is_played"]
                       & (matches["match_date"] >= today)
                       & (matches["match_date"] <= today + timedelta(days=horizon_days))].copy()
    if upcoming.empty:
        log.info("No matches in the next %d days", horizon_days)
        return upcoming

    train = training_frame(data, elo)
    seasons = sorted(train["season"].unique())
    train = train[train["season"] > seasons[BURN_IN_SEASONS - 1]] if len(seasons) > BURN_IN_SEASONS else train
    model = GoalsModel(home_advantage=ELO.home_advantage).fit(train)

    season = upcoming["season"].max()
    ratings = current_ratings(elo, upcoming_season=season, params=ELO)
    recent = data["recent_form"].set_index(["league_code", "team"])["form_points_last5"].astype(float)
    upcoming["home_elo"] = upcoming["home_team"].map(ratings).fillna(1500.0)
    upcoming["away_elo"] = upcoming["away_team"].map(ratings).fillna(1500.0)
    upcoming["home_form"] = recent.reindex(list(zip(upcoming["league_code"], upcoming["home_team"]))).to_numpy()
    upcoming["away_form"] = recent.reindex(list(zip(upcoming["league_code"], upcoming["away_team"]))).to_numpy()
    upcoming = add_league_averages(upcoming, data["league_seasons"])

    out = pd.concat([upcoming.reset_index(drop=True), model.predict(upcoming).reset_index(drop=True)], axis=1)
    out["model_version"] = MODEL_VERSION
    columns = ["model_version", "match_key", "league_code", "season", "match_date", "home_team", "away_team",
               "home_elo", "away_elo", "expected_home_goals", "expected_away_goals",
               "prob_home", "prob_draw", "prob_away", "most_likely_score"]
    out = out[columns]
    out[["home_elo", "away_elo"]] = out[["home_elo", "away_elo"]].round(1)
    with engine.begin() as conn:
        out.to_sql("match_predictions", conn, schema="model", if_exists="append", index=False, method="multi")

    log.info("Saved %d predictions for the next %d days. A few of them:", len(out), horizon_days)
    for r in out.sort_values("match_date").head(5).itertuples():
        log.info("  %s  %s vs %s  ->  H %.0f%% / D %.0f%% / A %.0f%%  (most likely %s)", r.match_date, r.home_team,
                 r.away_team, 100 * r.prob_home, 100 * r.prob_draw, 100 * r.prob_away, r.most_likely_score)
    return out


# -------------------------------------------------------------------- main

def main() -> None:
    parser = argparse.ArgumentParser(description="Elo ratings, backtest and match predictions")
    parser.add_argument("command", choices=["elo", "backtest", "predict", "all"])
    parser.add_argument("--days", type=int, default=PREDICTION_HORIZON_DAYS, help="prediction horizon in days")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    engine = get_engine()
    init_schema(engine)
    data = load_data(engine)
    elo = build_elo(engine, data)
    if args.command in ("backtest", "all"):
        backtest(engine, data, elo)
    if args.command in ("predict", "all"):
        predict_upcoming(engine, data, elo, horizon_days=args.days)


if __name__ == "__main__":
    main()
