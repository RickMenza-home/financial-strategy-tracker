"""
Shared pure-math functions for the Financial Strategy Tracker.

All functions are stateless and side-effect-free.
No database access, no Streamlit, no strategy-specific logic.

Sign convention (§2.1 / §2.2):
  - SELL trades produce positive cashflow (income received)
  - BUY  trades produce negative cashflow (cost paid to close)
  - broker_fee is always positive and always reduces net income
"""

from __future__ import annotations

from datetime import date

from constants import SHARES_PER_CONTRACT, TradeAction


# ---------------------------------------------------------------------------
# §2.1  Gross premium cashflow
# ---------------------------------------------------------------------------

def premium_value(premium: float, contracts: int, action: TradeAction) -> float:
    """
    Gross premium cashflow for a single trade (before fees).

        premium_value = premium × contracts × SHARES_PER_CONTRACT

    Sign:
        TradeAction.SELL → positive (income)
        TradeAction.BUY  → negative (expense)

    Args:
        premium:   Per-share premium price (>= 0).
        contracts: Number of contracts (>= 1).
        action:    TradeAction.SELL or TradeAction.BUY.

    Returns:
        Signed gross cashflow in dollars.
    """
    gross = total_premium(premium, contracts)
    return gross if action == TradeAction.SELL else -gross


# ---------------------------------------------------------------------------
# §2.2  Net premium cashflow (fee-adjusted)
# ---------------------------------------------------------------------------

def net_premium_value(premium: float, contracts: int, action: TradeAction,
                      broker_fee: float = 0.0) -> float:
    """
    Net cashflow after subtracting the broker fee.

        net_premium_value = premium_value(premium, contracts, action) - broker_fee

    broker_fee is always positive and always reduces net income regardless of
    trade direction (fees are a cost on both buys and sells).

    Args:
        premium:    Per-share premium price (>= 0).
        contracts:  Number of contracts (>= 1).
        action:     TradeAction.SELL or TradeAction.BUY.
        broker_fee: Total commission paid (>= 0, default 0.0).

    Returns:
        Signed net cashflow in dollars.
    """
    return premium_value(premium, contracts, action) - broker_fee


# ---------------------------------------------------------------------------
# §2.3  Total premium (display / gross, unsigned)
# ---------------------------------------------------------------------------

def total_premium(premium: float, contracts: int) -> float:
    """
    Gross premium value used for display in trade lists (always positive).

        total_premium = premium × contracts × SHARES_PER_CONTRACT

    This is the unsigned gross value, never fee-adjusted.  Use
    net_premium_value() wherever actual P&L is computed.

    Args:
        premium:   Per-share premium price (>= 0).
        contracts: Number of contracts (>= 1).

    Returns:
        Gross premium in dollars (always >= 0).
    """
    return premium * contracts * SHARES_PER_CONTRACT


# ---------------------------------------------------------------------------
# §2.4  Days to Expiration
# ---------------------------------------------------------------------------

def dte(expiration: date, status: str, today: date | None = None) -> int | None:
    """
    Days remaining until the option expires.

        dte = (expiration - today).days

    Only meaningful for trades with status == "OPEN".  Returns None for all
    other statuses so callers can render a blank cell.

    Args:
        expiration: The option expiration date.
        status:     The trade status string (e.g. "OPEN", "CLOSED", "EXPIRED").
        today:      Reference date; defaults to date.today() when None.

    Returns:
        Integer days remaining, or None if status != "OPEN".
    """
    if status != "OPEN":
        return None
    ref = today if today is not None else date.today()
    return (expiration - ref).days


# ---------------------------------------------------------------------------
# §2.9  Dividend calculations
# ---------------------------------------------------------------------------

def net_dividend(amount: float, broker_fee: float = 0.0) -> float:
    """
    Net dividend cashflow after subtracting the broker fee.

        net_dividend = amount - broker_fee

    Args:
        amount:     Gross dividend received (>= 0).
        broker_fee: Any fee deducted by broker (>= 0, default 0.0).

    Returns:
        Net dividend in dollars.
    """
    return amount - broker_fee


def dividend_per_share(amount: float, shares: int,
                       broker_fee: float = 0.0) -> float:
    """
    Net dividend per share.

        dividend_per_share = net_dividend(amount, broker_fee) / shares

    This is the amount by which cost_basis_per_share is reduced on each
    dividend receipt.

    Args:
        amount:     Gross dividend received (>= 0).
        shares:     Number of shares held at dividend date (>= 1).
        broker_fee: Any fee deducted by broker (>= 0, default 0.0).

    Returns:
        Net dividend per share in dollars.

    Raises:
        ValueError: If shares <= 0.
    """
    if shares <= 0:
        raise ValueError(f"shares must be >= 1, got {shares}")
    return net_dividend(amount, broker_fee) / shares
