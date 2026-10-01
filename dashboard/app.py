"""Football Analytics: live dashboard.

Run locally from the project root:  streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

import data  # noqa: E402
from components import inject_css  # noqa: E402
from views import about, leagues, predictions, teams, track_record  # noqa: E402

st.set_page_config(page_title="Football Analytics · Match Predictor", page_icon="⚽", layout="wide")
inject_css()

pages = [
    st.Page(predictions.render, title="Predictions", icon=":material/sports_soccer:", url_path="predictions", default=True),
    st.Page(track_record.render, title="Track record", icon=":material/insights:", url_path="track-record"),
    st.Page(leagues.render, title="Leagues", icon=":material/table_rows:", url_path="leagues"),
    st.Page(teams.render, title="Teams", icon=":material/shield:", url_path="teams"),
    st.Page(about.render, title="How it works", icon=":material/account_tree:", url_path="how-it-works"),
]

with st.sidebar:
    st.markdown("### Football Analytics")
    st.caption("Match predictions for 8 European leagues, updated every morning.")

nav = st.navigation(pages)

with st.sidebar:
    st.divider()
    try:
        updated = data.last_update()
        if updated is not None:
            st.caption(f"Data updated {updated:%d %b %Y, %H:%M} UTC")
    except Exception:
        st.caption("Database unavailable")
    st.caption("Built by [Lina Harcharras](https://linahrchrs.github.io) · "
               "[Source code](https://github.com/linahrchrs/football-analytics-pipeline)")

try:
    nav.run()
except Exception as exc:  # show a readable message instead of a stack trace to visitors
    st.error("The data could not be loaded right now. Please try again in a moment.")
    st.caption(f"{exc.__class__.__name__}")
