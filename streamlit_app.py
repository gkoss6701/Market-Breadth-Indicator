"""
Streamlit dashboard: composite score/regime over time, component breakdown,
and a recent-alerts panel. Reads from the same SQLite DB the GitHub Action
writes to.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st

from src.db.models import get_connection

st.set_page_config(page_title="Market Breadth Detector", layout="wide")
st.title("Market Breadth Detector")

with get_connection() as conn:
    breadth = pd.read_sql("SELECT * FROM breadth_daily ORDER BY date", conn, parse_dates=["date"])
    alerts = pd.read_sql(
        "SELECT * FROM alerts_sent ORDER BY sent_at DESC LIMIT 20", conn
    )

if breadth.empty:
    st.info("No breadth data yet -- run the ingestion + compute pipeline first.")
    st.stop()

latest = breadth.iloc[-1]
col1, col2, col3, col4 = st.columns(4)
col1.metric("Composite Score", f"{latest['composite_score']:.2f}")
col2.metric("Regime", latest["regime"])
col3.metric("% Above 50MA", f"{latest['pct_above_50ma']:.1f}%")
col4.metric("New Highs / Lows", f"{int(latest['new_highs'])} / {int(latest['new_lows'])}")

st.subheader("Composite Score Over Time")
st.line_chart(breadth.set_index("date")["composite_score"])

st.subheader("Component Metrics")
st.line_chart(breadth.set_index("date")[["pct_above_50ma", "pct_above_200ma"]])
st.line_chart(breadth.set_index("date")["ad_line"])

st.subheader("Recent Alerts")
st.dataframe(alerts, use_container_width=True)
