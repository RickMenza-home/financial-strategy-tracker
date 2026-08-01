"""
Database connection and schema initialisation.

Responsibility: open a SQLite connection and create all tables.
No business logic lives here — only DDL and connection management.

May import: config only.
"""

import sqlite3
from pathlib import Path

from config import DB_NAME


def get_connection(db_path: Path = DB_NAME) -> sqlite3.Connection:
    """Return a SQLite connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_NAME) -> None:
    """Create all tables if they do not already exist."""
    conn = get_connection(db_path)
    with conn:
        conn.executescript(_SCHEMA)
    conn.close()


def _get_schema() -> str:
    """Return the DDL schema string (used by Repository for in-memory DBs)."""
    return _SCHEMA


_SCHEMA = """
-- -----------------------------------------------------------------------
-- §1.1  Trades
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_type TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    strategy      TEXT    NOT NULL,
    action        TEXT    NOT NULL,
    trade_date    TEXT    NOT NULL,   -- ISO 8601 YYYY-MM-DD
    expiration    TEXT    NOT NULL,   -- ISO 8601 YYYY-MM-DD
    strike        REAL    NOT NULL,
    premium       REAL    NOT NULL,
    contracts     INTEGER NOT NULL,
    broker_fee    REAL    NOT NULL DEFAULT 0.0,
    status        TEXT    NOT NULL,
    notes         TEXT    NOT NULL DEFAULT ''
);

-- -----------------------------------------------------------------------
-- §1.2  Positions  (derived, one row per symbol × strategy_type)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS positions (
    symbol               TEXT NOT NULL,
    strategy_type        TEXT NOT NULL,
    shares               INTEGER NOT NULL DEFAULT 0,
    cost_basis           REAL    NOT NULL DEFAULT 0.0,
    premium_collected    REAL    NOT NULL DEFAULT 0.0,
    total_fees_paid      REAL    NOT NULL DEFAULT 0.0,
    dividends_collected  REAL    NOT NULL DEFAULT 0.0,
    status               TEXT    NOT NULL DEFAULT 'CSP',
    PRIMARY KEY (symbol, strategy_type)
);

-- -----------------------------------------------------------------------
-- §1.3  Assignments
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assignments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    symbol          TEXT    NOT NULL,
    assignment_date TEXT    NOT NULL,   -- ISO 8601
    strategy        TEXT    NOT NULL,
    assignment_type TEXT    NOT NULL,
    strike          REAL    NOT NULL,
    premium         REAL    NOT NULL,
    contracts       INTEGER NOT NULL,
    broker_fee      REAL    NOT NULL DEFAULT 0.0,
    shares          INTEGER NOT NULL,
    stock_value     REAL    NOT NULL,
    premium_value   REAL    NOT NULL,
    net_stock_basis REAL    NOT NULL,
    notes           TEXT    NOT NULL DEFAULT ''
);

-- -----------------------------------------------------------------------
-- §1.4  Covered Call Lifecycle Events
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS covered_call_lifecycle (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    symbol          TEXT    NOT NULL,
    cycle_number    INTEGER NOT NULL,
    trade_date      TEXT    NOT NULL,   -- ISO 8601
    expiration      TEXT    NOT NULL,   -- ISO 8601
    action          TEXT    NOT NULL,
    lifecycle_stage TEXT    NOT NULL,
    strike          REAL    NOT NULL,
    premium         REAL    NOT NULL,
    contracts       INTEGER NOT NULL,
    broker_fee      REAL    NOT NULL DEFAULT 0.0,
    shares_covered  INTEGER NOT NULL,
    premium_value   REAL    NOT NULL,
    notes           TEXT    NOT NULL DEFAULT ''
);

-- -----------------------------------------------------------------------
-- §1.5  Position Actions  (manual user actions)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS position_actions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_type       TEXT    NOT NULL,
    symbol              TEXT    NOT NULL,
    action_date         TEXT    NOT NULL,   -- ISO 8601 datetime
    action_type         TEXT    NOT NULL,
    previous_status     TEXT    NOT NULL,
    new_status          TEXT    NOT NULL,
    adjusted_premium    REAL    NOT NULL DEFAULT 0.0,
    adjusted_cost_basis REAL    NOT NULL DEFAULT 0.0,
    notes               TEXT    NOT NULL DEFAULT ''
);

-- -----------------------------------------------------------------------
-- §1.6  Dividends
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dividends (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_type TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    dividend_date TEXT    NOT NULL,   -- ISO 8601 YYYY-MM-DD
    amount        REAL    NOT NULL,
    shares        INTEGER NOT NULL,
    broker_fee    REAL    NOT NULL DEFAULT 0.0,
    notes         TEXT    NOT NULL DEFAULT ''
);
"""
