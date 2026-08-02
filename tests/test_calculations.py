"""
Unit tests for calculations.py.

Covers:
  - premium_value      §2.1   SELL/BUY sign, scaling, symmetry
  - net_premium_value  §2.2   fee deduction, zero-fee identity
  - total_premium      §2.3   unsigned gross, no fee deduction
  - dte                §2.4   OPEN returns int, all other statuses return None
  - net_dividend       §2.9   fee deduction, zero-fee identity
  - dividend_per_share §2.9   per-share split, invalid-shares guard
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
from constants import SHARES_PER_CONTRACT, TradeAction

SELL = TradeAction.SELL
BUY  = TradeAction.BUY


# ---------------------------------------------------------------------------
# §2.1  premium_value
# ---------------------------------------------------------------------------

class TestPremiumValue:

    @pytest.mark.parametrize("premium, contracts, expected", [
        (0.50, 1,  50.0),
        (0.40, 3, 120.0),
        (1.00, 1, 100.0),
        (1.00, 2, 200.0),
        (0.35, 2,  70.0),
    ])
    def test_sell_positive(self, premium, contracts, expected):
        assert premium_value(premium, contracts, SELL) == pytest.approx(expected)

    @pytest.mark.parametrize("premium, contracts, expected", [
        (0.50, 1,  -50.0),
        (0.40, 3, -120.0),
    ])
    def test_buy_negative(self, premium, contracts, expected):
        assert premium_value(premium, contracts, BUY) == pytest.approx(expected)

    def test_sell_and_buy_are_opposite(self):
        assert premium_value(0.75, 2, SELL) == pytest.approx(-premium_value(0.75, 2, BUY))

    def test_zero_premium_is_zero(self):
        assert premium_value(0.0, 1, SELL) == pytest.approx(0.0)
        assert premium_value(0.0, 1, BUY)  == pytest.approx(0.0)

    def test_scales_by_shares_per_contract(self):
        assert premium_value(1.0, 1, SELL) == pytest.approx(SHARES_PER_CONTRACT)
        assert premium_value(1.0, 3, SELL) == pytest.approx(3 * SHARES_PER_CONTRACT)


# ---------------------------------------------------------------------------
# §2.2  net_premium_value
# ---------------------------------------------------------------------------

class TestNetPremiumValue:

    def test_sell_fee_reduces_income(self):
        # 0.50 × 1 × 100 = 50.00 − 1.05 = 48.95
        assert net_premium_value(0.50, 1, SELL, broker_fee=1.05) == pytest.approx(48.95)

    def test_buy_fee_increases_cost(self):
        # −50.00 − 1.05 = −51.05
        assert net_premium_value(0.50, 1, BUY, broker_fee=1.05) == pytest.approx(-51.05)

    def test_fee_reduces_regardless_of_action(self):
        assert net_premium_value(0.50, 1, SELL, broker_fee=1.05) < premium_value(0.50, 1, SELL)
        assert net_premium_value(0.50, 1, BUY,  broker_fee=1.05) < premium_value(0.50, 1, BUY)

    def test_zero_fee_is_identity(self):
        for action in (SELL, BUY):
            assert net_premium_value(0.50, 1, action, broker_fee=0.0) == pytest.approx(
                premium_value(0.50, 1, action)
            )

    def test_zero_fee_default_is_identity(self):
        assert net_premium_value(0.50, 1, SELL) == pytest.approx(premium_value(0.50, 1, SELL))

    def test_multiple_contracts(self):
        # 0.40 × 3 × 100 = 120.00 − 3.15 = 116.85
        assert net_premium_value(0.40, 3, SELL, broker_fee=3.15) == pytest.approx(116.85)

    def test_fee_larger_than_gross_gives_negative_sell(self):
        # 0.05 × 1 × 100 = 5.00 − 10.00 = −5.00
        assert net_premium_value(0.05, 1, SELL, broker_fee=10.0) == pytest.approx(-5.0)


# ---------------------------------------------------------------------------
# §2.3  total_premium
# ---------------------------------------------------------------------------

class TestTotalPremium:

    @pytest.mark.parametrize("premium, contracts, expected", [
        (0.50, 1,   50.0),
        (0.40, 3,  120.0),
        (0.75, 2,  150.0),
        (0.0,  5,    0.0),
    ])
    def test_gross_value(self, premium, contracts, expected):
        assert total_premium(premium, contracts) == pytest.approx(expected)

    def test_always_non_negative(self):
        assert total_premium(0.50, 1) >= 0
        assert total_premium(0.0,  1) >= 0

    def test_equals_sell_premium_value(self):
        assert total_premium(0.50, 2) == pytest.approx(premium_value(0.50, 2, SELL))

    def test_no_fee_deduction(self):
        # total_premium is gross — fees must not affect it
        assert total_premium(0.50, 1) == pytest.approx(0.50 * 1 * SHARES_PER_CONTRACT)


# ---------------------------------------------------------------------------
# §2.4  dte
# ---------------------------------------------------------------------------

class TestDte:

    def test_open_returns_correct_days(self):
        assert dte(date(2026, 2, 21), "OPEN", today=date(2026, 1, 10)) == 42

    def test_open_same_day_is_zero(self):
        assert dte(date(2026, 2, 21), "OPEN", today=date(2026, 2, 21)) == 0

    def test_open_past_expiry_is_negative(self):
        assert dte(date(2026, 2, 21), "OPEN", today=date(2026, 3, 1)) == -8

    def test_open_30_days(self):
        assert dte(date(2026, 1, 31), "OPEN", today=date(2026, 1, 1)) == 30

    @pytest.mark.parametrize("status", ["CLOSED", "EXPIRED", "ASSIGNED"])
    def test_non_open_returns_none(self, status):
        assert dte(date(2026, 2, 21), status, today=date(2026, 1, 10)) is None

    @pytest.mark.parametrize("status", ["CLOSED", "EXPIRED", "ASSIGNED"])
    def test_non_open_ignores_future_expiry(self, status):
        assert dte(date(2099, 1, 1), status, today=date(2026, 1, 1)) is None

    def test_defaults_to_today(self):
        result = dte(date(2099, 12, 31), "OPEN")
        assert isinstance(result, int)
        assert result > 0


# ---------------------------------------------------------------------------
# §2.9  net_dividend
# ---------------------------------------------------------------------------

class TestNetDividend:

    def test_zero_fee_returns_amount(self):
        assert net_dividend(12.00) == pytest.approx(12.00)
        assert net_dividend(12.00, broker_fee=0.0) == pytest.approx(12.00)

    def test_fee_reduces_net(self):
        assert net_dividend(12.00, broker_fee=0.50) == pytest.approx(11.50)

    def test_zero_amount(self):
        assert net_dividend(0.0) == pytest.approx(0.0)

    def test_fee_equals_amount_is_zero(self):
        assert net_dividend(5.00, broker_fee=5.00) == pytest.approx(0.0)

    def test_fee_exceeds_amount_is_negative(self):
        assert net_dividend(1.00, broker_fee=2.00) == pytest.approx(-1.00)


# ---------------------------------------------------------------------------
# §2.9  dividend_per_share
# ---------------------------------------------------------------------------

class TestDividendPerShare:

    def test_basic(self):
        # 12.00 / 100 shares = 0.12 per share
        assert dividend_per_share(12.00, 100) == pytest.approx(0.12)

    def test_with_fee(self):
        # (12.00 − 0.50) / 100 = 0.115 per share
        assert dividend_per_share(12.00, 100, broker_fee=0.50) == pytest.approx(0.115)

    def test_single_share(self):
        assert dividend_per_share(5.00, 1) == pytest.approx(5.00)

    def test_matches_net_dividend_divided_by_shares(self):
        nd  = net_dividend(20.00, broker_fee=1.00)
        dps = dividend_per_share(20.00, 50, broker_fee=1.00)
        assert dps == pytest.approx(nd / 50)

    @pytest.mark.parametrize("shares", [0, -1, -100])
    def test_invalid_shares_raises(self, shares):
        with pytest.raises(ValueError):
            dividend_per_share(10.00, shares)
