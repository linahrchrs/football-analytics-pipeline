-- The model's track record. For each match, take the LAST prediction made on or before
-- match day (the pipeline runs early in the morning, before kickoffs), then compare it
-- with the result once the match has been played.
with last_prediction as (
    select distinct on (match_key) *
    from {{ source('model', 'match_predictions') }}
    where predicted_at::date <= match_date
    order by match_key, predicted_at desc
),

scored as (
    select
        p.match_key,
        p.league_code,
        m.league_name,
        p.season,
        p.match_date,
        p.home_team,
        p.away_team,
        p.predicted_at,
        p.model_version,
        p.home_elo,
        p.away_elo,
        p.expected_home_goals,
        p.expected_away_goals,
        p.prob_home,
        p.prob_draw,
        p.prob_away,
        p.most_likely_score,
        case
            when p.prob_home >= greatest(p.prob_draw, p.prob_away) then 'H'
            when p.prob_draw >= p.prob_away then 'D'
            else 'A'
        end as predicted_result,
        m.is_played,
        m.home_goals,
        m.away_goals,
        m.result as actual_result,
        m.implied_prob_home,
        m.implied_prob_draw,
        m.implied_prob_away
    from last_prediction p
    left join {{ ref('fct_matches') }} m using (match_key)
)

select
    *,
    case when is_played then predicted_result = actual_result end                       as is_correct,
    case when is_played then most_likely_score = home_goals || '-' || away_goals end    as is_exact_score,
    -- Ranked probability score for this match (0 = perfect, lower is better)
    case when is_played then round((
        power(prob_home - case when actual_result = 'H' then 1 else 0 end, 2)
        + power(prob_home + prob_draw - case when actual_result in ('H', 'D') then 1 else 0 end, 2)
    ) / 2, 4) end                                                                        as rps,
    case when is_played and implied_prob_home is not null then round((
        power(implied_prob_home - case when actual_result = 'H' then 1 else 0 end, 2)
        + power(implied_prob_home + implied_prob_draw - case when actual_result in ('H', 'D') then 1 else 0 end, 2)
    ) / 2, 4) end                                                                        as bookmaker_rps
from scored
