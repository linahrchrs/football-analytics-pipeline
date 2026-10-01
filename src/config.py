"""Project-wide settings: which leagues and seasons to load."""

# football-data.co.uk league codes, restricted to leagues that are also
# available on the football-data.org free tier (used for daily updates later).
LEAGUES = {
    "E0": "Premier League",
    "E1": "Championship",
    "SP1": "La Liga",
    "D1": "Bundesliga",
    "I1": "Serie A",
    "F1": "Ligue 1",
    "N1": "Eredivisie",
    "P1": "Primeira Liga",
}

# First season to load, given by its starting year (2015 -> 2015-16).
FIRST_SEASON = 2015

HISTORY_URL = "https://www.football-data.co.uk/mmz4281/{code}/{league}.csv"


def season_code(start_year: int) -> str:
    """2023 -> '2324' (the format used in football-data.co.uk URLs)."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_label(start_year: int) -> str:
    """2023 -> '2023-24' (the format stored in the database)."""
    return f"{start_year}-{(start_year + 1) % 100:02d}"


# ------------------------------------------------------------------ daily API
API_BASE_URL = "https://api.football-data.org/v4"

# football-data.co.uk league code -> football-data.org competition code
API_COMPETITIONS = {
    "E0": "PL",
    "E1": "ELC",
    "SP1": "PD",
    "D1": "BL1",
    "I1": "SA",
    "F1": "FL1",
    "N1": "DED",
    "P1": "PPL",
}

# Free tier: 10 requests per minute, so we wait between calls.
API_SECONDS_BETWEEN_CALLS = 7