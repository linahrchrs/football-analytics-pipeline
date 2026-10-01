-- Every match, played or upcoming, with its league name. The main table for analysis
-- and the source of the fixtures the model will predict.
select
    m.match_key,
    m.league_code,
    l.league_name,
    l.country,
    m.season,
    m.matchday,
    m.match_date,
    m.status,
    m.is_played,
    m.home_team,
    m.away_team,
    m.home_goals,
    m.away_goals,
    m.home_goals + m.away_goals as total_goals,
    m.result,
    m.home_shots,
    m.away_shots,
    m.home_shots_on_target,
    m.away_shots_on_target,
    m.home_corners,
    m.away_corners,
    m.home_yellow_cards,
    m.away_yellow_cards,
    m.home_red_cards,
    m.away_red_cards,
    m.odds_home,
    m.odds_draw,
    m.odds_away,
    -- Bookmaker probabilities with their margin removed: the benchmark our model has to beat
    case when m.odds_home > 0 and m.odds_draw > 0 and m.odds_away > 0 then
        round((1 / m.odds_home) / (1 / m.odds_home + 1 / m.odds_draw + 1 / m.odds_away), 4) end as implied_prob_home,
    case when m.odds_home > 0 and m.odds_draw > 0 and m.odds_away > 0 then
        round((1 / m.odds_draw) / (1 / m.odds_home + 1 / m.odds_draw + 1 / m.odds_away), 4) end as implied_prob_draw,
    case when m.odds_home > 0 and m.odds_draw > 0 and m.odds_away > 0 then
        round((1 / m.odds_away) / (1 / m.odds_home + 1 / m.odds_draw + 1 / m.odds_away), 4) end as implied_prob_away,
    m.source
from {{ ref('int_matches_unified') }} m
join {{ ref('leagues') }} l using (league_code)
