import streamlit as st

from components import hero


def render():
    hero("How it works",
         "An end-to-end data project: from raw match data to a model that publishes its predictions "
         "before kickoff and is judged on what happens next.")

    st.graphviz_chart("""
digraph {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#EDF2F1", color="#D5DDDB", fontname="Helvetica", fontsize=11];
  edge [color="#56616A"];
  csv [label="football-data.co.uk\\nhistory since 2015"];
  api [label="football-data.org API\\ncurrent season"];
  raw [label="PostgreSQL\\nraw tables", fillcolor="#0F5A57", fontcolor="white", color="#0F5A57"];
  dbt [label="dbt\\nstaging → marts\\n+ data tests"];
  model [label="Elo + Poisson model\\nPython"];
  app [label="This dashboard\\nStreamlit", fillcolor="#3CC2B6", color="#3CC2B6"];
  gh [label="GitHub Actions\\nevery day 05:00 UTC", shape=note];
  csv -> raw; api -> raw; raw -> dbt; dbt -> model; model -> dbt [label="predictions", fontsize=9]; dbt -> app;
  gh -> raw [style=dashed]; gh -> dbt [style=dashed]; gh -> model [style=dashed];
}""")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
#### Data
- **32,000+ matches** from 8 leagues (Premier League, Championship, La Liga, Bundesliga, Serie A,
  Ligue 1, Eredivisie, Primeira Liga) since 2015-16, plus the current season from a live API.
- The two sources name teams differently, so the mapping between them is **learned from the data**:
  the same match appears in both with the same date and score.
- **dbt** builds standings, form and league statistics, with tests on the football logic
  (points = 3 × wins + draws, goals scored = goals conceded, no team plays twice a day).
""")
    with c2:
        st.markdown("""
#### Model
- **Elo ratings** track every team's strength across seasons and divisions.
- **Two Poisson regressions** predict each side's goals from the Elo gap, recent form and the league's
  scoring level, which gives the probability of every scoreline.
- Every feature uses only information available **before kickoff**, and the model is scored with a
  walk-forward backtest and, live, on matches it had not seen.
""")

    st.markdown("""
#### Stack
Python · PostgreSQL (Neon) · dbt · scikit-learn · SciPy · GitHub Actions · Streamlit · Plotly

[Source code on GitHub](https://github.com/linahrchrs/football-analytics-pipeline) ·
[Lina Harcharras' portfolio](https://linahrchrs.github.io)
""")
