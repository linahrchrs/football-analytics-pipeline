"""Step 2b: map football-data.org team names to football-data.co.uk team names.

The two sources name teams differently ("Manchester United FC" vs "Man United",
"Club Atlético de Madrid" vs "Ath Madrid"). Instead of typing a mapping by hand,
we learn it from the data: the same match appears in both sources with the same
league, date and score, so each finished match is a "vote" that API team X is
CSV team Y. Teams without enough votes fall back to fuzzy name matching.

The result is written to dbt/seeds/team_name_map.csv, to review once and commit.
dbt uses it in step 3 to give every team a single name.

Usage:
    python -m src.ingestion.build_team_map
"""
from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd
from sqlalchemy import text

from src.db import ROOT, get_engine

log = logging.getLogger("team_map")

OUTPUT = ROOT / "dbt" / "seeds" / "team_name_map.csv"
MIN_VOTES = 2          # matches that must agree before we trust a results-based mapping
MIN_SHARE = 0.6        # share of a team's votes the winning name must have

VOTES_SQL = """
WITH pairs AS (
    SELECT a.league_code, a.home_team_id AS api_team_id, a.home_team_name AS api_team_name,
           a.home_team_short AS api_team_short, h.home_team AS csv_team_name
    FROM raw.api_matches a
    JOIN raw.historical_matches h
      ON h.league_code = a.league_code
     AND h.match_date BETWEEN a.match_date - 1 AND a.match_date + 1
     AND h.home_goals = a.home_goals
     AND h.away_goals = a.away_goals
    WHERE a.status = 'FINISHED'
    UNION ALL
    SELECT a.league_code, a.away_team_id, a.away_team_name, a.away_team_short, h.away_team
    FROM raw.api_matches a
    JOIN raw.historical_matches h
      ON h.league_code = a.league_code
     AND h.match_date BETWEEN a.match_date - 1 AND a.match_date + 1
     AND h.home_goals = a.home_goals
     AND h.away_goals = a.away_goals
    WHERE a.status = 'FINISHED'
)
SELECT league_code, api_team_id, api_team_name, api_team_short, csv_team_name, COUNT(*) AS votes
FROM pairs
GROUP BY 1, 2, 3, 4, 5
"""

API_TEAMS_SQL = """
SELECT DISTINCT league_code, home_team_id AS api_team_id, home_team_name AS api_team_name, home_team_short AS api_team_short
FROM raw.api_matches
UNION
SELECT DISTINCT league_code, away_team_id, away_team_name, away_team_short FROM raw.api_matches
"""

# Teams from each league's two most recent seasons in the CSV data
CSV_TEAMS_SQL = """
WITH recent AS (
    SELECT league_code, season,
           DENSE_RANK() OVER (PARTITION BY league_code ORDER BY season DESC) AS season_rank
    FROM (SELECT DISTINCT league_code, season FROM raw.historical_matches) s
)
SELECT DISTINCT h.league_code, h.home_team AS csv_team_name
FROM raw.historical_matches h
JOIN recent r ON r.league_code = h.league_code AND r.season = h.season AND r.season_rank <= 2
"""


def normalize(name: str) -> str:
    """'Club Atlético de Madrid' -> 'atletico madrid' (for fuzzy matching only)."""
    name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"\b(fc|cf|afc|sc|ac|as|ss|ssc|us|rc|rcd|cd|ud|sd|club|de|del|la|vfb|vfl|tsg|sv|bv|1)\b", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def similarity(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def pick_from_votes(votes: pd.DataFrame) -> pd.DataFrame:
    """For each API team, keep the CSV name with a clear majority of votes."""
    if votes.empty:
        return votes.assign(share=pd.Series(dtype=float))
    votes = votes.copy()
    votes["share"] = votes["votes"] / votes.groupby(["league_code", "api_team_id"])["votes"].transform("sum")
    best = votes.sort_values("votes", ascending=False).drop_duplicates(["league_code", "api_team_id"])
    return best[(best["votes"] >= MIN_VOTES) & (best["share"] >= MIN_SHARE)]


MIN_FUZZY = 0.5       # below this similarity we leave the team unmapped rather than guess


def fuzzy_match(api_teams: pd.DataFrame, csv_teams: pd.DataFrame, taken: set[tuple[str, str]]) -> pd.DataFrame:
    """Fallback: pair remaining teams by name similarity, best pairs first, one CSV name per API team."""
    pairs = []
    for t in api_teams.itertuples():
        for name in csv_teams.loc[csv_teams["league_code"] == t.league_code, "csv_team_name"]:
            if (t.league_code, name) in taken:
                continue
            score = max(similarity(name, t.api_team_name), similarity(name, t.api_team_short or ""))
            pairs.append((score, t, name))

    rows, used_api = [], set()
    for score, t, name in sorted(pairs, key=lambda p: p[0], reverse=True):
        if score < MIN_FUZZY or (t.league_code, t.api_team_id) in used_api or (t.league_code, name) in taken:
            continue
        used_api.add((t.league_code, t.api_team_id))
        taken.add((t.league_code, name))
        rows.append({"league_code": t.league_code, "api_team_id": t.api_team_id, "api_team_name": t.api_team_name,
                     "api_team_short": t.api_team_short, "csv_team_name": name,
                     "method": "fuzzy", "confidence": round(float(score), 2)})
    return pd.DataFrame(rows)


def build_mapping(votes: pd.DataFrame, api_teams: pd.DataFrame, csv_teams: pd.DataFrame) -> pd.DataFrame:
    by_results = pick_from_votes(votes)
    mapped = by_results.assign(method="results", confidence=by_results["share"].round(2))[
        ["league_code", "api_team_id", "api_team_name", "api_team_short", "csv_team_name", "method", "confidence"]]

    done_ids = set(zip(mapped["league_code"], mapped["api_team_id"]))
    remaining = api_teams[[(l, i) not in done_ids for l, i in zip(api_teams["league_code"], api_teams["api_team_id"])]]
    taken = set(zip(mapped["league_code"], mapped["csv_team_name"]))
    fuzzy = fuzzy_match(remaining, csv_teams, taken)

    result = pd.concat([mapped, fuzzy], ignore_index=True) if not fuzzy.empty else mapped
    return result.sort_values(["league_code", "csv_team_name"]).reset_index(drop=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    engine = get_engine()
    with engine.connect() as conn:
        votes = pd.read_sql(text(VOTES_SQL), conn)
        api_teams = pd.read_sql(text(API_TEAMS_SQL), conn)
        csv_teams = pd.read_sql(text(CSV_TEAMS_SQL), conn)

    mapping = build_mapping(votes, api_teams, csv_teams)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(OUTPUT, index=False)

    n_results = int((mapping["method"] == "results").sum())
    log.info("Mapped %d of %d API teams (%d from match results, %d fuzzy) -> %s",
             len(mapping), len(api_teams), n_results, len(mapping) - n_results, OUTPUT.relative_to(ROOT))
    to_check = mapping[(mapping["method"] == "fuzzy") & (mapping["confidence"] < 0.8)]
    for r in to_check.itertuples():
        log.warning("Check by hand: %s  '%s' -> '%s' (confidence %.2f)", r.league_code, r.api_team_name, r.csv_team_name, r.confidence)
    mapped_ids = set(zip(mapping["league_code"], mapping["api_team_id"]))
    for t in api_teams.itertuples():
        if (t.league_code, t.api_team_id) not in mapped_ids:
            log.warning("Not mapped: %s  '%s' (id %s): add it to the CSV by hand", t.league_code, t.api_team_name, t.api_team_id)


if __name__ == "__main__":
    main()