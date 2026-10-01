"""Small HTML building blocks and shared styling for the dashboard."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

HOME, DRAW, AWAY = "#0F5A57", "#C9D3D1", "#3CC2B6"
INK, MUTED, LINE = "#131719", "#56616A", "#D5DDDB"
OUTCOME_COLORS = {"W": "#0F5A57", "D": "#9AA6A4", "L": "#C2564B"}

CSS = f"""
<style>
[data-testid="stMainBlockContainer"], .block-container {{ padding-top: 4rem; max-width: 1180px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}
.hero-title {{ font-family: 'Archivo', sans-serif; font-weight: 900; font-stretch: 75%; font-size: clamp(2.4rem, 5vw, 3.6rem);
              line-height: .95; margin: 0 0 .6rem; color: {INK}; }}
.hero-sub {{ color: {MUTED}; font-size: 1.05rem; max-width: 62ch; margin: 0 0 1.4rem; }}
.day {{ font-family: 'Archivo', sans-serif; font-weight: 700; font-size: 1.05rem; margin: 1.6rem 0 .4rem; color: {INK};
        border-bottom: 2px solid {INK}; padding-bottom: .3rem; }}
.fixture {{ display: grid; grid-template-columns: 1fr 120px 1fr; align-items: center; gap: 12px;
            padding: 16px 4px 6px; }}
.fixture .team {{ font-weight: 600; font-size: 1.02rem; color: {INK}; }}
.fixture .team small {{ display: block; font-weight: 400; color: {MUTED}; font-size: .8rem; }}
.fixture .away {{ text-align: right; }}
.fixture .score {{ text-align: center; font-family: 'Archivo', sans-serif; font-weight: 800; font-size: 1.6rem; color: {INK}; line-height: 1; }}
.fixture .score small {{ display: block; font-family: 'IBM Plex Sans', sans-serif; font-weight: 400; font-size: .72rem; color: {MUTED}; margin-top: 4px; }}
.probbar {{ display: flex; height: 26px; border-radius: 6px; overflow: hidden; margin: 6px 4px 4px; font-size: .78rem; font-weight: 600; }}
.probbar div {{ display: flex; align-items: center; justify-content: center; white-space: nowrap; overflow: hidden; }}
.probmeta {{ display: flex; justify-content: space-between; color: {MUTED}; font-size: .78rem; margin: 0 4px 10px;
             padding-bottom: 12px; border-bottom: 1px solid {LINE}; }}
.legend {{ display: flex; gap: 18px; font-size: .85rem; color: {MUTED}; margin-bottom: .4rem; }}
.legend span::before {{ content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px;
                        background: var(--c); vertical-align: -1px; }}
.form {{ display: inline-flex; gap: 3px; }}
.form b {{ display: inline-grid; place-items: center; width: 20px; height: 20px; border-radius: 4px; color: #fff;
           font-size: .7rem; font-weight: 700; }}
.note {{ background: #EDF2F1; border-left: 4px solid {HOME}; padding: 12px 16px; border-radius: 6px; color: {INK}; margin: .5rem 0 1rem; }}
@media (max-width: 640px) {{
  .fixture {{ grid-template-columns: 1fr 70px 1fr; }}
  .fixture .score {{ font-size: 1.25rem; }}
}}
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def hero(title: str, subtitle: str) -> None:
    st.html(f'<div class="hero-title">{html.escape(title)}</div><p class="hero-sub">{subtitle}</p>')


def note(text: str) -> None:
    st.html(f'<div class="note">{text}</div>')


def legend() -> None:
    st.html(f'<div class="legend"><span style="--c:{HOME}">Home win</span>'
            f'<span style="--c:{DRAW}">Draw</span><span style="--c:{AWAY}">Away win</span></div>')


def _segment(prob: float, color: str, text_color: str) -> str:
    pct = 100 * float(prob)
    label = f"{pct:.0f}%" if pct >= 9 else ""
    return f'<div style="width:{pct:.1f}%;background:{color};color:{text_color}">{label}</div>'


def fixture_card(row: pd.Series) -> str:
    """One predicted match: teams, most likely score, probability bar."""
    home, away = html.escape(row["home_team"]), html.escape(row["away_team"])
    return (
        '<div class="fixture">'
        f'<div class="team">{home}<small>Elo {row["home_elo"]:.0f}</small></div>'
        f'<div class="score">{html.escape(row["most_likely_score"])}<small>most likely</small></div>'
        f'<div class="team away">{away}<small>Elo {row["away_elo"]:.0f}</small></div>'
        '</div>'
        '<div class="probbar">'
        f'{_segment(row["prob_home"], HOME, "#fff")}{_segment(row["prob_draw"], DRAW, INK)}{_segment(row["prob_away"], AWAY, INK)}'
        '</div>'
        f'<div class="probmeta"><span>Expected goals {row["expected_home_goals"]:.1f}</span>'
        f'<span>{html.escape(str(row["league_name"] or row["league_code"]))}</span>'
        f'<span>Expected goals {row["expected_away_goals"]:.1f}</span></div>'
    )


def form_badges(sequence: str | None) -> str:
    if not sequence:
        return ""
    return '<span class="form">' + "".join(
        f'<b style="background:{OUTCOME_COLORS.get(c, MUTED)}">{c}</b>' for c in sequence) + "</span>"


def plotly_layout(fig, height: int = 380):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10),
        font=dict(family="IBM Plex Sans, sans-serif", color=INK, size=13),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        hoverlabel=dict(font_family="IBM Plex Sans, sans-serif"),
    )
    fig.update_xaxes(showgrid=False, linecolor=LINE)
    fig.update_yaxes(gridcolor="#EEF2F1", zeroline=False)
    return fig
