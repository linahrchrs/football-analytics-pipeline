-- League table for every league and season, from played matches.
-- Ranking uses points, then goal difference, then goals scored (official tie-breakers
-- vary by league, and point deductions are not included).
with team_season as (
    select
        league_code,
        season,
        team,
        count(*)                                  as played,
        count(*) filter (where outcome = 'W')     as won,
        count(*) filter (where outcome = 'D')     as drawn,
        count(*) filter (where outcome = 'L')     as lost,
        sum(goals_for)                            as goals_for,
        sum(goals_against)                        as goals_against,
        sum(goals_for) - sum(goals_against)       as goal_difference,
        sum(points)                               as points,
        sum(points) filter (where is_home)        as home_points,
        sum(points) filter (where not is_home)    as away_points
    from {{ ref('int_team_matches') }}
    group by 1, 2, 3
)

select
    league_code,
    season,
    rank() over (
        partition by league_code, season
        order by points desc, goal_difference desc, goals_for desc
    ) as position,
    team,
    played,
    won,
    drawn,
    lost,
    goals_for,
    goals_against,
    goal_difference,
    points,
    home_points,
    away_points,
    round(points::numeric / nullif(played, 0), 2) as points_per_game
from team_season
