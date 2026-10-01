import plotly.graph_objects as go
import streamlit as st

import data
from components import HOME, form_badges, hero, plotly_layout


def render():
    hero("Teams and Elo ratings",
         "Elo measures strength from results: beating a strong team earns more points than beating a weak one. "
         "Every team started at 1500 in 2015.")

    lg = data.leagues()
    c1, c2 = st.columns([1, 2])
    league_name = c1.selectbox("League", lg["league_name"])
    code = lg.loc[lg["league_name"] == league_name, "league_code"].iloc[0]
    ratings = data.team_ratings(code)
    if ratings.empty:
        st.info("No ratings for this league yet.")
        return
    team = c2.selectbox("Team", ratings["team"])

    row = ratings.set_index("team").loc[team]
    seasons = data.team_seasons(team)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Elo rating", f"{row['rating']:.0f}",
              f"{row['change_last_5']:+.0f} over 5 matches" if row["change_last_5"] == row["change_last_5"] else None)
    m2.metric("Rank in league (Elo)", f"#{int(row['league_rank'])}")
    if not seasons.empty:
        cur = seasons.iloc[0]
        m3.metric(f"Position {cur['season']}", f"#{int(cur['position'])}", f"{int(cur['points'])} pts", delta_color="off", delta_arrow="off")
        m4.metric("Seasons in the data", len(seasons))

    hist = data.elo_history(team)
    fig = go.Figure()
    fig.add_scatter(x=hist["match_date"], y=hist["rating_after"], mode="lines", line=dict(color=HOME, width=2),
                    customdata=hist[["opponent", "season"]],
                    hovertemplate="%{x|%d %b %Y}<br>after vs %{customdata[0]}: %{y:.0f}<extra></extra>")
    fig.add_hline(y=1500, line_dash="dot", line_color="#9AA6A4", annotation_text="starting rating",
                  annotation_position="bottom right")
    fig.update_layout(title=f"{team}: Elo rating after every match")
    st.plotly_chart(plotly_layout(fig, 380), width="stretch")

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("#### Last 10 matches")
        matches = data.team_matches(team)
        lines = []
        for m in matches.itertuples():
            home = m.home_team == team
            gf, ga = (m.home_goals, m.away_goals) if home else (m.away_goals, m.home_goals)
            outcome = "W" if gf > ga else "D" if gf == ga else "L"
            opponent = m.away_team if home else m.home_team
            lines.append(f"{form_badges(outcome)} &nbsp; {m.match_date:%d %b} &nbsp; "
                         f"{'vs' if home else 'at'} <b>{opponent}</b> &nbsp; {int(gf)}-{int(ga)}")
        st.html("<div style='line-height:2.1'>" + "<br>".join(lines) + "</div>")
    with c2:
        st.markdown("#### Season by season")
        st.dataframe(seasons[["season", "league_code", "position", "points", "goals_for", "goals_against"]],
                     hide_index=True, width="stretch",
                     column_config={"season": "Season", "league_code": "League", "position": "#",
                                    "points": "Pts", "goals_for": "GF", "goals_against": "GA"})
