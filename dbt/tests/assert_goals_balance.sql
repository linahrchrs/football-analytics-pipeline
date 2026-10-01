-- In every league season, total goals scored must equal total goals conceded.
select league_code, season, sum(goals_for) as scored, sum(goals_against) as conceded
from {{ ref('fct_standings') }}
group by 1, 2
having sum(goals_for) <> sum(goals_against)
