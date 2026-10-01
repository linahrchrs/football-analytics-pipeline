import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data
from components import AWAY, HOME, MUTED, hero, note, plotly_layout

PREDICTOR_LABELS = {"model": "This model", "bookmaker": "Bookmakers", "baseline": "Naive baseline"}
PREDICTOR_COLORS = {"This model": HOME, "Bookmakers": "#9AA6A4", "Naive baseline": "#E3E8E7"}


def render():
    hero("How good is the model?",
         "Every prediction is saved before kickoff and never changed, then compared with the real result. "
         "The benchmark is the bookmakers, whose odds carry far more information than results alone.")

    live, backtest_tab = st.tabs(["Live predictions", "Backtest on past seasons"])
    with live:
        render_live()
    with backtest_tab:
        render_backtest()


def render_live():
    df = data.finished_predictions()
    if df.empty:
        note("The live record starts with the first predicted matches. Results appear here the morning "
             "after each game; meanwhile, the backtest tab shows how the model did on past seasons.")
        return

    with_odds = df[df["bookmaker_rps"].notna()]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matches predicted", len(df))
    c2.metric("Correct outcome", f"{100 * df['is_correct'].mean():.1f}%")
    c3.metric("Exact score", f"{100 * df['is_exact_score'].mean():.1f}%")
    if not with_odds.empty:
        diff = with_odds["rps"].mean() - with_odds["bookmaker_rps"].mean()
        c4.metric("RPS vs bookmakers", f"{with_odds['rps'].mean():.3f}", f"{diff:+.3f}", delta_color="inverse",
                  help="Ranked probability score: 0 is perfect, lower is better. The delta compares with bookmakers.")
    else:
        c4.metric("Average RPS", f"{df['rps'].mean():.3f}", help="Ranked probability score: 0 is perfect, lower is better.")

    # Running average after each matchday (one point per date, not per match)
    by_day = df.groupby("match_date").agg(rps_sum=("rps", "sum"), n=("rps", "size"),
                                          bk_sum=("bookmaker_rps", "sum"), bk_n=("bookmaker_rps", "count")).sort_index()
    by_day["Model"] = by_day["rps_sum"].cumsum() / by_day["n"].cumsum()
    by_day["Bookmakers"] = by_day["bk_sum"].cumsum() / by_day["bk_n"].cumsum().replace(0, float("nan"))
    st.markdown("#### Average score so far (RPS, lower is better)")
    fig = go.Figure()
    fig.add_scatter(x=by_day.index, y=by_day["Model"], name="This model", mode="lines+markers",
                    line=dict(color=HOME, width=3))
    if by_day["bk_n"].sum() > 0:
        fig.add_scatter(x=by_day.index, y=by_day["Bookmakers"], name="Bookmakers", mode="lines+markers",
                        line=dict(color=MUTED, width=2, dash="dash"))
    st.plotly_chart(plotly_layout(fig, 320), width="stretch")

    st.markdown("#### Latest results")
    recent = df.head(30).copy()
    recent["Match"] = recent["home_team"] + " – " + recent["away_team"]
    recent["Score"] = recent["home_goals"].astype("Int64").astype(str) + "-" + recent["away_goals"].astype("Int64").astype(str)
    recent["Predicted"] = recent["predicted_result"].map({"H": "Home win", "D": "Draw", "A": "Away win"})
    recent["Probabilities"] = recent.apply(
        lambda r: f"{100 * r.prob_home:.0f} / {100 * r.prob_draw:.0f} / {100 * r.prob_away:.0f}", axis=1)
    recent["Correct"] = recent["is_correct"].map({True: "✓", False: "✗"})
    st.dataframe(recent[["match_date", "league_name", "Match", "Score", "Predicted", "Probabilities", "most_likely_score", "Correct"]],
                 hide_index=True, width="stretch",
                 column_config={"match_date": st.column_config.DateColumn("Date", format="D MMM"),
                                "league_name": "League", "most_likely_score": "Predicted score",
                                "Probabilities": st.column_config.TextColumn("H / D / A %")})


def render_backtest():
    bt = data.backtest()
    if bt.empty:
        note("No backtest yet: run `python -m src.model.run backtest`.")
        return
    bt["Predictor"] = bt["predictor"].map(PREDICTOR_LABELS)

    st.markdown("The model is trained on earlier seasons only, then scored on the next one, "
                "exactly as if it had been predicting live.")
    avg = bt.groupby("Predictor")[["accuracy", "rps", "log_loss"]].mean()
    cols = st.columns(len(avg))
    for col, name in zip(cols, ["This model", "Bookmakers", "Naive baseline"]):
        if name in avg.index:
            col.metric(name, f"RPS {avg.loc[name, 'rps']:.3f}", f"{100 * avg.loc[name, 'accuracy']:.1f}% correct",
                       delta_color="off", delta_arrow="off")

    fig = px.bar(bt, x="test_season", y="rps", color="Predictor", barmode="group",
                 color_discrete_map=PREDICTOR_COLORS, category_orders={"Predictor": list(PREDICTOR_COLORS)},
                 labels={"test_season": "Season", "rps": "RPS (lower is better)"})
    fig.update_yaxes(range=[max(0, bt["rps"].min() - 0.03), bt["rps"].max() + 0.01])
    st.plotly_chart(plotly_layout(fig, 360), width="stretch")

    with st.expander("What do these scores mean?"):
        st.markdown(
            "- **Correct outcome**: how often the most likely result (home win, draw, away win) happened.\n"
            "- **RPS (ranked probability score)**: the standard score for football forecasts. It rewards "
            "confident correct probabilities and treats a draw as closer to a win than a loss is. 0 is perfect.\n"
            "- **Naive baseline**: always predicts the historical frequencies of home wins, draws and away wins.\n"
            "- **Bookmakers**: odds converted to probabilities, with the bookmaker's margin removed.")
    st.dataframe(bt[["test_season", "Predictor", "matches", "accuracy", "rps", "log_loss", "brier_score"]],
                 hide_index=True, width="stretch",
                 column_config={"test_season": "Season", "matches": "Matches",
                                "accuracy": st.column_config.NumberColumn("Accuracy", format="percent"),
                                "rps": st.column_config.NumberColumn("RPS", format="%.4f"),
                                "log_loss": st.column_config.NumberColumn("Log loss", format="%.4f"),
                                "brier_score": st.column_config.NumberColumn("Brier", format="%.4f")})
