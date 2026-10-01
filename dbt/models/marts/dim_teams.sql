-- Every team seen in the data, with the leagues and seasons it played in.
select
    team,
    league_code,
    min(season)              as first_season,
    max(season)              as last_season,
    count(distinct season)   as seasons_played,
    count(*)                 as matches_played
from {{ ref('int_team_matches') }}
group by 1, 2
