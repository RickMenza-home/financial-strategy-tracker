"""
Recalculation engine — plugin registry and orchestration.

Responsibility:
  - Hold the STRATEGY_PLUGINS registry.
  - Replay all trades and dividends in chronological order through the correct plugin.
  - Persist the resulting positions, assignments, and lifecycle events via the repository.

No SQL lives here. No business logic lives in repository.py.
May import: models, strategies/*.
"""

from __future__ import annotations

from constants import EventType
from models import Position
from strategies.base import StrategyPlugin
from strategies.wheel.engine import WheelPlugin

# ---------------------------------------------------------------------------
# Plugin registry
# ---------------------------------------------------------------------------

STRATEGY_PLUGINS: dict[str, StrategyPlugin] = {
    "wheel": WheelPlugin(),
    # "iron_condor": IronCondorPlugin(),   # future
}


# ---------------------------------------------------------------------------
# Recalculation
# ---------------------------------------------------------------------------

def recalculate_positions(repo) -> None:
    """
    Rebuild all derived data (positions, assignments, lifecycle events) by
    replaying every trade and dividend in chronological order.

    Steps (§4.2):
      1. Load all trades ordered by trade_date ASC, id ASC.
      2. Load all dividends ordered by dividend_date ASC, id ASC.
      3. Clear positions, assignments, and covered_call_lifecycle tables.
      4. Replay trades and dividends interleaved by date through the correct plugin.
      5. Persist resulting positions, assignments, and lifecycle events.

    Args:
        repo: A Repository instance (injected to avoid circular imports).
    """
    trades    = repo.get_trades_chronological()
    dividends = repo.get_dividends_chronological()

    repo.clear_derived_tables()

    # Running state per (symbol, strategy_type)
    states: dict[tuple[str, str], dict] = {}

    # Interleave trades and dividends by date
    ti = 0  # trade index
    di = 0  # dividend index

    while ti < len(trades) or di < len(dividends):
        next_event = _pick_event(trades, dividends, ti, di)

        if next_event == EventType.TRADE:
            trade  = trades[ti]
            ti    += 1
            plugin = STRATEGY_PLUGINS.get(trade.strategy_type)
            if plugin is None:
                continue  # unknown strategy — skip silently

            key = (trade.symbol, trade.strategy_type)
            if key not in states:
                states[key] = plugin.initial_position_state(trade.symbol)

            result = plugin.process_trade(trade, states[key])
            states[key] = result.state

            for assignment in result.assignments:
                repo.add_assignment(assignment)
            for event in result.lifecycle_events:
                repo.add_covered_call_lifecycle(event)

        else:
            dividend = dividends[di]
            di      += 1
            plugin   = STRATEGY_PLUGINS.get(dividend.strategy_type)
            if plugin is None:
                continue

            key = (dividend.symbol, dividend.strategy_type)
            if key not in states:
                states[key] = plugin.initial_position_state(dividend.symbol)

            if states[key]["shares"] > 0:
                states[key] = plugin.process_dividend(dividend, states[key])

    # Persist all final positions
    for (symbol, strategy_type), state in states.items():
        plugin = STRATEGY_PLUGINS.get(strategy_type)
        if plugin is None:
            continue
        position = _state_to_position(state, strategy_type)
        repo.upsert_position(position)


def _pick_event(trades, dividends, ti: int, di: int) -> EventType:
    """
    Determine whether the next event to process is a trade or a dividend.
    Trades win ties (same date → trade first).
    """
    if ti >= len(trades):
        return EventType.DIVIDEND
    if di >= len(dividends):
        return EventType.TRADE
    if trades[ti].trade_date <= dividends[di].dividend_date:
        return EventType.TRADE
    return EventType.DIVIDEND


def _state_to_position(state: dict, strategy_type: str) -> Position:
    return Position(
        symbol              = state["symbol"],
        strategy_type       = strategy_type,
        shares              = state["shares"],
        cost_basis          = state["cost_basis"],
        premium_collected   = state["premium_collected"],
        total_fees_paid     = state["total_fees_paid"],
        dividends_collected = state["dividends_collected"],
        status              = state["wheel_status"],
    )
