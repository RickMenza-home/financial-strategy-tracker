"""
Repository layer — all database access for the application.

Responsibility: translate between Python dataclasses and SQLite rows.
No business logic or calculation lives here.

May import: config, models, database.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Callable

from config import DB_NAME
from database import get_connection, init_db, _get_schema
from models import (
    Assignment,
    CoveredCallLifecycle,
    Dividend,
    Position,
    PositionAction,
    Trade,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _row_to_trade(row) -> Trade:
    return Trade(
        id=row["id"],
        strategy_type=row["strategy_type"],
        symbol=row["symbol"],
        strategy=row["strategy"],
        action=row["action"],
        trade_date=_date(row["trade_date"]),
        expiration=_date(row["expiration"]),
        strike=row["strike"],
        premium=row["premium"],
        contracts=row["contracts"],
        broker_fee=row["broker_fee"],
        status=row["status"],
        notes=row["notes"] or "",
    )


def _row_to_position(row) -> Position:
    return Position(
        symbol=row["symbol"],
        strategy_type=row["strategy_type"],
        shares=row["shares"],
        cost_basis=row["cost_basis"],
        premium_collected=row["premium_collected"],
        total_fees_paid=row["total_fees_paid"],
        dividends_collected=row["dividends_collected"],
        status=row["status"],
    )


def _row_to_assignment(row) -> Assignment:
    return Assignment(
        id=row["id"],
        trade_id=row["trade_id"],
        symbol=row["symbol"],
        assignment_date=_date(row["assignment_date"]),
        strategy=row["strategy"],
        assignment_type=row["assignment_type"],
        strike=row["strike"],
        premium=row["premium"],
        contracts=row["contracts"],
        broker_fee=row["broker_fee"],
        shares=row["shares"],
        stock_value=row["stock_value"],
        premium_value=row["premium_value"],
        net_stock_basis=row["net_stock_basis"],
        notes=row["notes"] or "",
    )


def _row_to_lifecycle(row) -> CoveredCallLifecycle:
    return CoveredCallLifecycle(
        id=row["id"],
        trade_id=row["trade_id"],
        symbol=row["symbol"],
        cycle_number=row["cycle_number"],
        trade_date=_date(row["trade_date"]),
        expiration=_date(row["expiration"]),
        action=row["action"],
        lifecycle_stage=row["lifecycle_stage"],
        strike=row["strike"],
        premium=row["premium"],
        contracts=row["contracts"],
        broker_fee=row["broker_fee"],
        shares_covered=row["shares_covered"],
        premium_value=row["premium_value"],
        notes=row["notes"] or "",
    )


def _row_to_position_action(row) -> PositionAction:
    return PositionAction(
        id=row["id"],
        strategy_type=row["strategy_type"],
        symbol=row["symbol"],
        action_date=_datetime(row["action_date"]),
        action_type=row["action_type"],
        previous_status=row["previous_status"],
        new_status=row["new_status"],
        adjusted_premium=row["adjusted_premium"],
        adjusted_cost_basis=row["adjusted_cost_basis"],
        notes=row["notes"] or "",
    )


def _row_to_dividend(row) -> Dividend:
    return Dividend(
        id=row["id"],
        strategy_type=row["strategy_type"],
        symbol=row["symbol"],
        dividend_date=_date(row["dividend_date"]),
        amount=row["amount"],
        shares=row["shares"],
        broker_fee=row["broker_fee"],
        notes=row["notes"] or "",
    )


# ---------------------------------------------------------------------------
# Repository class
# ---------------------------------------------------------------------------

class Repository:
    """
    Provides all data-access operations for the application.

    Pass ``db_path=":memory:"`` (as a Path or string) for in-memory databases
    used in tests.  An in-memory repository reuses a single connection so that
    all operations share the same database instance (each new sqlite3 connection
    to ":memory:" is a completely separate, empty database).
    """

    def __init__(self, db_path: Path | str = DB_NAME) -> None:
        self._db_path = db_path
        # For in-memory databases, keep one persistent connection so all
        # operations share the same schema and data.
        if str(db_path) == ":memory:":
            self._shared_conn = get_connection(db_path)
            with self._shared_conn:
                self._shared_conn.executescript(_get_schema())
        else:
            self._shared_conn = None
            init_db(db_path)

    def _conn(self):
        if self._shared_conn is not None:
            return self._shared_conn
        return get_connection(self._db_path)

    def _release(self, conn) -> None:
        """Close the connection unless it is the shared in-memory connection."""
        if conn is not self._shared_conn:
            self._release(conn)

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def add_trade(self, trade: Trade) -> Trade:
        """Insert a new trade and return it with its assigned id."""
        sql = """
            INSERT INTO trades
                (strategy_type, symbol, strategy, action, trade_date, expiration,
                 strike, premium, contracts, broker_fee, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn = self._conn()
        with conn:
            cur = conn.execute(sql, (
                trade.strategy_type,
                trade.symbol,
                trade.strategy,
                trade.action,
                str(trade.trade_date),
                str(trade.expiration),
                trade.strike,
                trade.premium,
                trade.contracts,
                trade.broker_fee,
                trade.status,
                trade.notes,
            ))
            trade.id = cur.lastrowid
        self._release(conn)
        return trade

    def update_trade(self, trade: Trade) -> None:
        """Update all fields of an existing trade by id."""
        sql = """
            UPDATE trades SET
                strategy_type = ?,
                symbol        = ?,
                strategy      = ?,
                action        = ?,
                trade_date    = ?,
                expiration    = ?,
                strike        = ?,
                premium       = ?,
                contracts     = ?,
                broker_fee    = ?,
                status        = ?,
                notes         = ?
            WHERE id = ?
        """
        conn = self._conn()
        with conn:
            conn.execute(sql, (
                trade.strategy_type,
                trade.symbol,
                trade.strategy,
                trade.action,
                str(trade.trade_date),
                str(trade.expiration),
                trade.strike,
                trade.premium,
                trade.contracts,
                trade.broker_fee,
                trade.status,
                trade.notes,
                trade.id,
            ))
        self._release(conn)

    def delete_trade(self, trade_id: int) -> None:
        """Delete a trade by id."""
        conn = self._conn()
        with conn:
            conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        self._release(conn)

    def get_trades(self) -> list[Trade]:
        """Return all trades ordered by trade_date DESC."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY trade_date DESC"
        ).fetchall()
        self._release(conn)
        return [_row_to_trade(r) for r in rows]

    def get_trade_by_id(self, trade_id: int) -> Trade | None:
        """Return a single trade by id, or None if not found."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        self._release(conn)
        return _row_to_trade(row) if row else None

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self) -> list[Position]:
        """Return all positions ordered by premium_collected DESC."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM positions ORDER BY premium_collected DESC"
        ).fetchall()
        self._release(conn)
        return [_row_to_position(r) for r in rows]

    def get_position_by_symbol(self, symbol: str, strategy_type: str = "wheel") -> Position | None:
        """Return a single position by (symbol, strategy_type), or None."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM positions WHERE symbol = ? AND strategy_type = ?",
            (symbol, strategy_type),
        ).fetchone()
        self._release(conn)
        return _row_to_position(row) if row else None

    def upsert_position(self, position: Position) -> None:
        """Insert or replace a position record (used by the engine)."""
        sql = """
            INSERT INTO positions
                (symbol, strategy_type, shares, cost_basis, premium_collected,
                 total_fees_paid, dividends_collected, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, strategy_type) DO UPDATE SET
                shares              = excluded.shares,
                cost_basis          = excluded.cost_basis,
                premium_collected   = excluded.premium_collected,
                total_fees_paid     = excluded.total_fees_paid,
                dividends_collected = excluded.dividends_collected,
                status              = excluded.status
        """
        conn = self._conn()
        with conn:
            conn.execute(sql, (
                position.symbol,
                position.strategy_type,
                position.shares,
                position.cost_basis,
                position.premium_collected,
                position.total_fees_paid,
                position.dividends_collected,
                position.status,
            ))
        self._release(conn)

    def update_position_status(self, symbol: str, new_status: str,
                                strategy_type: str = "wheel") -> None:
        """Update the status field on a position."""
        conn = self._conn()
        with conn:
            conn.execute(
                "UPDATE positions SET status = ? WHERE symbol = ? AND strategy_type = ?",
                (new_status, symbol, strategy_type),
            )
        self._release(conn)

    def adjust_position_premium(self, symbol: str, delta: float,
                                 strategy_type: str = "wheel") -> None:
        """Add delta to premium_collected and recalculate cost_basis accordingly."""
        conn = self._conn()
        with conn:
            conn.execute(
                """
                UPDATE positions
                SET premium_collected = premium_collected + ?
                WHERE symbol = ? AND strategy_type = ?
                """,
                (delta, symbol, strategy_type),
            )
        self._release(conn)

    # ------------------------------------------------------------------
    # Assignments
    # ------------------------------------------------------------------

    def get_assignments(self) -> list[Assignment]:
        """Return all assignments ordered by assignment_date DESC."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM assignments ORDER BY assignment_date DESC"
        ).fetchall()
        self._release(conn)
        return [_row_to_assignment(r) for r in rows]

    def add_assignment(self, assignment: Assignment) -> Assignment:
        """Insert an assignment record and return it with its assigned id."""
        sql = """
            INSERT INTO assignments
                (trade_id, symbol, assignment_date, strategy, assignment_type,
                 strike, premium, contracts, broker_fee, shares, stock_value,
                 premium_value, net_stock_basis, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn = self._conn()
        with conn:
            cur = conn.execute(sql, (
                assignment.trade_id,
                assignment.symbol,
                str(assignment.assignment_date),
                assignment.strategy,
                assignment.assignment_type,
                assignment.strike,
                assignment.premium,
                assignment.contracts,
                assignment.broker_fee,
                assignment.shares,
                assignment.stock_value,
                assignment.premium_value,
                assignment.net_stock_basis,
                assignment.notes,
            ))
            assignment.id = cur.lastrowid
        self._release(conn)
        return assignment

    # ------------------------------------------------------------------
    # Covered Call Lifecycle
    # ------------------------------------------------------------------

    def get_covered_call_lifecycle(self) -> list[CoveredCallLifecycle]:
        """Return all CC lifecycle events ordered by trade_date DESC."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM covered_call_lifecycle ORDER BY trade_date DESC"
        ).fetchall()
        self._release(conn)
        return [_row_to_lifecycle(r) for r in rows]

    def add_covered_call_lifecycle(self, event: CoveredCallLifecycle) -> CoveredCallLifecycle:
        """Insert a CC lifecycle event and return it with its assigned id."""
        sql = """
            INSERT INTO covered_call_lifecycle
                (trade_id, symbol, cycle_number, trade_date, expiration, action,
                 lifecycle_stage, strike, premium, contracts, broker_fee,
                 shares_covered, premium_value, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn = self._conn()
        with conn:
            cur = conn.execute(sql, (
                event.trade_id,
                event.symbol,
                event.cycle_number,
                str(event.trade_date),
                str(event.expiration),
                event.action,
                event.lifecycle_stage,
                event.strike,
                event.premium,
                event.contracts,
                event.broker_fee,
                event.shares_covered,
                event.premium_value,
                event.notes,
            ))
            event.id = cur.lastrowid
        self._release(conn)
        return event

    # ------------------------------------------------------------------
    # Position Actions
    # ------------------------------------------------------------------

    def get_position_actions(self, symbol: str | None = None) -> list[PositionAction]:
        """Return all position actions, optionally filtered by symbol."""
        conn = self._conn()
        if symbol:
            rows = conn.execute(
                "SELECT * FROM position_actions WHERE symbol = ? ORDER BY action_date DESC",
                (symbol,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM position_actions ORDER BY action_date DESC"
            ).fetchall()
        self._release(conn)
        return [_row_to_position_action(r) for r in rows]

    def record_position_action(self, action: PositionAction) -> PositionAction:
        """Insert a position action record and return it with its assigned id."""
        sql = """
            INSERT INTO position_actions
                (strategy_type, symbol, action_date, action_type, previous_status,
                 new_status, adjusted_premium, adjusted_cost_basis, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn = self._conn()
        with conn:
            cur = conn.execute(sql, (
                action.strategy_type,
                action.symbol,
                str(action.action_date),
                action.action_type,
                action.previous_status,
                action.new_status,
                action.adjusted_premium,
                action.adjusted_cost_basis,
                action.notes,
            ))
            action.id = cur.lastrowid
        self._release(conn)
        return action

    # ------------------------------------------------------------------
    # Dividends
    # ------------------------------------------------------------------

    def add_dividend(self, dividend: Dividend) -> Dividend:
        """Insert a new dividend record and return it with its assigned id."""
        sql = """
            INSERT INTO dividends
                (strategy_type, symbol, dividend_date, amount, shares, broker_fee, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        conn = self._conn()
        with conn:
            cur = conn.execute(sql, (
                dividend.strategy_type,
                dividend.symbol,
                str(dividend.dividend_date),
                dividend.amount,
                dividend.shares,
                dividend.broker_fee,
                dividend.notes,
            ))
            dividend.id = cur.lastrowid
        self._release(conn)
        return dividend

    def update_dividend(self, dividend: Dividend) -> None:
        """Update all fields of an existing dividend by id."""
        sql = """
            UPDATE dividends SET
                strategy_type = ?,
                symbol        = ?,
                dividend_date = ?,
                amount        = ?,
                shares        = ?,
                broker_fee    = ?,
                notes         = ?
            WHERE id = ?
        """
        conn = self._conn()
        with conn:
            conn.execute(sql, (
                dividend.strategy_type,
                dividend.symbol,
                str(dividend.dividend_date),
                dividend.amount,
                dividend.shares,
                dividend.broker_fee,
                dividend.notes,
                dividend.id,
            ))
        self._release(conn)

    def delete_dividend(self, dividend_id: int) -> None:
        """Delete a dividend by id."""
        conn = self._conn()
        with conn:
            conn.execute("DELETE FROM dividends WHERE id = ?", (dividend_id,))
        self._release(conn)

    def get_dividends(self) -> list[Dividend]:
        """Return all dividends ordered by dividend_date DESC."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM dividends ORDER BY dividend_date DESC"
        ).fetchall()
        self._release(conn)
        return [_row_to_dividend(r) for r in rows]

    def get_dividends_by_symbol(self, symbol: str) -> list[Dividend]:
        """Return dividends for a specific symbol, ordered by dividend_date DESC."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM dividends WHERE symbol = ? ORDER BY dividend_date DESC",
            (symbol,),
        ).fetchall()
        self._release(conn)
        return [_row_to_dividend(r) for r in rows]

    # ------------------------------------------------------------------
    # Recalculation (stub — wired to engine in Task 5)
    # ------------------------------------------------------------------

    def recalculate_positions(self) -> None:
        """
        Stub: clear derived tables and write nothing yet.

        This will be wired to the strategy engine in Task 5 so that all
        positions, assignments, and lifecycle events are rebuilt by replaying
        trades in chronological order.
        """
        conn = self._conn()
        with conn:
            conn.execute("DELETE FROM covered_call_lifecycle")
            conn.execute("DELETE FROM assignments")
            conn.execute("DELETE FROM positions")
        self._release(conn)

    # ------------------------------------------------------------------
    # Internal helpers used by the engine (Task 5)
    # ------------------------------------------------------------------

    def get_trades_chronological(self) -> list[Trade]:
        """Return all trades ordered by trade_date ASC (for engine replay)."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY trade_date ASC, id ASC"
        ).fetchall()
        self._release(conn)
        return [_row_to_trade(r) for r in rows]

    def get_dividends_chronological(self) -> list[Dividend]:
        """Return all dividends ordered by dividend_date ASC (for engine replay)."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM dividends ORDER BY dividend_date ASC, id ASC"
        ).fetchall()
        self._release(conn)
        return [_row_to_dividend(r) for r in rows]

    def clear_derived_tables(self) -> None:
        """Delete all derived data (positions, assignments, lifecycle events)."""
        conn = self._conn()
        with conn:
            conn.execute("DELETE FROM covered_call_lifecycle")
            conn.execute("DELETE FROM assignments")
            conn.execute("DELETE FROM positions")
        self._release(conn)
