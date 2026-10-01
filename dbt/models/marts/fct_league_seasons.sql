-- One row per league and season: how often home teams win, how many goals are scored.
-- Home advantage is one of the effects the prediction model has to capture.
select
    m.league_code,
    l.league_name,
    m.season,
    count(*)                                                           as matches,
    round(avg(case when m.result = 'H' then 1.0 else 0 end), 3)        as home_win_rate,
    round(avg(case when m.result = 'D' then 1.0 else 0 end), 3)        as draw_rate,
    round(avg(case when m.result = 'A' then 1.0 else 0 end), 3)        as away_win_rate,
    round(avg(m.home_goals + m.away_goals), 2)                         as avg_goals_per_match,
    round(avg(m.home_goals), 2)                                        as avg_home_goals,
    round(avg(m.away_goals), 2)                                        as avg_away_goals,
    round(avg(case when m.home_goals + m.away_goals > 2 then 1.0 else 0 end), 3) as over_2_5_rate
from {{ ref('int_matches_unified') }} m
join {{ ref('leagues') }} l using (league_code)
where m.is_played
group by 1, 2, 3
