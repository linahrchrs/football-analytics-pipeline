-- Raw layer: data as received from the sources, lightly typed.
-- Cleaning and modelling happen later in dbt.

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.historical_matches (
    league_code             TEXT        NOT NULL,   -- e.g. E0 = Premier League
    season                  TEXT        NOT NULL,   -- e.g. 2023-24
    match_date              DATE        NOT NULL,
    kickoff_time            TIME,
    home_team               TEXT        NOT NULL,
    away_team               TEXT        NOT NULL,
    home_goals              SMALLINT,
    away_goals              SMALLINT,
    result                  CHAR(1),                -- H / D / A
    home_goals_ht           SMALLINT,
    away_goals_ht           SMALLINT,
    result_ht               CHAR(1),
    referee                 TEXT,
    home_shots              SMALLINT,
    away_shots              SMALLINT,
    home_shots_on_target    SMALLINT,
    away_shots_on_target    SMALLINT,
    home_fouls              SMALLINT,
    away_fouls              SMALLINT,
    home_corners            SMALLINT,
    away_corners            SMALLINT,
    home_yellow_cards       SMALLINT,
    away_yellow_cards       SMALLINT,
    home_red_cards          SMALLINT,
    away_red_cards          SMALLINT,
    odds_home               NUMERIC(6,2),           -- Bet365 odds, used later as a
    odds_draw               NUMERIC(6,2),           -- benchmark for our own model
    odds_away               NUMERIC(6,2),
    source_file             TEXT        NOT NULL,
    loaded_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (league_code, match_date, home_team, away_team)
);

CREATE INDEX IF NOT EXISTS idx_hist_league_season
    ON raw.historical_matches (league_code, season);