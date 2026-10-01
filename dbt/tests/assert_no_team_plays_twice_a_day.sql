-- A team cannot play two matches on the same day: catches duplicates between the two sources.
select league_code, team, match_date, count(*) as matches
from {{ ref('int_team_matches') }}
group by 1, 2, 3
having count(*) > 1
