-- One row per team per played match (each match appears twice: home and away view).
-- This "long" format makes standings, form and team stats simple aggregations.
with matches as (
    select * from {{ ref('int_matches_unified') }} where is_played
),

team_rows as (
    select
        match_key, league_code, season, match_date,
        home_team as team, away_team as opponent, true as is_home,
        home_goals as goals_for, away_goals as goals_against,
        home_shots as shots_for, away_shots as shots_against,
        home_shots_on_target as shots_on_target_for, away_shots_on_target as shots_on_target_against
    from matches
    union all
    select
        match_key, league_code, season, match_date,
        away_team, home_team, false,
        away_goals, home_goals,
        away_shots, home_shots,
        away_shots_on_target, home_shots_on_target
    from matches
)

select
    *,
    case when goals_for > goals_against then 'W' when goals_for = goals_against then 'D' else 'L' end as outcome,
    case when goals_for > goals_against then 3 when goals_for = goals_against then 1 else 0 end as points,
    row_number() over (partition by league_code, season, team order by match_date, match_key) as match_number
from team_rows
