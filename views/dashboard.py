"""
Dashboard page (§6).

Displays summary metrics and a weekly premium bar chart.
No user input — read-only view.
"""

from __future__ import annotations

import datetime

import streamlit as st
import streamlit as st

from calculations import total_premium
from charts.premium_charts import premium_by_week_chart
from repository import Repository


def render(repo: Repository) -> None:
    """Render the Dashboard page."""
    st.header("Dashboard")

    trades    = repo.get_trades()
    positions = repo.get_positions()

    # ------------------------------------------------------------------
    # Compute metrics (§6.1)
    # ------------------------------------------------------------------
    today       = datetime.datetime.now(tz=datetime.timezone.utc).date()
    week_label  = today.strftime("%Y-W%U")
    month_label = today.strftime("%Y-%m")

    weekly_premium  = 0.0
    monthly_premium = 0.0
    gross_premium   = 0.0
    open_positions  = 0

    for t in trades:
        tp = total_premium(t.premium, t.contracts)
        gross_premium += tp
        if t.trade_date.strftime("%Y-W%U") == week_label:
            weekly_premium += tp
        if t.trade_date.strftime("%Y-%m") == month_label:
            monthly_premium += tp
        if t.status == "OPEN":
            open_positions += 1

    total_dividends = sum(p.dividends_collected for p in positions)
    total_fees      = sum(p.total_fees_paid for p in positions)
    net_premium     = gross_premium + total_dividends - total_fees

    # ------------------------------------------------------------------
    # Display metrics
    # ------------------------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Weekly Premium",  f"${weekly_premium:,.2f}")
    col2.metric("Monthly Premium", f"${monthly_premium:,.2f}")
    col3.metric("Total Premium",   f"${gross_premium:,.2f}")
    col4.metric("Open Positions",  open_positions)

    col5, col6, col7 = st.columns(3)
    col5.metric("Total Dividends", f"${total_dividends:,.2f}")
    col6.metric("Total Fees",      f"${total_fees:,.2f}")
    col7.metric("Net Premium",     f"${net_premium:,.2f}")

    # ------------------------------------------------------------------
    # Weekly premium bar chart (§6.2)
    # ------------------------------------------------------------------
    st.plotly_chart(premium_by_week_chart(trades), width="stretch")
