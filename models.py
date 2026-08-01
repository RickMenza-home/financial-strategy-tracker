"""
Data model dataclasses for the Financial Strategy Tracker.

All classes are pure data containers — no business logic, no imports beyond stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


# ---------------------------------------------------------------------------
# Core trade record
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    """A single options trade entered by the user (§1.1)."""

    id: int | None          # Primary key; None before insertion
    strategy_type: str      # Plugin identifier, e.g. "wheel"
    symbol: str             # Uppercase ticker, e.g. "SOFI"
    strategy: str           # Trade sub-type within the strategy, e.g. "CSP", "CC"
    action: str             # "SELL" or "BUY"
    trade_date: date        # ISO 8601
    expiration: date        # ISO 8601, must be >= trade_date
    strike: float           # > 0
    premium: float          # >= 0, per-share price
    contracts: int          # >= 1
    broker_fee: float       # >= 0, total commission/fee paid. Defaults to 0.0
    status: str             # "OPEN", "CLOSED", "ASSIGNED", "EXPIRED"
    notes: str = ""         # Free text


# ---------------------------------------------------------------------------
# Derived position (one per symbol × strategy_type)
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """
    Current position for a (symbol, strategy_type) pair, fully derived from
    trades by the recalculation engine (§1.2).
    """

    symbol: str
    strategy_type: str
    shares: int
    cost_basis: float           # Per-share cost basis
    premium_collected: float    # Running net premium (fee-adjusted)
    total_fees_paid: float      # Cumulative broker fees across all trades
    dividends_collected: float  # Total net dividends received
    status: str                 # Strategy-defined status, e.g. "CSP", "CC OPEN"


# ---------------------------------------------------------------------------
# Assignment event (one per assignment)
# ---------------------------------------------------------------------------

@dataclass
class Assignment:
    """
    An event created when a trade reaches ASSIGNED status (§1.3).
    Covers both PUT ASSIGNED (CSP → shares acquired) and
    CALL ASSIGNED (CC → shares called away).
    """

    id: int | None              # Primary key; None before insertion
    trade_id: int               # FK → trades.id
    symbol: str
    assignment_date: date       # Expiration date of the assigned option
    strategy: str               # "CSP" or "CC"
    assignment_type: str        # "PUT ASSIGNED" or "CALL ASSIGNED"
    strike: float
    premium: float              # Per-share premium of the original trade
    contracts: int
    broker_fee: float           # Broker fee paid for the original trade
    shares: int                 # Positive for PUT ASSIGNED, negative for CALL ASSIGNED
    stock_value: float          # strike × abs(shares)
    premium_value: float        # Net premium cashflow of the trade
    net_stock_basis: float      # See §2.5 / §2.6
    notes: str = ""


# ---------------------------------------------------------------------------
# Covered call lifecycle event (one per CC trade)
# ---------------------------------------------------------------------------

@dataclass
class CoveredCallLifecycle:
    """
    Tracks the lifecycle of each covered call trade (§1.4).
    One record is created per CC trade during recalculation.
    """

    id: int | None              # Primary key; None before insertion
    trade_id: int               # FK → trades.id
    symbol: str
    cycle_number: int           # Incremented each time a PUT is assigned
    trade_date: date
    expiration: date
    action: str                 # "SELL" or "BUY"
    lifecycle_stage: str        # "OPEN", "CLOSED", "EXPIRED", "CALLED AWAY"
    strike: float
    premium: float
    contracts: int
    broker_fee: float           # Broker fee paid for this CC trade
    shares_covered: int         # contracts × 100
    premium_value: float        # Net premium cashflow of the trade
    notes: str = ""


# ---------------------------------------------------------------------------
# Position action (manual user action on a position)
# ---------------------------------------------------------------------------

@dataclass
class PositionAction:
    """
    A manual action recorded by the user on a position (§1.5).
    Examples: CLOSE_CSP, KEEP_SHARES, SELL_CC, ADJUST_PREMIUM.
    """

    id: int | None              # Primary key; None before insertion
    strategy_type: str          # Plugin identifier
    symbol: str
    action_date: datetime       # When the action was recorded
    action_type: str            # Strategy-defined action type string
    previous_status: str        # Position status before the action
    new_status: str             # Position status after the action
    adjusted_premium: float     # New total premium after adjustment
    adjusted_cost_basis: float  # New cost basis after adjustment
    notes: str = ""


# ---------------------------------------------------------------------------
# Dividend record
# ---------------------------------------------------------------------------

@dataclass
class Dividend:
    """
    A dividend payment received while holding shares (§1.6).
    Replayed by the recalculation engine alongside trades.
    """

    id: int | None              # Primary key; None before insertion
    strategy_type: str          # Plugin identifier, e.g. "wheel"
    symbol: str                 # Uppercase ticker
    dividend_date: date         # Date the dividend was received
    amount: float               # Total cash received (gross, before fees). >= 0
    shares: int                 # Number of shares held at dividend date. >= 1
    broker_fee: float           # Any fee deducted by broker. Defaults to 0.0
    notes: str = ""


# ---------------------------------------------------------------------------
# Plugin result (returned by each strategy plugin's process_trade)
# ---------------------------------------------------------------------------

@dataclass
class PluginResult:
    """
    The value returned by a strategy plugin after processing one trade (§3.0).

    Attributes:
        state:            Updated position state dict for the symbol.
        assignments:      New Assignment events to persist (may be empty).
        lifecycle_events: Strategy-specific lifecycle rows to persist (may be empty).
                          For the wheel strategy these are CoveredCallLifecycle objects.
    """

    state: dict
    assignments: list[Assignment] = field(default_factory=list)
    lifecycle_events: list[Any] = field(default_factory=list)
