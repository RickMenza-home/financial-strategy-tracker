"""
Trades page (§8).

Displays all trades in a table and allows editing or deleting a selected trade.
"""

from __future__ import annotations

import datetime

import streamlit as st

from calculations import dte, total_premium
from constants import TradeAction
from engine import recalculate_positions
from models import Trade
from repository import Repository


def render(repo: Repository) -> None:
    """Render the Trades page."""
    st.header("Trades")

    trades = repo.get_trades()

    if not trades:
        st.info("No trades yet. Use the Add Trade page to enter your first trade.")
        return

    # ------------------------------------------------------------------
    # §8.1 Trade Table
    # ------------------------------------------------------------------
    today = datetime.datetime.now(tz=datetime.timezone.utc).date()

    table_data = []
    for t in trades:
        days = dte(t.expiration, t.status, today)
        tp = total_premium(t.premium, t.contracts)
        table_data.append({
            "ID":         t.id,
            "Symbol":     t.symbol,
            "Strategy":   t.strategy,
            "Action":     t.action.value if isinstance(t.action, TradeAction) else t.action,
            "Trade Date": t.trade_date.strftime("%Y-%m-%d"),
            "Expiration": t.expiration.strftime("%Y-%m-%d"),
            "Strike":     f"${t.strike:,.2f}",
            "Premium":    f"${t.premium:,.2f}",
            "Contracts":  t.contracts,
            "Broker Fee": f"${t.broker_fee:,.2f}",
            "Status":     t.status,
            "DTE":        days if days is not None else "",
            "Total Premium": f"${tp:,.2f}",
            "Notes":      t.notes,
        })

    st.dataframe(table_data, width="stretch", hide_index=True)

    # ------------------------------------------------------------------
    # §8.2 Edit Trade
    # ------------------------------------------------------------------
    st.subheader("Edit Trade")

    trade_options = {f"{t.id} — {t.symbol} {t.strategy} {t.action if isinstance(t.action, str) else t.action.value} ({t.trade_date})": t.id for t in trades}
    selected_label = st.selectbox("Select a trade to edit", options=list(trade_options.keys()))
    selected_id = trade_options[selected_label]
    selected_trade = repo.get_trade_by_id(selected_id)

    if selected_trade is None:
        st.error("Trade not found.")
        return

    with st.form("edit_trade_form"):
        col1, col2, col3, col4 = st.columns(4)

        symbol = col1.text_input("Symbol", value=selected_trade.symbol)
        strategy_type = col2.text_input("Strategy Type", value=selected_trade.strategy_type)
        strategy_options = ["CSP", "CC"]
        strategy_idx = strategy_options.index(selected_trade.strategy) if selected_trade.strategy in strategy_options else 0
        strategy = col3.selectbox("Strategy", options=strategy_options, index=strategy_idx)
        action_options = ["SELL", "BUY"]
        action_val = selected_trade.action.value if isinstance(selected_trade.action, TradeAction) else selected_trade.action
        action_idx = action_options.index(action_val) if action_val in action_options else 0
        action = col4.selectbox("Action", options=action_options, index=action_idx)

        col5, col6, col7, col8 = st.columns(4)

        trade_date = col5.date_input("Trade Date", value=selected_trade.trade_date)
        expiration = col6.date_input("Expiration", value=selected_trade.expiration)
        strike = col7.number_input("Strike", value=selected_trade.strike, min_value=0.01, step=0.50, format="%.2f")
        premium = col8.number_input("Premium", value=selected_trade.premium, min_value=0.0, step=0.01, format="%.2f")

        col9, col10, col11, col12 = st.columns(4)

        contracts = col9.number_input("Contracts", value=selected_trade.contracts, min_value=1, step=1)
        broker_fee = col10.number_input("Broker Fee", value=selected_trade.broker_fee, min_value=0.0, step=0.01, format="%.2f")
        status_options = ["OPEN", "CLOSED", "ASSIGNED", "EXPIRED"]
        status_idx = status_options.index(selected_trade.status) if selected_trade.status in status_options else 0
        status = col11.selectbox("Status", options=status_options, index=status_idx)
        notes = col12.text_input("Notes", value=selected_trade.notes)

        submitted = st.form_submit_button("Save Changes")

    if submitted:
        updated_trade = Trade(
            id=selected_trade.id,
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
        repo.update_trade(updated_trade)
        recalculate_positions(repo)
        st.success("Trade updated. Recalculation complete.")
        st.rerun()

    # ------------------------------------------------------------------
    # §8.3 Delete Trade
    # ------------------------------------------------------------------
    st.subheader("Delete Trade")

    delete_label = st.selectbox(
        "Select a trade to delete",
        options=list(trade_options.keys()),
        key="delete_select",
    )
    delete_id = trade_options[delete_label]

    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = False

    if st.button("Delete Trade"):
        st.session_state.confirm_delete = True

    if st.session_state.confirm_delete:
        st.warning("Are you sure you want to delete this trade? This cannot be undone.")
        col_yes, col_no = st.columns(2)
        if col_yes.button("Yes, delete"):
            repo.delete_trade(delete_id)
            recalculate_positions(repo)
            st.session_state.confirm_delete = False
            st.success("Trade deleted. Recalculation complete.")
            st.rerun()
        if col_no.button("Cancel"):
            st.session_state.confirm_delete = False
            st.rerun()
