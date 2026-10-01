import plotly.graph_objects as go
import streamlit as st

import data
from components import AWAY, DRAW, HOME, hero, plotly_layout


def render():
    hero("League tables", "Standings, form and scoring trends for every league since 2015-16.")

    lg = data.leagues()
    c1, c2 = st.columns([2, 1])
    league_name = c1.selectbox("League", lg["league_name"])
    code = lg.loc[lg["league_name"] == league_name, "league_code"].iloc[0]
    seasons = data.seasons(code)
    if not seasons:
        st.info("No matches for this league yet.")
        return
    season = c2.selectbox("Season", seasons)

    table = data.standings(code, season)
    form = data.recent_form(code, season).set_index("team")["form"]
    table["form"] = table["team"].map(form)
    st.dataframe(
        table[["position", "team", "played", "won", "drawn", "lost", "goals_for", "goals_against",
               "goal_difference", "points", "form", "elo"]],
        hide_index=True, width="stretch", height=min(38 * (len(table) + 1), 820),
        column_config={
            "position": st.column_config.NumberColumn("#", width="small"),
            "team": "Team", "played": "P", "won": "W", "drawn": "D", "lost": "L",
            "goals_for": "GF", "goals_against": "GA", "goal_difference": "GD",
            "points": st.column_config.ProgressColumn("Pts", format="%d", min_value=0,
                                                      max_value=int(table["points"].max() or 1)),
            "form": st.column_config.TextColumn("Last 5", help="Oldest to most recent: W win, D draw, L loss"),
            "elo": st.column_config.NumberColumn("Elo now", format="%.0f"),
        })
    st.caption("Ranked by points, goal difference, then goals scored. Official tie-breakers and point deductions may differ.")

    st.markdown("#### How results are shared out, season by season")
    ls = data.league_seasons(code)
    fig = go.Figure()
    for col, name, color in [("home_win_rate", "Home wins", HOME), ("draw_rate", "Draws", DRAW), ("away_win_rate", "Away wins", AWAY)]:
        fig.add_bar(x=ls["season"], y=ls[col], name=name, marker_color=color,
                    hovertemplate="%{x}: %{y:.0%}<extra>" + name + "</extra>")
    fig.update_layout(barmode="stack", yaxis_tickformat=".0%")
    st.plotly_chart(plotly_layout(fig, 340), width="stretch")
    st.caption("Home advantage is one of the effects the model has to learn. Seasons played without fans "
               "(2020-21) are a natural experiment worth a look.")
