-- Current-season fixtures and results from the football-data.org API.
-- One row per match; updated every day (scores, status, rescheduled dates).

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.api_matches (
    match_id            BIGINT      PRIMARY KEY,    -- football-data.org id
    league_code         TEXT        NOT NULL,       -- our code, e.g. E0
    competition_code    TEXT        NOT NULL,       -- API code, e.g. PL
    season              TEXT        NOT NULL,       -- e.g. 2026-27
    matchday            SMALLINT,
    utc_kickoff         TIMESTAMPTZ NOT NULL,
    match_date          DATE        NOT NULL,       -- kickoff date (UTC)
    status              TEXT        NOT NULL,       -- SCHEDULED, TIMED, FINISHED, POSTPONED...
    home_team_id        INTEGER     NOT NULL,
    home_team_name      TEXT        NOT NULL,       -- e.g. "Manchester United FC"
    home_team_short     TEXT,                       -- e.g. "Man United"
    away_team_id        INTEGER     NOT NULL,
    away_team_name      TEXT        NOT NULL,
    away_team_short     TEXT,
    home_goals          SMALLINT,                   -- NULL until the match is played
    away_goals          SMALLINT,
    home_goals_ht       SMALLINT,
    away_goals_ht       SMALLINT,
    winner              TEXT,                       -- HOME_TEAM / AWAY_TEAM / DRAW
    api_last_updated    TIMESTAMPTZ,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_league_date ON raw.api_matches (league_code, match_date);
CREATE INDEX IF NOT EXISTS idx_api_status ON raw.api_matches (status);