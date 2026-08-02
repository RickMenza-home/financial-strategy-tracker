"""
Wheel strategy plugin — position state machine.

Implements §3.1 (initial state), §3.2 (CSP processing), §3.3 (CC processing),
§3.4 (lifecycle stage mapping), and §3.6 (dividend processing) from REQUIREMENTS.md.

This module is pure: no database access, no side effects.
May import: models, strategies/base, strategies/wheel/calculations, calculations.
"""

from __future__ import annotations

from models import Assignment, CoveredCallLifecycle, PluginResult, Position, Trade
from calculations import net_premium_value
from constants import SHARES_PER_CONTRACT, TradeAction, AssignmentType
from strategies.base import StrategyPlugin
from strategies.wheel.calculations import (
    cost_basis_reduction_per_share,
    net_stock_basis,
)


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

class WheelStatus:
    CSP           = "CSP"
    COVERED_CALLS = "COVERED CALLS"
    READY_FOR_CC  = "READY FOR CC"
    CC_OPEN       = "CC OPEN"


# ---------------------------------------------------------------------------
# Lifecycle stage mapping  §3.4
# ---------------------------------------------------------------------------

_LIFECYCLE_STAGE: dict[str, str] = {
    "OPEN":     "OPEN",
    "CLOSED":   "CLOSED",
    "EXPIRED":  "EXPIRED",
    "ASSIGNED": "CALLED AWAY",
}

# ---------------------------------------------------------------------------
# Available actions by status  §10.3
# ---------------------------------------------------------------------------

_AVAILABLE_ACTIONS: dict[str, list[str]] = {
    WheelStatus.CSP: [
        "CLOSE_CSP",
        "CSP_EXPIRED_UNASSIGNED",
        "CSP_ASSIGNED",
    ],
    WheelStatus.COVERED_CALLS: [
        "ADJUST_PREMIUM",
        "KEEP_SHARES",
        "SELL_CC",
    ],
    WheelStatus.CC_OPEN: [
        "ADJUST_PREMIUM",
        "WAIT_FOR_EXPIRATION",
        "CLOSE_CC",
    ],
    WheelStatus.READY_FOR_CC: [
        "SELL_CC",
        "ADJUST_PREMIUM",
    ],
}


# ---------------------------------------------------------------------------
# WheelPlugin
# ---------------------------------------------------------------------------

class WheelPlugin(StrategyPlugin):
    """Wheel options strategy plugin."""

    strategy_type = "wheel"
    display_name  = "Wheel Strategy"

    # ------------------------------------------------------------------
    # §3.1  Initial state
    # ------------------------------------------------------------------

    def initial_position_state(self, symbol: str) -> dict:
        return {
            "symbol":             symbol,
            "strategy_type":      self.strategy_type,
            "shares":             0,
            "cost_basis":         0.0,
            "premium_collected":  0.0,
            "total_fees_paid":    0.0,
            "dividends_collected": 0.0,
            "wheel_status":       WheelStatus.CSP,
            "cycle_number":       0,
        }

    # ------------------------------------------------------------------
    # §3.0  process_trade dispatcher
    # ------------------------------------------------------------------

    def process_trade(self, trade: Trade, state: dict) -> PluginResult:
        if trade.strategy == "CSP":
            return self._process_csp(trade, state)
        if trade.strategy == "CC":
            return self._process_cc(trade, state)
        # Unknown strategy sub-type — pass through unchanged
        return PluginResult(state=state)

    # ------------------------------------------------------------------
    # §3.2  CSP processing
    # ------------------------------------------------------------------

    def _process_csp(self, trade: Trade, state: dict) -> PluginResult:
        net_pv = net_premium_value(
            trade.premium, trade.contracts, trade.action,
            broker_fee=trade.broker_fee,
        )

        state["premium_collected"] += net_pv
        state["total_fees_paid"]   += trade.broker_fee

        assignments: list[Assignment] = []

        if trade.status == "ASSIGNED":
            shares_added = trade.contracts * SHARES_PER_CONTRACT
            nsb = net_stock_basis(trade.strike, trade.contracts, net_pv,
                                   AssignmentType.PUT)

            state["shares"]        += shares_added
            # cost basis per share: strike minus net_premium per share
            state["cost_basis"]     = trade.strike - (net_pv / shares_added)
            state["wheel_status"]   = WheelStatus.COVERED_CALLS
            state["cycle_number"]  += 1

            assignments.append(Assignment(
                id              = None,
                trade_id        = trade.id,
                symbol          = trade.symbol,
                assignment_date = trade.expiration,
                strategy        = "CSP",
                assignment_type = "PUT ASSIGNED",
                strike          = trade.strike,
                premium         = trade.premium,
                contracts       = trade.contracts,
                broker_fee      = trade.broker_fee,
                shares          = shares_added,
                stock_value     = trade.strike * shares_added,
                premium_value   = net_pv,
                net_stock_basis = nsb,
                notes           = trade.notes,
            ))

        return PluginResult(state=state, assignments=assignments)

    # ------------------------------------------------------------------
    # §3.3  CC processing
    # ------------------------------------------------------------------

    def _process_cc(self, trade: Trade, state: dict) -> PluginResult:
        net_pv = net_premium_value(
            trade.premium, trade.contracts, trade.action,
            broker_fee=trade.broker_fee,
        )

        state["premium_collected"] += net_pv
        state["total_fees_paid"]   += trade.broker_fee

        lifecycle_stage = _LIFECYCLE_STAGE.get(trade.status, trade.status)

        lifecycle = CoveredCallLifecycle(
            id              = None,
            trade_id        = trade.id,
            symbol          = trade.symbol,
            cycle_number    = state["cycle_number"],
            trade_date      = trade.trade_date,
            expiration      = trade.expiration,
            action          = trade.action,
            lifecycle_stage = lifecycle_stage,
            strike          = trade.strike,
            premium         = trade.premium,
            contracts       = trade.contracts,
            broker_fee      = trade.broker_fee,
            shares_covered  = trade.contracts * SHARES_PER_CONTRACT,
            premium_value   = net_pv,
            notes           = trade.notes,
        )

        assignments: list[Assignment] = []

        if trade.status in ("OPEN", "CLOSED", "EXPIRED"):
            # Reduce cost basis per share by the fee-adjusted premium
            reduction = cost_basis_reduction_per_share(net_pv, trade.contracts)
            state["cost_basis"] -= reduction

            if state["shares"] > 0:
                state["wheel_status"] = (
                    WheelStatus.CC_OPEN
                    if trade.status == "OPEN"
                    else WheelStatus.READY_FOR_CC
                )

        elif trade.status == "ASSIGNED":
            shares_called = trade.contracts * SHARES_PER_CONTRACT
            nsb = net_stock_basis(trade.strike, trade.contracts, net_pv,
                                   AssignmentType.CALL)

            state["shares"] = max(0, state["shares"] - shares_called)

            assignments.append(Assignment(
                id              = None,
                trade_id        = trade.id,
                symbol          = trade.symbol,
                assignment_date = trade.expiration,
                strategy        = "CC",
                assignment_type = "CALL ASSIGNED",
                strike          = trade.strike,
                premium         = trade.premium,
                contracts       = trade.contracts,
                broker_fee      = trade.broker_fee,
                shares          = -shares_called,
                stock_value     = trade.strike * shares_called,
                premium_value   = net_pv,
                net_stock_basis = nsb,
                notes           = trade.notes,
            ))

            if state["shares"] == 0:
                state["cost_basis"]   = 0.0
                state["wheel_status"] = WheelStatus.CSP
            else:
                state["wheel_status"] = WheelStatus.READY_FOR_CC

        return PluginResult(
            state=state,
            assignments=assignments,
            lifecycle_events=[lifecycle],
        )

    # ------------------------------------------------------------------
    # §3.6  Dividend processing
    # ------------------------------------------------------------------

    def process_dividend(self, dividend, state: dict) -> dict:
        """
        Apply one dividend to the running position state.

        Only called by the engine when state["shares"] > 0.
        Returns the updated state dict.
        """
        from calculations import net_dividend, dividend_per_share as _dps

        nd  = net_dividend(dividend.amount, dividend.broker_fee)
        dps = _dps(dividend.amount, state["shares"], dividend.broker_fee)

        state["dividends_collected"] += nd
        state["total_fees_paid"]     += dividend.broker_fee
        state["cost_basis"]          -= dps

        return state

    # ------------------------------------------------------------------
    # §10.3  Available actions by status
    # ------------------------------------------------------------------

    def get_available_actions(self, position: Position) -> list[str]:
        return _AVAILABLE_ACTIONS.get(position.status, [])
