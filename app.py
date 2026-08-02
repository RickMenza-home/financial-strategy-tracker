"""
Financial Strategy Tracker — Streamlit application entry point.

Wires all pages together with sidebar navigation.
Run with: streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from repository import Repository

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Financial Strategy Tracker",
    page_icon="📈",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Shared repository instance (cached for the session)
# ---------------------------------------------------------------------------


@st.cache_resource
def get_repo() -> Repository:
    return Repository()


repo = get_repo()

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

PAGES = {
    "Dashboard":     "dashboard",
    "Add Trade":     "add_trade",
    "Trades":        "trades",
    "Import Trades": "import_trades",
    "Positions":     "positions",
    "Assignments":   "assignments",
    "Covered Calls": "covered_calls",
    "Dividends":     "dividends",
}

with st.sidebar:
    st.title("Strategy Tracker")
    selection = st.radio("Navigate", list(PAGES.keys()), label_visibility="collapsed")

# ---------------------------------------------------------------------------
# Page routing
# ---------------------------------------------------------------------------

if selection == "Dashboard":
    from views.dashboard import render
    render(repo)

elif selection == "Add Trade":
    st.header("Add Trade")
    st.info("Coming in Task 8.")

elif selection == "Trades":
    st.header("Trades")
    st.info("Coming in Task 8.")

elif selection == "Import Trades":
    st.header("Import Trades")
    st.info("Coming in Task 11.")

elif selection == "Positions":
    st.header("Positions")
    st.info("Coming in Task 9.")

elif selection == "Assignments":
    st.header("Assignments")
    st.info("Coming in Task 10.")

elif selection == "Covered Calls":
    st.header("Covered Calls")
    st.info("Coming in Task 10.")

elif selection == "Dividends":
    st.header("Dividends")
    st.info("Coming in Task 13.")
