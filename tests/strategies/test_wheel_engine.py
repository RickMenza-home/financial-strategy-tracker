"""
Unit tests for strategies/wheel/engine.py and strategies/wheel/calculations.py.

Covers all cases listed in §15.1:
  - CSP open / expired-unassigned / expired-assigned
  - CC open / closed / expired / called-away
  - Cost basis reduction uses net_premium_value
  - Cycle number increment on CSP assignment
  - shares floor at 0 on CALL ASSIGNED
  - total_fees_paid accumulation (trades + dividends)
  - broker_fee propagated to Assignment and lifecycle events
  - Dividend reduces cost_basis by dividend_per_share
  - Dividend accumulates dividends_collected
  - Dividend skipped when shares == 0

Also covers the full end-to-end recalculate_positions round-trip via Repository.
"""

import pytest
from datetime import date

from constants import TradeAction, AssignmentType
from models import Dividend, Trade
from strategies.wheel.engine import WheelPlugin, WheelStatus
from strategies.wheel.calculations import (
    cost_basis_reduction_per_share,
    net_stock_basis,
)
from calculations import net_premium_value
from repository import Repository

# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

SYMBOL = "SOFI"
STRATEGY_TYPE = "wheel"


@pytest.fixture
def plugin():
    return WheelPlugin()


@pytest.fixture
def state(plugin):
    return plugin.initial_position_state(SYMBOL)


@pytest.fixture
def repo():
    return Repository(db_path=":memory:")


def _trade(**kw) -> Trade:
    defaults = dict(
        id=1,
        strategy_type=STRATEGY_TYPE,
        symbol=SYMBOL,
        strategy="CSP",
        action=TradeAction.SELL,
        trade_date=date(2026, 1, 10),
        expiration=date(2026, 2, 21),
        strike=16.0,
        premium=0.50,
        contracts=1,
        broker_fee=1.05,
        status="OPEN",
        notes="",
    )
    defaults.update(kw)
    return Trade(**defaults)


def _dividend(**kw) -> Dividend:
    defaults = dict(
        id=1,
        strategy_type=STRATEGY_TYPE,
        symbol=SYMBOL,
        dividend_date=date(2026, 3, 15),
        amount=12.00,
        shares=100,
        broker_fee=0.0,
        notes="",
    )
    defaults.update(kw)
    return Dividend(**defaults)


# ---------------------------------------------------------------------------
# Initial state  §3.1
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_all_zeros(self, plugin):
        s = plugin.initial_position_state(SYMBOL)
        assert s["shares"]             == 0
        assert s["cost_basis"]         == 0.0
        assert s["premium_collected"]  == 0.0
        assert s["total_fees_paid"]    == 0.0
        assert s["dividends_collected"] == 0.0
        assert s["cycle_number"]       == 0

    def test_status_is_csp(self, plugin):
        s = plugin.initial_position_state(SYMBOL)
        assert s["wheel_status"] == WheelStatus.CSP

    def test_symbol_stored(self, plugin):
        s = plugin.initial_position_state("NKE")
        assert s["symbol"] == "NKE"


# ---------------------------------------------------------------------------
# §3.2  CSP — OPEN (no assignment)
# ---------------------------------------------------------------------------

class TestCSPOpen:
    def test_premium_collected_accumulates(self, plugin, state):
        t = _trade(status="OPEN", premium=0.50, contracts=1, broker_fee=1.05)
        result = plugin.process_trade(t, state)
        net = net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05)
        assert result.state["premium_collected"] == pytest.approx(net)

    def test_fee_accumulates(self, plugin, state):
        t = _trade(status="OPEN", broker_fee=1.05)
        result = plugin.process_trade(t, state)
        assert result.state["total_fees_paid"] == pytest.approx(1.05)

    def test_no_assignment_events(self, plugin, state):
        t = _trade(status="OPEN")
        result = plugin.process_trade(t, state)
        assert result.assignments == []

    def test_no_lifecycle_events(self, plugin, state):
        t = _trade(status="OPEN")
        result = plugin.process_trade(t, state)
        assert result.lifecycle_events == []

    def test_shares_unchanged(self, plugin, state):
        t = _trade(status="OPEN")
        result = plugin.process_trade(t, state)
        assert result.state["shares"] == 0

    def test_status_unchanged(self, plugin, state):
        t = _trade(status="OPEN")
        result = plugin.process_trade(t, state)
        assert result.state["wheel_status"] == WheelStatus.CSP

    def test_multiple_csp_accumulate(self, plugin, state):
        for _ in range(3):
            result = plugin.process_trade(_trade(status="OPEN", broker_fee=1.05), state)
            state = result.state
        net = net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05)
        assert state["premium_collected"] == pytest.approx(net * 3)
        assert state["total_fees_paid"]   == pytest.approx(1.05 * 3)


# ---------------------------------------------------------------------------
# §3.2  CSP — EXPIRED (unassigned)
# ---------------------------------------------------------------------------

class TestCSPExpired:
    def test_premium_collected(self, plugin, state):
        t = _trade(status="EXPIRED")
        result = plugin.process_trade(t, state)
        net = net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05)
        assert result.state["premium_collected"] == pytest.approx(net)

    def test_no_assignment(self, plugin, state):
        result = plugin.process_trade(_trade(status="EXPIRED"), state)
        assert result.assignments == []

    def test_shares_still_zero(self, plugin, state):
        result = plugin.process_trade(_trade(status="EXPIRED"), state)
        assert result.state["shares"] == 0

    def test_status_stays_csp(self, plugin, state):
        result = plugin.process_trade(_trade(status="EXPIRED"), state)
        assert result.state["wheel_status"] == WheelStatus.CSP


# ---------------------------------------------------------------------------
# §3.2  CSP — ASSIGNED
# ---------------------------------------------------------------------------

class TestCSPAssigned:
    def _assign(self, plugin, state, strike=16.0, contracts=1, premium=0.50,
                broker_fee=1.05):
        t = _trade(status="ASSIGNED", strike=strike, contracts=contracts,
                   premium=premium, broker_fee=broker_fee)
        return plugin.process_trade(t, state)

    def test_shares_added(self, plugin, state):
        result = self._assign(plugin, state, contracts=1)
        assert result.state["shares"] == 100

    def test_shares_added_two_contracts(self, plugin, state):
        result = self._assign(plugin, state, contracts=2)
        assert result.state["shares"] == 200

    def test_cycle_number_incremented(self, plugin, state):
        result = self._assign(plugin, state)
        assert result.state["cycle_number"] == 1

    def test_status_becomes_covered_calls(self, plugin, state):
        result = self._assign(plugin, state)
        assert result.state["wheel_status"] == WheelStatus.COVERED_CALLS

    def test_cost_basis_per_share(self, plugin, state):
        # cost_basis = strike - (net_pv / shares)
        net_pv = net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05)
        result = self._assign(plugin, state, strike=16.0, contracts=1,
                               premium=0.50, broker_fee=1.05)
        expected = 16.0 - (net_pv / 100)
        assert result.state["cost_basis"] == pytest.approx(expected)

    def test_assignment_event_created(self, plugin, state):
        result = self._assign(plugin, state)
        assert len(result.assignments) == 1

    def test_assignment_type_put_assigned(self, plugin, state):
        result = self._assign(plugin, state)
        assert result.assignments[0].assignment_type == "PUT ASSIGNED"

    def test_assignment_shares_positive(self, plugin, state):
        result = self._assign(plugin, state, contracts=1)
        assert result.assignments[0].shares == 100

    def test_assignment_broker_fee_propagated(self, plugin, state):
        result = self._assign(plugin, state, broker_fee=2.10)
        assert result.assignments[0].broker_fee == pytest.approx(2.10)

    def test_assignment_net_stock_basis(self, plugin, state):
        net_pv = net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05)
        expected_nsb = net_stock_basis(16.0, 1, net_pv, AssignmentType.PUT)
        result = self._assign(plugin, state)
        assert result.assignments[0].net_stock_basis == pytest.approx(expected_nsb)

    def test_assignment_stock_value(self, plugin, state):
        result = self._assign(plugin, state, strike=16.0, contracts=1)
        assert result.assignments[0].stock_value == pytest.approx(1600.0)

    def test_premium_and_fees_accumulated(self, plugin, state):
        net_pv = net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05)
        result = self._assign(plugin, state)
        assert result.state["premium_collected"] == pytest.approx(net_pv)
        assert result.state["total_fees_paid"]   == pytest.approx(1.05)


# ---------------------------------------------------------------------------
# §3.3  CC — helpers
# ---------------------------------------------------------------------------

def _csp_assign_state(plugin):
    """Return a state after one CSP assignment (shares=100, cycle=1)."""
    state = plugin.initial_position_state(SYMBOL)
    t = _trade(strategy="CSP", status="ASSIGNED", strike=16.0, contracts=1,
               premium=0.50, broker_fee=1.05)
    return plugin.process_trade(t, state).state


def _cc_trade(**kw) -> Trade:
    defaults = dict(strategy="CC", strike=17.0, premium=0.40,
                    contracts=1, broker_fee=1.05, status="OPEN",
                    trade_date=date(2026, 3, 1), expiration=date(2026, 3, 21))
    defaults.update(kw)
    return _trade(**defaults)


# ---------------------------------------------------------------------------
# §3.3  CC — OPEN
# ---------------------------------------------------------------------------

class TestCCOpen:
    def test_lifecycle_event_created(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="OPEN"), state)
        assert len(result.lifecycle_events) == 1

    def test_lifecycle_stage_open(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="OPEN"), state)
        assert result.lifecycle_events[0].lifecycle_stage == "OPEN"

    def test_status_becomes_cc_open(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="OPEN"), state)
        assert result.state["wheel_status"] == WheelStatus.CC_OPEN

    def test_cost_basis_reduced(self, plugin):
        state = _csp_assign_state(plugin)
        basis_before = state["cost_basis"]
        net_pv = net_premium_value(0.40, 1, TradeAction.SELL, broker_fee=1.05)
        result = plugin.process_trade(_cc_trade(status="OPEN"), state)
        reduction = cost_basis_reduction_per_share(net_pv, 1)
        assert result.state["cost_basis"] == pytest.approx(basis_before - reduction)

    def test_cost_basis_uses_net_not_gross(self, plugin):
        """Reduction must use net_premium_value, not gross premium."""
        state = _csp_assign_state(plugin)
        basis_before = state["cost_basis"]
        gross_reduction = cost_basis_reduction_per_share(0.40 * 100, 1)
        net_pv = net_premium_value(0.40, 1, TradeAction.SELL, broker_fee=1.05)
        net_reduction = cost_basis_reduction_per_share(net_pv, 1)
        result = plugin.process_trade(_cc_trade(status="OPEN"), state)
        # Must match net, not gross
        assert result.state["cost_basis"] == pytest.approx(basis_before - net_reduction)
        assert result.state["cost_basis"] != pytest.approx(basis_before - gross_reduction)

    def test_premium_accumulated(self, plugin):
        state = _csp_assign_state(plugin)
        premium_before = state["premium_collected"]
        net_pv = net_premium_value(0.40, 1, TradeAction.SELL, broker_fee=1.05)
        result = plugin.process_trade(_cc_trade(status="OPEN"), state)
        assert result.state["premium_collected"] == pytest.approx(premium_before + net_pv)

    def test_fee_accumulated(self, plugin):
        state = _csp_assign_state(plugin)
        fees_before = state["total_fees_paid"]
        result = plugin.process_trade(_cc_trade(status="OPEN", broker_fee=2.10), state)
        assert result.state["total_fees_paid"] == pytest.approx(fees_before + 2.10)

    def test_lifecycle_broker_fee_propagated(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="OPEN", broker_fee=2.10), state)
        assert result.lifecycle_events[0].broker_fee == pytest.approx(2.10)

    def test_lifecycle_cycle_number(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="OPEN"), state)
        assert result.lifecycle_events[0].cycle_number == 1

    def test_lifecycle_shares_covered(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="OPEN", contracts=1), state)
        assert result.lifecycle_events[0].shares_covered == 100

    def test_no_assignment_event(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="OPEN"), state)
        assert result.assignments == []


# ---------------------------------------------------------------------------
# §3.3  CC — CLOSED
# ---------------------------------------------------------------------------

class TestCCClosed:
    def test_lifecycle_stage_closed(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="CLOSED"), state)
        assert result.lifecycle_events[0].lifecycle_stage == "CLOSED"

    def test_status_becomes_ready_for_cc(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="CLOSED"), state)
        assert result.state["wheel_status"] == WheelStatus.READY_FOR_CC

    def test_cost_basis_reduced(self, plugin):
        state = _csp_assign_state(plugin)
        basis_before = state["cost_basis"]
        net_pv = net_premium_value(0.40, 1, TradeAction.SELL, broker_fee=1.05)
        result = plugin.process_trade(_cc_trade(status="CLOSED"), state)
        assert result.state["cost_basis"] == pytest.approx(
            basis_before - cost_basis_reduction_per_share(net_pv, 1)
        )

    def test_no_assignment_event(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="CLOSED"), state)
        assert result.assignments == []


# ---------------------------------------------------------------------------
# §3.3  CC — EXPIRED
# ---------------------------------------------------------------------------

class TestCCExpired:
    def test_lifecycle_stage_expired(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="EXPIRED"), state)
        assert result.lifecycle_events[0].lifecycle_stage == "EXPIRED"

    def test_status_becomes_ready_for_cc(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="EXPIRED"), state)
        assert result.state["wheel_status"] == WheelStatus.READY_FOR_CC

    def test_cost_basis_reduced(self, plugin):
        state = _csp_assign_state(plugin)
        basis_before = state["cost_basis"]
        net_pv = net_premium_value(0.40, 1, TradeAction.SELL, broker_fee=1.05)
        result = plugin.process_trade(_cc_trade(status="EXPIRED"), state)
        assert result.state["cost_basis"] == pytest.approx(
            basis_before - cost_basis_reduction_per_share(net_pv, 1)
        )

    def test_shares_unchanged(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="EXPIRED"), state)
        assert result.state["shares"] == 100

    def test_no_assignment_event(self, plugin):
        state = _csp_assign_state(plugin)
        result = plugin.process_trade(_cc_trade(status="EXPIRED"), state)
        assert result.assignments == []


# ---------------------------------------------------------------------------
# §3.3  CC — ASSIGNED (called away)
# ---------------------------------------------------------------------------

class TestCCCalledAway:
    def _called_away(self, plugin, state, contracts=1, broker_fee=1.05):
        t = _cc_trade(status="ASSIGNED", contracts=contracts, broker_fee=broker_fee)
        return plugin.process_trade(t, state)

    def test_shares_reduced_to_zero(self, plugin):
        state = _csp_assign_state(plugin)   # shares=100
        result = self._called_away(plugin, state, contracts=1)
        assert result.state["shares"] == 0

    def test_shares_floor_at_zero(self, plugin):
        """Calling away more shares than held must never go negative."""
        state = _csp_assign_state(plugin)   # shares=100
        result = self._called_away(plugin, state, contracts=2)  # would be -100
        assert result.state["shares"] == 0

    def test_status_becomes_csp_when_no_shares(self, plugin):
        state = _csp_assign_state(plugin)
        result = self._called_away(plugin, state, contracts=1)
        assert result.state["wheel_status"] == WheelStatus.CSP

    def test_cost_basis_zeroed_when_no_shares(self, plugin):
        state = _csp_assign_state(plugin)
        result = self._called_away(plugin, state, contracts=1)
        assert result.state["cost_basis"] == pytest.approx(0.0)

    def test_status_ready_for_cc_when_shares_remain(self, plugin):
        """If more than 1 contract held but only 1 called away, status = READY FOR CC."""
        state = plugin.initial_position_state(SYMBOL)
        # Assign 2 contracts of CSP → 200 shares
        t = _trade(strategy="CSP", status="ASSIGNED", contracts=2, broker_fee=0.0)
        state = plugin.process_trade(t, state).state
        assert state["shares"] == 200
        # Call away 1 contract → 100 shares remain
        result = self._called_away(plugin, state, contracts=1)
        assert result.state["shares"] == 100
        assert result.state["wheel_status"] == WheelStatus.READY_FOR_CC

    def test_lifecycle_stage_called_away(self, plugin):
        state = _csp_assign_state(plugin)
        result = self._called_away(plugin, state)
        assert result.lifecycle_events[0].lifecycle_stage == "CALLED AWAY"

    def test_assignment_event_created(self, plugin):
        state = _csp_assign_state(plugin)
        result = self._called_away(plugin, state)
        assert len(result.assignments) == 1

    def test_assignment_type_call_assigned(self, plugin):
        state = _csp_assign_state(plugin)
        result = self._called_away(plugin, state)
        assert result.assignments[0].assignment_type == "CALL ASSIGNED"

    def test_assignment_shares_negative(self, plugin):
        state = _csp_assign_state(plugin)
        result = self._called_away(plugin, state, contracts=1)
        assert result.assignments[0].shares == -100

    def test_assignment_broker_fee_propagated(self, plugin):
        state = _csp_assign_state(plugin)
        result = self._called_away(plugin, state, broker_fee=2.10)
        assert result.assignments[0].broker_fee == pytest.approx(2.10)

    def test_assignment_net_stock_basis(self, plugin):
        state = _csp_assign_state(plugin)
        net_pv = net_premium_value(0.40, 1, TradeAction.SELL, broker_fee=1.05)
        expected = net_stock_basis(17.0, 1, net_pv, AssignmentType.CALL)
        result = self._called_away(plugin, state)
        assert result.assignments[0].net_stock_basis == pytest.approx(expected)


# ---------------------------------------------------------------------------
# §3.6  Dividend processing
# ---------------------------------------------------------------------------

class TestDividendProcessing:
    def test_dividends_collected_accumulated(self, plugin):
        state = _csp_assign_state(plugin)   # shares=100
        d = _dividend(amount=12.00, broker_fee=0.0)
        state = plugin.process_dividend(d, state)
        assert state["dividends_collected"] == pytest.approx(12.00)

    def test_dividend_fee_accumulates_in_total_fees(self, plugin):
        state = _csp_assign_state(plugin)
        fees_before = state["total_fees_paid"]
        d = _dividend(amount=12.00, broker_fee=0.50)
        state = plugin.process_dividend(d, state)
        assert state["total_fees_paid"] == pytest.approx(fees_before + 0.50)

    def test_cost_basis_reduced_by_dividend_per_share(self, plugin):
        state = _csp_assign_state(plugin)   # shares=100
        basis_before = state["cost_basis"]
        d = _dividend(amount=12.00, shares=100, broker_fee=0.0)
        state = plugin.process_dividend(d, state)
        assert state["cost_basis"] == pytest.approx(basis_before - 0.12)

    def test_cost_basis_reduction_uses_net_dividend(self, plugin):
        state = _csp_assign_state(plugin)
        basis_before = state["cost_basis"]
        # net = 12.00 - 0.50 = 11.50 → per share = 0.115
        d = _dividend(amount=12.00, shares=100, broker_fee=0.50)
        state = plugin.process_dividend(d, state)
        assert state["cost_basis"] == pytest.approx(basis_before - 0.115)

    def test_multiple_dividends_accumulate(self, plugin):
        state = _csp_assign_state(plugin)
        for _ in range(3):
            state = plugin.process_dividend(
                _dividend(amount=12.00, shares=100, broker_fee=0.0), state
            )
        assert state["dividends_collected"] == pytest.approx(36.00)

    def test_dividend_skipped_when_no_shares_via_engine(self, plugin):
        """Engine must not call process_dividend when shares == 0."""
        state = plugin.initial_position_state(SYMBOL)
        assert state["shares"] == 0
        # Simulate what the engine does: check shares > 0 before calling
        d = _dividend(amount=12.00, shares=100, broker_fee=0.0)
        if state["shares"] > 0:
            state = plugin.process_dividend(d, state)
        assert state["dividends_collected"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Wheel calculations (§2.5, §2.6, §2.7)
# ---------------------------------------------------------------------------

class TestWheelCalculations:
    def test_net_stock_basis_put(self):
        # stock_value = 16 × 100 = 1600; net_pv = 50 − 1.05 = 48.95
        # nsb = 1600 − 48.95 = 1551.05
        net_pv = net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05)
        assert net_stock_basis(16.0, 1, net_pv, AssignmentType.PUT) == pytest.approx(1551.05)

    def test_net_stock_basis_put_two_contracts(self):
        net_pv = net_premium_value(0.50, 2, TradeAction.SELL, broker_fee=2.10)
        assert net_stock_basis(16.0, 2, net_pv, AssignmentType.PUT) == pytest.approx(3200 - net_pv)

    def test_net_stock_basis_call(self):
        # stock_value = 17 × 100 = 1700; net_pv = 40 − 1.05 = 38.95
        # nsb = 1700 + 38.95 = 1738.95
        net_pv = net_premium_value(0.40, 1, TradeAction.SELL, broker_fee=1.05)
        assert net_stock_basis(17.0, 1, net_pv, AssignmentType.CALL) == pytest.approx(1738.95)

    def test_net_stock_basis_call_two_contracts(self):
        net_pv = net_premium_value(0.40, 2, TradeAction.SELL, broker_fee=2.10)
        assert net_stock_basis(17.0, 2, net_pv, AssignmentType.CALL) == pytest.approx(3400 + net_pv)

    def test_put_and_call_differ_by_twice_net_premium(self):
        """PUT reduces basis, CALL adds it — they differ by 2 × net_premium."""
        net_pv = net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05)
        put_nsb  = net_stock_basis(16.0, 1, net_pv, AssignmentType.PUT)
        call_nsb = net_stock_basis(16.0, 1, net_pv, AssignmentType.CALL)
        assert call_nsb - put_nsb == pytest.approx(2 * net_pv)

    def test_cost_basis_reduction_per_share(self):
        net_pv = net_premium_value(0.40, 1, TradeAction.SELL, broker_fee=1.05)
        assert cost_basis_reduction_per_share(net_pv, 1) == pytest.approx(net_pv / 100)

    def test_cost_basis_reduction_two_contracts(self):
        net_pv = net_premium_value(0.40, 2, TradeAction.SELL, broker_fee=2.10)
        assert cost_basis_reduction_per_share(net_pv, 2) == pytest.approx(net_pv / 200)


# ---------------------------------------------------------------------------
# StrategyPlugin interface contract  §3.0
# ---------------------------------------------------------------------------

class TestPluginInterface:
    def test_has_strategy_type(self, plugin):
        assert isinstance(plugin.strategy_type, str)
        assert plugin.strategy_type == "wheel"

    def test_has_display_name(self, plugin):
        assert isinstance(plugin.display_name, str)
        assert len(plugin.display_name) > 0

    def test_initial_position_state_returns_dict(self, plugin):
        assert isinstance(plugin.initial_position_state("X"), dict)

    def test_process_trade_returns_plugin_result(self, plugin, state):
        from models import PluginResult
        result = plugin.process_trade(_trade(), state)
        assert isinstance(result, PluginResult)

    def test_get_available_actions_returns_list(self, plugin):
        from models import Position
        pos = Position("SOFI", "wheel", 0, 0.0, 0.0, 0.0, 0.0, WheelStatus.CSP)
        actions = plugin.get_available_actions(pos)
        assert isinstance(actions, list)

    @pytest.mark.parametrize("status,expected_actions", [
        (WheelStatus.CSP,           ["CLOSE_CSP", "CSP_EXPIRED_UNASSIGNED", "CSP_ASSIGNED"]),
        (WheelStatus.COVERED_CALLS, ["ADJUST_PREMIUM", "KEEP_SHARES", "SELL_CC"]),
        (WheelStatus.CC_OPEN,       ["ADJUST_PREMIUM", "WAIT_FOR_EXPIRATION", "CLOSE_CC"]),
        (WheelStatus.READY_FOR_CC,  ["SELL_CC", "ADJUST_PREMIUM"]),
    ])
    def test_available_actions_by_status(self, plugin, status, expected_actions):
        from models import Position
        pos = Position("SOFI", "wheel", 0, 0.0, 0.0, 0.0, 0.0, status)
        assert plugin.get_available_actions(pos) == expected_actions


# ---------------------------------------------------------------------------
# End-to-end recalculate_positions round-trip via Repository
# ---------------------------------------------------------------------------

class TestRecalculatePositionsEndToEnd:
    """Full cycle replayed through the repository → engine → back to repository."""

    def _add_csp(self, repo, status, **kw):
        defaults = dict(
            id=None, strategy_type="wheel", symbol=SYMBOL,
            strategy="CSP", action=TradeAction.SELL,
            trade_date=date(2026, 1, 10), expiration=date(2026, 2, 21),
            strike=16.0, premium=0.50, contracts=1, broker_fee=1.05,
            status=status, notes="",
        )
        defaults.update(kw)
        return repo.add_trade(Trade(**defaults))

    def _add_cc(self, repo, status, **kw):
        defaults = dict(
            id=None, strategy_type="wheel", symbol=SYMBOL,
            strategy="CC", action=TradeAction.SELL,
            trade_date=date(2026, 3, 1), expiration=date(2026, 3, 21),
            strike=17.0, premium=0.40, contracts=1, broker_fee=1.05,
            status=status, notes="",
        )
        defaults.update(kw)
        return repo.add_trade(Trade(**defaults))

    def test_open_csp_creates_position(self, repo):
        self._add_csp(repo, "OPEN")
        repo.recalculate_positions()
        pos = repo.get_position_by_symbol(SYMBOL)
        assert pos is not None
        assert pos.shares == 0
        assert pos.status == WheelStatus.CSP

    def test_assigned_csp_creates_assignment(self, repo):
        self._add_csp(repo, "ASSIGNED")
        repo.recalculate_positions()
        assignments = repo.get_assignments()
        assert len(assignments) == 1
        assert assignments[0].assignment_type == "PUT ASSIGNED"

    def test_assigned_csp_position_has_shares(self, repo):
        self._add_csp(repo, "ASSIGNED")
        repo.recalculate_positions()
        pos = repo.get_position_by_symbol(SYMBOL)
        assert pos.shares == 100
        assert pos.status == WheelStatus.COVERED_CALLS

    def test_full_csp_cc_expired_cycle(self, repo):
        self._add_csp(repo, "ASSIGNED")
        self._add_cc(repo, "EXPIRED")
        repo.recalculate_positions()
        pos = repo.get_position_by_symbol(SYMBOL)
        assert pos.shares == 100
        assert pos.status == WheelStatus.READY_FOR_CC
        events = repo.get_covered_call_lifecycle()
        assert len(events) == 1
        assert events[0].lifecycle_stage == "EXPIRED"

    def test_full_csp_cc_called_away_resets_position(self, repo):
        self._add_csp(repo, "ASSIGNED")
        self._add_cc(repo, "ASSIGNED")
        repo.recalculate_positions()
        pos = repo.get_position_by_symbol(SYMBOL)
        assert pos.shares == 0
        assert pos.status == WheelStatus.CSP
        assert len(repo.get_assignments()) == 2  # PUT + CALL

    def test_premium_and_fees_accumulated_across_trades(self, repo):
        self._add_csp(repo, "ASSIGNED")
        self._add_cc(repo, "EXPIRED")
        repo.recalculate_positions()
        pos = repo.get_position_by_symbol(SYMBOL)
        net_csp = net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05)
        net_cc  = net_premium_value(0.40, 1, TradeAction.SELL, broker_fee=1.05)
        assert pos.premium_collected == pytest.approx(net_csp + net_cc)
        assert pos.total_fees_paid   == pytest.approx(1.05 + 1.05)

    def test_dividend_included_in_position(self, repo):
        self._add_csp(repo, "ASSIGNED")
        repo.add_dividend(Dividend(
            id=None, strategy_type="wheel", symbol=SYMBOL,
            dividend_date=date(2026, 3, 1), amount=12.00,
            shares=100, broker_fee=0.0, notes="",
        ))
        repo.recalculate_positions()
        pos = repo.get_position_by_symbol(SYMBOL)
        assert pos.dividends_collected == pytest.approx(12.00)

    def test_recalculate_is_idempotent(self, repo):
        self._add_csp(repo, "ASSIGNED")
        self._add_cc(repo, "EXPIRED")
        repo.recalculate_positions()
        repo.recalculate_positions()
        assert len(repo.get_positions())             == 1
        assert len(repo.get_assignments())           == 1
        assert len(repo.get_covered_call_lifecycle()) == 1

    def test_two_symbols_independent(self, repo):
        self._add_csp(repo, "ASSIGNED", symbol="SOFI")
        self._add_csp(repo, "OPEN",     symbol="NKE")
        repo.recalculate_positions()
        assert repo.get_position_by_symbol("SOFI").shares == 100
        assert repo.get_position_by_symbol("NKE").shares  == 0
