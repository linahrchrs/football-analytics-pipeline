-- Current-season matches from football-data.org, with team names translated to
-- the canonical (football-data.co.uk) names through the team_name_map seed.
with api as (
    select * from {{ source('raw', 'api_matches') }}
),

team_map as (
    select league_code, api_team_id, csv_team_name from {{ ref('team_name_map') }}
)

select
    md5(api.league_code || '|' || api.season || '|'
        || coalesce(home_map.csv_team_name, api.home_team_name) || '|'
        || coalesce(away_map.csv_team_name, api.away_team_name))      as match_key,
    api.match_id                                                       as api_match_id,
    api.league_code,
    api.season,
    api.matchday,
    api.match_date,
    api.utc_kickoff,
    api.status,
    api.status = 'FINISHED'                                            as is_played,
    coalesce(home_map.csv_team_name, api.home_team_name)               as home_team,
    coalesce(away_map.csv_team_name, api.away_team_name)               as away_team,
    home_map.csv_team_name is not null and away_map.csv_team_name is not null as teams_mapped,
    api.home_goals,
    api.away_goals,
    case api.winner when 'HOME_TEAM' then 'H' when 'AWAY_TEAM' then 'A' when 'DRAW' then 'D' end as result,
    api.home_goals_ht,
    api.away_goals_ht,
    'football-data.org' as source
from api
left join team_map as home_map
    on home_map.league_code = api.league_code and home_map.api_team_id = api.home_team_id
left join team_map as away_map
    on away_map.league_code = api.league_code and away_map.api_team_id = api.away_team_id
where api.status <> 'CANCELLED'
