-- A team's points must equal 3 x wins + draws, and played = won + drawn + lost.
select league_code, season, team, points, won, drawn, played
from {{ ref('fct_standings') }}
where points <> 3 * won + drawn
   or played <> won + drawn + lost
