"""
Add Trade page (§7).

A form for entering a single trade manually.
On submit: save trade, trigger recalculation, display confirmation.
"""

from __future__ import annotations

import datetime

import streamlit as st

from constants import TradeAction
from calculations import total_premium
from engine import recalculate_positions
from models import Trade
from repository import Repository


def render(repo: Repository) -> None:
    """Render the Add Trade page."""
    st.header("Add Trade")

    today = datetime.datetime.now(tz=datetime.timezone.utc).date()

    with st.form("add_trade_form"):
        # ---- Row 1: Symbol, Strategy Type, Strategy, Action ----
        col1, col2, col3, col4 = st.columns(4)

        symbol = col1.text_input("Symbol", value="SOFI")
        strategy_type = col2.text_input("Strategy Type", value="wheel")
        strategy = col3.selectbox("Strategy", options=["CSP", "CC"])
        action = col4.selectbox("Action", options=["SELL", "BUY"])

        # ---- Row 2: Trade Date, Expiration, Strike, Premium ----
        col5, col6, col7, col8 = st.columns(4)

        trade_date = col5.date_input("Trade Date", value=today)
        expiration = col6.date_input("Expiration", value=today)
        strike = col7.number_input("Strike", value=25.0, min_value=0.01, step=0.50, format="%.2f")
        premium = col8.number_input("Premium", value=0.50, min_value=0.0, step=0.01, format="%.2f")

        # ---- Row 3: Contracts, Broker Fee, Status, Notes ----
        col9, col10, col11, col12 = st.columns(4)

        contracts = col9.number_input("Contracts", value=1, min_value=1, step=1)
        broker_fee = col10.number_input("Broker Fee", value=0.0, min_value=0.0, step=0.01, format="%.2f")
        status = col11.selectbox("Status", options=["OPEN", "CLOSED", "ASSIGNED", "EXPIRED"])
        notes = col12.text_input("Notes", value="")

        submitted = st.form_submit_button("Add Trade")

    if submitted:
        trade = Trade(
            id=None,
            strategy_type=strategy_type.strip().lower(),
            symbol=symbol.strip().upper(),
            strategy=strategy,
            action=TradeAction(action),
            trade_date=trade_date,
            expiration=expiration,
            strike=strike,
            premium=premium,
            contracts=int(contracts),
            broker_fee=broker_fee,
            status=status,
            notes=notes.strip(),
        )
        repo.add_trade(trade)
        recalculate_positions(repo)

        tp = total_premium(trade.premium, trade.contracts)
        st.success(
            f"Trade added: {trade.action.value} {trade.contracts} {trade.symbol} "
            f"{trade.strategy} @ ${trade.premium:.2f} — "
            f"Total Premium: ${tp:,.2f}"
        )
