"""
CRUD round-trip tests for repository.py using an in-memory SQLite database.

Each test function gets a fresh Repository instance via the `repo` fixture,
so there is no shared state between tests.
"""

import pytest
from datetime import date, datetime

from models import (
    Assignment,
    CoveredCallLifecycle,
    Dividend,
    Position,
    PositionAction,
    Trade,
)
from constants import TradeAction
from repository import Repository


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def repo():
    """Fresh in-memory repository for every test."""
    return Repository(db_path=":memory:")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trade(**overrides) -> Trade:
    defaults = dict(
        id=None,
        strategy_type="wheel",
        symbol="SOFI",
        strategy="CSP",
        action=TradeAction.SELL,
        trade_date=date(2026, 1, 10),
        expiration=date(2026, 2, 21),
        strike=16.0,
        premium=0.50,
        contracts=1,
        broker_fee=1.05,
        status="OPEN",
        notes="test trade",
    )
    defaults.update(overrides)
    return Trade(**defaults)


def _position(**overrides) -> Position:
    defaults = dict(
        symbol="SOFI",
        strategy_type="wheel",
        shares=0,
        cost_basis=0.0,
        premium_collected=48.95,
        total_fees_paid=1.05,
        dividends_collected=0.0,
        status="CSP",
    )
    defaults.update(overrides)
    return Position(**defaults)


def _assignment(trade_id: int, **overrides) -> Assignment:
    defaults = dict(
        id=None,
        trade_id=trade_id,
        symbol="SOFI",
        assignment_date=date(2026, 2, 21),
        strategy="CSP",
        assignment_type="PUT ASSIGNED",
        strike=16.0,
        premium=0.50,
        contracts=1,
        broker_fee=1.05,
        shares=100,
        stock_value=1600.0,
        premium_value=48.95,
        net_stock_basis=1551.05,
        notes="",
    )
    defaults.update(overrides)
    return Assignment(**defaults)


def _lifecycle(trade_id: int, **overrides) -> CoveredCallLifecycle:
    defaults = dict(
        id=None,
        trade_id=trade_id,
        symbol="SOFI",
        cycle_number=1,
        trade_date=date(2026, 3, 1),
        expiration=date(2026, 3, 21),
        action=TradeAction.SELL,
        lifecycle_stage="OPEN",
        strike=17.0,
        premium=0.40,
        contracts=1,
        broker_fee=1.05,
        shares_covered=100,
        premium_value=38.95,
        notes="",
    )
    defaults.update(overrides)
    return CoveredCallLifecycle(**defaults)


def _position_action(**overrides) -> PositionAction:
    defaults = dict(
        id=None,
        strategy_type="wheel",
        symbol="SOFI",
        action_date=datetime(2026, 3, 1, 12, 0, 0),
        action_type="KEEP_SHARES",
        previous_status="COVERED CALLS",
        new_status="READY FOR CC",
        adjusted_premium=0.0,
        adjusted_cost_basis=0.0,
        notes="kept shares",
    )
    defaults.update(overrides)
    return PositionAction(**defaults)


def _dividend(**overrides) -> Dividend:
    defaults = dict(
        id=None,
        strategy_type="wheel",
        symbol="SOFI",
        dividend_date=date(2026, 3, 15),
        amount=12.00,
        shares=100,
        broker_fee=0.0,
        notes="",
    )
    defaults.update(overrides)
    return Dividend(**defaults)


# ---------------------------------------------------------------------------
# Trade CRUD
# ---------------------------------------------------------------------------

class TestTradeCRUD:

    def test_add_trade_assigns_id(self, repo):
        t = repo.add_trade(_trade())
        assert t.id is not None
        assert t.id > 0

    def test_get_trade_by_id_roundtrip(self, repo):
        inserted = repo.add_trade(_trade(symbol="NKE", notes="roundtrip"))
        fetched = repo.get_trade_by_id(inserted.id)
        assert fetched is not None
        assert fetched.symbol == "NKE"
        assert fetched.notes == "roundtrip"
        assert fetched.trade_date == date(2026, 1, 10)

    def test_get_trade_by_id_missing_returns_none(self, repo):
        assert repo.get_trade_by_id(9999) is None

    def test_get_trades_ordered_by_date_desc(self, repo):
        repo.add_trade(_trade(trade_date=date(2026, 1, 1)))
        repo.add_trade(_trade(trade_date=date(2026, 3, 1)))
        repo.add_trade(_trade(trade_date=date(2026, 2, 1)))
        trades = repo.get_trades()
        dates = [t.trade_date for t in trades]
        assert dates == sorted(dates, reverse=True)

    def test_update_trade(self, repo):
        t = repo.add_trade(_trade(premium=0.50))
        t.premium = 0.75
        t.status = "CLOSED"
        repo.update_trade(t)
        fetched = repo.get_trade_by_id(t.id)
        assert fetched.premium == 0.75
        assert fetched.status == "CLOSED"

    def test_delete_trade(self, repo):
        t = repo.add_trade(_trade())
        repo.delete_trade(t.id)
        assert repo.get_trade_by_id(t.id) is None

    def test_delete_trade_removes_from_get_trades(self, repo):
        t1 = repo.add_trade(_trade(symbol="SOFI"))
        t2 = repo.add_trade(_trade(symbol="NKE"))
        repo.delete_trade(t1.id)
        ids = [t.id for t in repo.get_trades()]
        assert t1.id not in ids
        assert t2.id in ids

    def test_trade_broker_fee_defaults(self, repo):
        t = _trade(broker_fee=0.0)
        inserted = repo.add_trade(t)
        fetched = repo.get_trade_by_id(inserted.id)
        assert fetched.broker_fee == 0.0

    def test_trade_notes_default_empty(self, repo):
        t = _trade(notes="")
        inserted = repo.add_trade(t)
        fetched = repo.get_trade_by_id(inserted.id)
        assert fetched.notes == ""

    def test_get_trades_chronological(self, repo):
        repo.add_trade(_trade(trade_date=date(2026, 3, 1)))
        repo.add_trade(_trade(trade_date=date(2026, 1, 1)))
        trades = repo.get_trades_chronological()
        dates = [t.trade_date for t in trades]
        assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# Position CRUD
# ---------------------------------------------------------------------------

class TestPositionCRUD:

    def test_upsert_position_insert(self, repo):
        repo.upsert_position(_position())
        positions = repo.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "SOFI"

    def test_upsert_position_update(self, repo):
        repo.upsert_position(_position(premium_collected=50.0))
        repo.upsert_position(_position(premium_collected=100.0))
        positions = repo.get_positions()
        assert len(positions) == 1
        assert positions[0].premium_collected == 100.0

    def test_get_position_by_symbol(self, repo):
        repo.upsert_position(_position(symbol="SOFI", shares=100))
        pos = repo.get_position_by_symbol("SOFI")
        assert pos is not None
        assert pos.shares == 100

    def test_get_position_by_symbol_missing_returns_none(self, repo):
        assert repo.get_position_by_symbol("AAPL") is None

    def test_get_positions_ordered_by_premium_desc(self, repo):
        repo.upsert_position(_position(symbol="SOFI", premium_collected=10.0))
        repo.upsert_position(_position(symbol="NKE", premium_collected=50.0))
        repo.upsert_position(_position(symbol="MSFT", premium_collected=30.0))
        positions = repo.get_positions()
        premiums = [p.premium_collected for p in positions]
        assert premiums == sorted(premiums, reverse=True)

    def test_update_position_status(self, repo):
        repo.upsert_position(_position(status="CSP"))
        repo.update_position_status("SOFI", "COVERED CALLS")
        pos = repo.get_position_by_symbol("SOFI")
        assert pos.status == "COVERED CALLS"

    def test_adjust_position_premium(self, repo):
        repo.upsert_position(_position(premium_collected=100.0))
        repo.adjust_position_premium("SOFI", 25.0)
        pos = repo.get_position_by_symbol("SOFI")
        assert pos.premium_collected == pytest.approx(125.0)

    def test_adjust_position_premium_negative_delta(self, repo):
        repo.upsert_position(_position(premium_collected=100.0))
        repo.adjust_position_premium("SOFI", -20.0)
        pos = repo.get_position_by_symbol("SOFI")
        assert pos.premium_collected == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# Assignment CRUD
# ---------------------------------------------------------------------------

class TestAssignmentCRUD:

    def test_add_assignment_assigns_id(self, repo):
        t = repo.add_trade(_trade(status="ASSIGNED"))
        a = repo.add_assignment(_assignment(t.id))
        assert a.id is not None
        assert a.id > 0

    def test_get_assignments_roundtrip(self, repo):
        t = repo.add_trade(_trade(status="ASSIGNED"))
        repo.add_assignment(_assignment(t.id, notes="put assigned"))
        assignments = repo.get_assignments()
        assert len(assignments) == 1
        a = assignments[0]
        assert a.symbol == "SOFI"
        assert a.assignment_type == "PUT ASSIGNED"
        assert a.notes == "put assigned"
        assert a.assignment_date == date(2026, 2, 21)

    def test_get_assignments_ordered_by_date_desc(self, repo):
        t = repo.add_trade(_trade(status="ASSIGNED"))
        repo.add_assignment(_assignment(t.id, assignment_date=date(2026, 1, 1)))
        repo.add_assignment(_assignment(t.id, assignment_date=date(2026, 3, 1)))
        assignments = repo.get_assignments()
        dates = [a.assignment_date for a in assignments]
        assert dates == sorted(dates, reverse=True)

    def test_assignment_fields_preserved(self, repo):
        t = repo.add_trade(_trade(status="ASSIGNED"))
        a_in = _assignment(
            t.id,
            strike=16.0,
            premium=0.50,
            contracts=2,
            broker_fee=1.05,
            shares=200,
            stock_value=3200.0,
            premium_value=97.95,
            net_stock_basis=3102.05,
        )
        repo.add_assignment(a_in)
        a_out = repo.get_assignments()[0]
        assert a_out.contracts == 2
        assert a_out.shares == 200
        assert a_out.stock_value == pytest.approx(3200.0)
        assert a_out.net_stock_basis == pytest.approx(3102.05)
        assert a_out.broker_fee == pytest.approx(1.05)


# ---------------------------------------------------------------------------
# Covered Call Lifecycle CRUD
# ---------------------------------------------------------------------------

class TestCoveredCallLifecycleCRUD:

    def test_add_lifecycle_assigns_id(self, repo):
        t = repo.add_trade(_trade(strategy="CC"))
        e = repo.add_covered_call_lifecycle(_lifecycle(t.id))
        assert e.id is not None
        assert e.id > 0

    def test_get_lifecycle_roundtrip(self, repo):
        t = repo.add_trade(_trade(strategy="CC"))
        repo.add_covered_call_lifecycle(_lifecycle(t.id, lifecycle_stage="EXPIRED"))
        events = repo.get_covered_call_lifecycle()
        assert len(events) == 1
        e = events[0]
        assert e.symbol == "SOFI"
        assert e.lifecycle_stage == "EXPIRED"
        assert e.cycle_number == 1
        assert e.shares_covered == 100

    def test_get_lifecycle_ordered_by_date_desc(self, repo):
        t = repo.add_trade(_trade(strategy="CC"))
        repo.add_covered_call_lifecycle(_lifecycle(t.id, trade_date=date(2026, 1, 1)))
        repo.add_covered_call_lifecycle(_lifecycle(t.id, trade_date=date(2026, 4, 1)))
        events = repo.get_covered_call_lifecycle()
        dates = [e.trade_date for e in events]
        assert dates == sorted(dates, reverse=True)

    def test_lifecycle_broker_fee_preserved(self, repo):
        t = repo.add_trade(_trade(strategy="CC"))
        repo.add_covered_call_lifecycle(_lifecycle(t.id, broker_fee=2.10))
        e = repo.get_covered_call_lifecycle()[0]
        assert e.broker_fee == pytest.approx(2.10)


# ---------------------------------------------------------------------------
# Position Actions CRUD
# ---------------------------------------------------------------------------

class TestPositionActionCRUD:

    def test_record_action_assigns_id(self, repo):
        a = repo.record_position_action(_position_action())
        assert a.id is not None
        assert a.id > 0

    def test_get_position_actions_roundtrip(self, repo):
        repo.record_position_action(_position_action(action_type="KEEP_SHARES"))
        actions = repo.get_position_actions()
        assert len(actions) == 1
        assert actions[0].action_type == "KEEP_SHARES"

    def test_get_position_actions_filtered_by_symbol(self, repo):
        repo.record_position_action(_position_action(symbol="SOFI"))
        repo.record_position_action(_position_action(symbol="NKE"))
        sofi_actions = repo.get_position_actions(symbol="SOFI")
        assert len(sofi_actions) == 1
        assert sofi_actions[0].symbol == "SOFI"

    def test_get_position_actions_all_when_no_filter(self, repo):
        repo.record_position_action(_position_action(symbol="SOFI"))
        repo.record_position_action(_position_action(symbol="NKE"))
        assert len(repo.get_position_actions()) == 2

    def test_position_action_fields_preserved(self, repo):
        a_in = _position_action(
            previous_status="COVERED CALLS",
            new_status="READY FOR CC",
            adjusted_premium=150.0,
            adjusted_cost_basis=15.50,
            notes="manual keep",
        )
        repo.record_position_action(a_in)
        a_out = repo.get_position_actions()[0]
        assert a_out.previous_status == "COVERED CALLS"
        assert a_out.new_status == "READY FOR CC"
        assert a_out.adjusted_premium == pytest.approx(150.0)
        assert a_out.adjusted_cost_basis == pytest.approx(15.50)
        assert a_out.notes == "manual keep"

    def test_action_date_roundtrip(self, repo):
        dt = datetime(2026, 5, 15, 9, 30, 0)
        repo.record_position_action(_position_action(action_date=dt))
        a_out = repo.get_position_actions()[0]
        assert a_out.action_date == dt


# ---------------------------------------------------------------------------
# Dividend CRUD
# ---------------------------------------------------------------------------

class TestDividendCRUD:

    def test_add_dividend_assigns_id(self, repo):
        d = repo.add_dividend(_dividend())
        assert d.id is not None
        assert d.id > 0

    def test_get_dividends_roundtrip(self, repo):
        repo.add_dividend(_dividend(amount=12.00, shares=100))
        divs = repo.get_dividends()
        assert len(divs) == 1
        assert divs[0].amount == pytest.approx(12.00)
        assert divs[0].shares == 100

    def test_update_dividend(self, repo):
        d = repo.add_dividend(_dividend(amount=12.00))
        d.amount = 15.00
        d.notes = "updated"
        repo.update_dividend(d)
        divs = repo.get_dividends()
        assert divs[0].amount == pytest.approx(15.00)
        assert divs[0].notes == "updated"

    def test_delete_dividend(self, repo):
        d = repo.add_dividend(_dividend())
        repo.delete_dividend(d.id)
        assert len(repo.get_dividends()) == 0

    def test_get_dividends_ordered_by_date_desc(self, repo):
        repo.add_dividend(_dividend(dividend_date=date(2026, 1, 1)))
        repo.add_dividend(_dividend(dividend_date=date(2026, 4, 1)))
        repo.add_dividend(_dividend(dividend_date=date(2026, 2, 15)))
        divs = repo.get_dividends()
        dates = [d.dividend_date for d in divs]
        assert dates == sorted(dates, reverse=True)

    def test_get_dividends_by_symbol(self, repo):
        repo.add_dividend(_dividend(symbol="SOFI"))
        repo.add_dividend(_dividend(symbol="NKE"))
        sofi_divs = repo.get_dividends_by_symbol("SOFI")
        assert len(sofi_divs) == 1
        assert sofi_divs[0].symbol == "SOFI"

    def test_get_dividends_chronological(self, repo):
        repo.add_dividend(_dividend(dividend_date=date(2026, 3, 1)))
        repo.add_dividend(_dividend(dividend_date=date(2026, 1, 1)))
        divs = repo.get_dividends_chronological()
        dates = [d.dividend_date for d in divs]
        assert dates == sorted(dates)

    def test_dividend_broker_fee_preserved(self, repo):
        repo.add_dividend(_dividend(broker_fee=0.50))
        d = repo.get_dividends()[0]
        assert d.broker_fee == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Recalculate positions stub
# ---------------------------------------------------------------------------

class TestRecalculatePositions:
    """recalculate_positions now calls the real engine (wired in Task 5)."""

    def test_clears_and_rebuilds_positions(self, repo):
        repo.upsert_position(_position())
        # No trades — engine produces no positions, so table ends up empty
        repo.recalculate_positions()
        assert repo.get_positions() == []

    def test_rebuilds_assignment_from_trade(self, repo):
        """An ASSIGNED trade causes the engine to re-create the assignment."""
        t = repo.add_trade(_trade(status="ASSIGNED"))
        repo.recalculate_positions()
        assignments = repo.get_assignments()
        assert len(assignments) == 1
        assert assignments[0].trade_id == t.id

    def test_rebuilds_lifecycle_from_cc_trade(self, repo):
        """A CC trade causes the engine to re-create the lifecycle event."""
        # Need a prior CSP assignment so shares > 0 before CC is processed
        repo.add_trade(_trade(strategy="CSP", status="ASSIGNED",
                               trade_date=date(2026, 1, 10),
                               expiration=date(2026, 2, 21)))
        cc = repo.add_trade(_trade(strategy="CC", status="OPEN",
                                    trade_date=date(2026, 3, 1),
                                    expiration=date(2026, 3, 21)))
        repo.recalculate_positions()
        events = repo.get_covered_call_lifecycle()
        assert len(events) == 1
        assert events[0].trade_id == cc.id

    def test_preserves_trades(self, repo):
        repo.add_trade(_trade())
        repo.recalculate_positions()
        assert len(repo.get_trades()) == 1

    def test_preserves_dividends(self, repo):
        repo.add_dividend(_dividend())
        repo.recalculate_positions()
        assert len(repo.get_dividends()) == 1
