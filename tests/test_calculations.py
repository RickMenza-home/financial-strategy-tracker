"""
Unit tests for calculations.py.

Covers:
  - premium_value:     SELL vs BUY sign, zero premium, zero contracts
  - net_premium_value: fee-adjusted net for SELL and BUY, zero fee
  - total_premium:     always positive gross, independent of action
  - dte:               OPEN trades, non-OPEN statuses, past expiry, same-day, custom today
  - net_dividend:      fee-adjusted, zero fee
  - dividend_per_share: correct per-share value, zero fee, invalid shares guard
"""

import pytest
from datetime import date

from calculations import (
    dividend_per_share,
    dte,
    net_dividend,
    net_premium_value,
    premium_value,
    total_premium,
)
from constants import TradeAction


# ---------------------------------------------------------------------------
# premium_value — §2.1
# ---------------------------------------------------------------------------

class TestPremiumValue:

    def test_sell_is_positive(self):
        assert premium_value(0.50, 1, TradeAction.SELL) == pytest.approx(50.0)

    def test_buy_is_negative(self):
        assert premium_value(0.50, 1, TradeAction.BUY) == pytest.approx(-50.0)

    def test_sell_multiple_contracts(self):
        assert premium_value(0.40, 3, TradeAction.SELL) == pytest.approx(120.0)

    def test_buy_multiple_contracts(self):
        assert premium_value(0.40, 3, TradeAction.BUY) == pytest.approx(-120.0)

    def test_zero_premium_sell(self):
        assert premium_value(0.0, 1, TradeAction.SELL) == pytest.approx(0.0)

    def test_zero_premium_buy(self):
        assert premium_value(0.0, 1, TradeAction.BUY) == pytest.approx(0.0)

    def test_multiplied_by_100_per_contract(self):
        # 1 contract = 100 shares
        assert premium_value(1.00, 1, TradeAction.SELL) == pytest.approx(100.0)
        assert premium_value(1.00, 2, TradeAction.SELL) == pytest.approx(200.0)

    def test_fractional_premium(self):
        assert premium_value(0.35, 2, TradeAction.SELL) == pytest.approx(70.0)

    def test_sell_and_buy_are_opposite(self):
        sell = premium_value(0.75, 2, TradeAction.SELL)
        buy  = premium_value(0.75, 2, TradeAction.BUY)
        assert sell == pytest.approx(-buy)


# ---------------------------------------------------------------------------
# net_premium_value — §2.2
# ---------------------------------------------------------------------------

class TestNetPremiumValue:

    def test_sell_with_fee_reduces_income(self):
        # gross = 50.0, fee = 1.05  →  net = 48.95
        assert net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05) == pytest.approx(48.95)

    def test_buy_with_fee_increases_cost(self):
        # gross = -50.0, fee = 1.05  →  net = -51.05
        assert net_premium_value(0.50, 1, TradeAction.BUY, broker_fee=1.05) == pytest.approx(-51.05)

    def test_zero_fee_equals_premium_value(self):
        assert net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=0.0) == pytest.approx(
            premium_value(0.50, 1, TradeAction.SELL)
        )

    def test_zero_fee_default_equals_premium_value(self):
        assert net_premium_value(0.50, 1, TradeAction.SELL) == pytest.approx(
            premium_value(0.50, 1, TradeAction.SELL)
        )

    def test_fee_always_reduces_regardless_of_action(self):
        net_sell = net_premium_value(0.50, 1, TradeAction.SELL, broker_fee=1.05)
        net_buy  = net_premium_value(0.50, 1, TradeAction.BUY,  broker_fee=1.05)
        gross_sell = premium_value(0.50, 1, TradeAction.SELL)
        gross_buy  = premium_value(0.50, 1, TradeAction.BUY)
        assert net_sell < gross_sell   # less income after fee
        assert net_buy  < gross_buy    # more cost after fee (more negative)

    def test_multiple_contracts_with_fee(self):
        # gross = 0.40 × 3 × 100 = 120.0, fee = 3.15  →  net = 116.85
        assert net_premium_value(0.40, 3, TradeAction.SELL, broker_fee=3.15) == pytest.approx(116.85)

    def test_large_fee_can_produce_negative_sell_net(self):
        # edge: fee exceeds premium income
        assert net_premium_value(0.05, 1, TradeAction.SELL, broker_fee=10.0) == pytest.approx(-5.0)


# ---------------------------------------------------------------------------
# total_premium — §2.3
# ---------------------------------------------------------------------------

class TestTotalPremium:

    def test_always_positive(self):
        assert total_premium(0.50, 1) > 0

    def test_same_as_sell_gross(self):
        assert total_premium(0.50, 2) == pytest.approx(premium_value(0.50, 2, TradeAction.SELL))

    def test_no_fee_deduction(self):
        assert total_premium(0.50, 1) == pytest.approx(50.0)

    def test_multiple_contracts(self):
        assert total_premium(0.40, 3) == pytest.approx(120.0)

    def test_zero_premium(self):
        assert total_premium(0.0, 5) == pytest.approx(0.0)

    def test_is_always_unsigned(self):
        # total_premium has no concept of action — it is always gross positive
        tp = total_premium(0.75, 2)
        assert tp == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# dte — §2.4
# ---------------------------------------------------------------------------

class TestDte:

    def test_open_trade_returns_days(self):
        today = date(2026, 1, 10)
        expiry = date(2026, 2, 21)
        assert dte(expiry, "OPEN", today=today) == 42

    def test_closed_returns_none(self):
        assert dte(date(2026, 2, 21), "CLOSED", today=date(2026, 1, 10)) is None

    def test_expired_returns_none(self):
        assert dte(date(2026, 2, 21), "EXPIRED", today=date(2026, 2, 21)) is None

    def test_assigned_returns_none(self):
        assert dte(date(2026, 2, 21), "ASSIGNED", today=date(2026, 1, 10)) is None

    def test_same_day_expiry_open_is_zero(self):
        today = date(2026, 2, 21)
        assert dte(today, "OPEN", today=today) == 0

    def test_past_expiry_open_is_negative(self):
        today = date(2026, 3, 1)
        expiry = date(2026, 2, 21)
        assert dte(expiry, "OPEN", today=today) == -8

    def test_uses_date_today_when_no_today_arg(self):
        # Just confirm it runs without error and returns an int for OPEN
        result = dte(date(2099, 12, 31), "OPEN")
        assert isinstance(result, int)

    def test_non_open_ignores_expiry_date(self):
        # Even if expiry is in the future, non-OPEN returns None
        far_future = date(2099, 1, 1)
        for status in ("CLOSED", "EXPIRED", "ASSIGNED"):
            assert dte(far_future, status, today=date(2026, 1, 1)) is None

    def test_open_30_days_out(self):
        today = date(2026, 1, 1)
        expiry = date(2026, 1, 31)
        assert dte(expiry, "OPEN", today=today) == 30


# ---------------------------------------------------------------------------
# net_dividend — §2.9
# ---------------------------------------------------------------------------

class TestNetDividend:

    def test_no_fee(self):
        assert net_dividend(12.00) == pytest.approx(12.00)

    def test_zero_fee_explicit(self):
        assert net_dividend(12.00, broker_fee=0.0) == pytest.approx(12.00)

    def test_with_fee(self):
        assert net_dividend(12.00, broker_fee=0.50) == pytest.approx(11.50)

    def test_zero_amount(self):
        assert net_dividend(0.0, broker_fee=0.0) == pytest.approx(0.0)

    def test_fee_equals_amount_gives_zero(self):
        assert net_dividend(5.00, broker_fee=5.00) == pytest.approx(0.0)

    def test_fee_exceeds_amount_gives_negative(self):
        # Unusual but not guarded — caller's responsibility
        assert net_dividend(1.00, broker_fee=2.00) == pytest.approx(-1.00)


# ---------------------------------------------------------------------------
# dividend_per_share — §2.9
# ---------------------------------------------------------------------------

class TestDividendPerShare:

    def test_basic(self):
        # net = 12.00, shares = 100  →  0.12 / share
        assert dividend_per_share(12.00, 100) == pytest.approx(0.12)

    def test_with_fee(self):
        # net = 12.00 - 0.50 = 11.50, shares = 100  →  0.115 / share
        assert dividend_per_share(12.00, 100, broker_fee=0.50) == pytest.approx(0.115)

    def test_zero_fee(self):
        assert dividend_per_share(50.00, 200) == pytest.approx(0.25)

    def test_single_share(self):
        assert dividend_per_share(5.00, 1) == pytest.approx(5.00)

    def test_fractional_result(self):
        assert dividend_per_share(10.00, 3) == pytest.approx(10.00 / 3)

    def test_zero_shares_raises(self):
        with pytest.raises(ValueError):
            dividend_per_share(10.00, 0)

    def test_negative_shares_raises(self):
        with pytest.raises(ValueError):
            dividend_per_share(10.00, -5)

    def test_matches_net_dividend_divided_by_shares(self):
        nd = net_dividend(20.00, broker_fee=1.00)
        dps = dividend_per_share(20.00, 50, broker_fee=1.00)
        assert dps == pytest.approx(nd / 50)
