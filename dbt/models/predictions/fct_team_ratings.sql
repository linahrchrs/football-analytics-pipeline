-- Current Elo rating of every team, its rank within its current league,
-- and how much it moved over its last 5 matches.
with history as (
    select
        *,
        row_number() over (partition by team order by match_date desc, match_key desc) as recency
    from {{ source('model', 'elo_ratings') }}
),

latest as (
    select team, league_code, season, match_date as last_match_date, rating_after as rating
    from history
    where recency = 1
),

five_ago as (
    select team, rating_before as rating_5_matches_ago
    from history
    where recency = 5
)

select
    l.team,
    l.league_code,
    lg.league_name,
    l.season as last_season,
    l.last_match_date,
    l.rating,
    rank() over (partition by l.league_code order by l.rating desc) as league_rank,
    round(l.rating - f.rating_5_matches_ago, 1)                      as change_last_5
from latest l
left join five_ago f using (team)
left join {{ ref('leagues') }} lg using (league_code)
