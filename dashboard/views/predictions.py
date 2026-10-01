import streamlit as st

import data
from components import fixture_card, hero, legend, note


def render():
    hero("Upcoming matches, predicted",
         "Win, draw and loss probabilities from an Elo + Poisson model, refreshed every morning "
         "before the day's games. The score in the middle is the single most likely result.")

    lg = data.leagues()
    names = {"All leagues": None, **dict(zip(lg["league_name"], lg["league_code"]))}
    choice = st.pills("League", list(names), default="All leagues", label_visibility="collapsed")
    df = data.upcoming_predictions(names.get(choice or "All leagues"))

    if df.empty:
        note("No predicted matches in the next few days for this selection. Predictions cover the "
             "next 10 days and appear once fixtures are published.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Matches predicted", len(df))
    fav = df.assign(top=df[["prob_home", "prob_away"]].max(axis=1)).sort_values("top", ascending=False).iloc[0]
    winner = fav["home_team"] if fav["prob_home"] >= fav["prob_away"] else fav["away_team"]
    c2.metric("Strongest favourite", winner, f"{100 * fav['top']:.0f}% to win", delta_color="off", delta_arrow="off")
    goals = (df["expected_home_goals"] + df["expected_away_goals"]).mean()
    c3.metric("Goals expected per match", f"{goals:.1f}")

    legend()
    for match_date, day in df.groupby("match_date", sort=True):
        st.html(f'<div class="day">{match_date:%A} {match_date.day} {match_date:%B}</div>' + "".join(fixture_card(r) for _, r in day.iterrows()))
