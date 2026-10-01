-- Each team's form going INTO every match: computed only from earlier matches,
-- so it can be used as a model feature without leaking the result.
select
    match_key,
    league_code,
    season,
    match_date,
    team,
    opponent,
    is_home,
    match_number,
    outcome,
    points,
    goals_for,
    goals_against,
    sum(points)        over w_last5 as form_points_last5,
    sum(goals_for)     over w_last5 as form_goals_for_last5,
    sum(goals_against) over w_last5 as form_goals_against_last5,
    count(*)           over w_last5 as form_matches_counted,
    string_agg(outcome, '') over w_last5 as form_sequence_last5,   -- oldest to newest, e.g. 'WWDLW'
    coalesce(sum(points) over w_season, 0) as season_points_before,
    count(*)           over w_season as season_matches_before
from {{ ref('int_team_matches') }}
window
    w_last5  as (partition by league_code, team order by match_date, match_key rows between 5 preceding and 1 preceding),
    w_season as (partition by league_code, season, team order by match_date, match_key rows between unbounded preceding and 1 preceding)
