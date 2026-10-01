-- Outputs of the prediction model (step 4), written by src/model/run.py.

CREATE SCHEMA IF NOT EXISTS model;

-- Elo rating of each team before and after every played match (rebuilt on every run).
CREATE TABLE IF NOT EXISTS model.elo_ratings (
    match_key       TEXT        NOT NULL,
    league_code     TEXT        NOT NULL,
    season          TEXT        NOT NULL,
    match_date      DATE        NOT NULL,
    team            TEXT        NOT NULL,
    opponent        TEXT        NOT NULL,
    is_home         BOOLEAN     NOT NULL,
    rating_before   NUMERIC(7,1) NOT NULL,
    rating_after    NUMERIC(7,1) NOT NULL,
    PRIMARY KEY (match_key, team)
);

-- Every prediction ever made. Rows are never overwritten, so the dashboard can show
-- what the model said BEFORE each match and measure its real track record.
CREATE TABLE IF NOT EXISTS model.match_predictions (
    prediction_id       BIGSERIAL   PRIMARY KEY,
    predicted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_version       TEXT        NOT NULL,
    match_key           TEXT        NOT NULL,
    league_code         TEXT        NOT NULL,
    season              TEXT        NOT NULL,
    match_date          DATE        NOT NULL,
    home_team           TEXT        NOT NULL,
    away_team           TEXT        NOT NULL,
    home_elo            NUMERIC(7,1),
    away_elo            NUMERIC(7,1),
    expected_home_goals NUMERIC(5,2) NOT NULL,
    expected_away_goals NUMERIC(5,2) NOT NULL,
    prob_home           NUMERIC(5,4) NOT NULL,
    prob_draw           NUMERIC(5,4) NOT NULL,
    prob_away           NUMERIC(5,4) NOT NULL,
    most_likely_score   TEXT        NOT NULL,
    UNIQUE (match_key, model_version, predicted_at)
);
CREATE INDEX IF NOT EXISTS idx_pred_match ON model.match_predictions (match_key, predicted_at);

-- Walk-forward backtest: the model trained on earlier seasons, scored on the next one.
CREATE TABLE IF NOT EXISTS model.backtest_results (
    run_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_version   TEXT        NOT NULL,
    test_season     TEXT        NOT NULL,
    predictor       TEXT        NOT NULL,   -- model / bookmaker / baseline
    matches         INTEGER     NOT NULL,
    accuracy        NUMERIC(5,4),
    log_loss        NUMERIC(6,4),
    brier_score     NUMERIC(6,4),
    rps             NUMERIC(6,4),           -- ranked probability score: the standard metric for football
    PRIMARY KEY (run_at, test_season, predictor)
);
