-- One row per match across both sources, played or upcoming.
--   * football-data.co.uk is the reference for played matches (it has shots, cards and odds).
--   * football-data.org fills the gap: results from the last few days, before the CSV
--     files are updated, and every upcoming fixture.
with csv as (
    select * from {{ ref('stg_historical_matches') }}
),

api as (
    select * from {{ ref('stg_api_matches') }}
)

select
    csv.match_key,
    csv.league_code,
    csv.season,
    csv.match_date,
    true as is_played,
    'FINISHED' as status,
    api.matchday,
    csv.home_team,
    csv.away_team,
    csv.home_goals,
    csv.away_goals,
    csv.result,
    csv.home_shots,
    csv.away_shots,
    csv.home_shots_on_target,
    csv.away_shots_on_target,
    csv.home_corners,
    csv.away_corners,
    csv.home_yellow_cards,
    csv.away_yellow_cards,
    csv.home_red_cards,
    csv.away_red_cards,
    csv.odds_home,
    csv.odds_draw,
    csv.odds_away,
    csv.source
from csv
left join api on api.match_key = csv.match_key

union all

select
    api.match_key,
    api.league_code,
    api.season,
    api.match_date,
    api.is_played,
    api.status,
    api.matchday,
    api.home_team,
    api.away_team,
    api.home_goals,
    api.away_goals,
    api.result,
    null, null, null, null, null, null, null, null, null, null,
    null, null, null,
    api.source
from api
where not exists (select 1 from csv where csv.match_key = api.match_key)
