# Financial Strategy Tracker — Implementation Plan

## Problem Statement

Build a Streamlit desktop web application for tracking financial trading strategies,
starting with the Wheel Options Strategy. The app tracks trades, computes positions
and cost basis through a strategy-agnostic plugin engine, and provides views for
trades, positions, assignments, and covered calls.

## Requirements

As specified in `REQUIREMENTS.md` — data model (§1–2), recalculation engine (§3),
repository (§4), IB importer (§5), all 7 pages (§6–12), architecture constraints (§13),
tests (§14), config/build (§15–17).

## Background

The project is greenfield — all directories (`charts/`, `views/`, `importers/`, `tests/`)
are empty. The architecture is a layered plugin system:

```
config → models → database → repository → engine/strategies → views → app.py
```

Strict import boundaries are defined in §13.1 of the requirements.

## Proposed Solution

Build the application layer by layer, bottom-up. Each task produces a working and
testable increment. The installer is introduced early (Task 7) so testers can validate
on machines with no Python environment, with each subsequent feature delivered as a
new installer build.

---

## Task Breakdown

### Task 1: Project scaffold and configuration

- **Objective:** Set up the project structure, dependencies, and configuration so the
  app can be launched with a blank database.
- **Implementation:**
  - Create `config.py` with the DATA_DIR resolution rule from §15
  - Create `requirements.txt` pinning: `streamlit`, `pandas`, `plotly`, `openpyxl`, `pytest`
  - Create `VERSION` file with `0.1.0`
  - Create all empty `__init__.py` files for:
    `strategies/`, `strategies/wheel/`, `importers/`, `importers/wheel/`,
    `charts/`, `views/`, `views/strategies/`, `views/strategies/wheel/`,
    `tests/`, `tests/strategies/`
- **Tests:** None — scaffold only.
- **Demo:** `python -c "from config import DB_NAME; print(DB_NAME)"` prints the correct
  path without error.

---

### Task 2: Data models

- **Objective:** Define all dataclasses so every other layer has typed objects to work with.
- **Implementation:** Create `models.py` with dataclasses for:
  - `Trade` — all fields from §1.1
  - `Position` — all fields from §1.2
  - `Assignment` — all fields from §1.3
  - `CoveredCallLifecycle` — all fields from §1.4
  - `PositionAction` — all fields from §1.5
  - `PluginResult` — `state: dict`, `assignments: list[Assignment]`, `lifecycle_events: list`
- **Tests:** None — pure data containers, validated indirectly by engine tests.
- **Demo:** `python -c "from models import Trade, Position, PluginResult; print('OK')"` exits cleanly.

---

### Task 3: Database initialization and repository

- **Objective:** Create the SQLite schema and a fully working repository so all data
  operations are available before any business logic is written.
- **Implementation:**
  - `database.py` — schema creation for all 5 tables from §1
  - `repository.py` — all operations listed in §4.1; `recalculate_positions` stub
    clears derived tables and writes nothing yet (wired to engine in Task 5)
- **Tests:** `tests/test_repository.py` — CRUD round-trips for trades, positions,
  assignments, lifecycle events, and position actions using an in-memory SQLite
  database (`:memory:`).
- **Demo:** `pytest tests/test_repository.py` — all CRUD tests pass.

---

### Task 4: Shared calculations module

- **Objective:** Implement and test all pure math functions so they can be reused by
  the engine and views.
- **Implementation:** Create `calculations.py` with:
  - `premium_value(premium, contracts)`
  - `net_premium_value(premium, contracts, broker_fee)`
  - `dte(expiration)`
  - `total_premium(premium, contracts)`
- **Tests:** `tests/test_calculations.py` — covers SELL vs BUY sign conventions,
  fee-adjusted net, DTE for open/non-open trades, edge cases (zero fee, zero contracts).
- **Demo:** `pytest tests/test_calculations.py` — all pass.

---

### Task 5: Wheel strategy plugin and recalculation engine

- **Objective:** Implement the core business logic — the state machine that turns a
  list of trades into positions, assignments, and lifecycle events.
- **Implementation:**
  - `strategies/base.py` — abstract `StrategyPlugin` base class and `PluginResult` (§3.0)
  - `strategies/wheel/calculations.py` — wheel-specific math: `net_stock_basis_put`,
    `net_stock_basis_call`, `cost_basis_from_cc`
  - `strategies/wheel/engine.py` — `WheelPlugin` implementing all state transitions
    from §3.2–3.3, using `net_premium_value` throughout
  - `engine.py` — plugin registry (`STRATEGY_PLUGINS`) and `recalculate_positions(db)`
    that replays all trades via the correct plugin and persists results (wiring §4.2
    into repository)
- **Tests:** `tests/strategies/test_wheel_engine.py`:
  - CSP open / expired-unassigned / expired-assigned
  - CC open / closed / expired / called-away
  - Cost basis reduction uses `net_premium_value`
  - Cycle number increment on assignment
  - `shares` floor at 0
  - `total_fees_paid` accumulation
  - `broker_fee` propagated to Assignment and lifecycle events
- **Demo:** Insert a sequence of CSP → assigned → CC → expired trades in a test DB,
  call `recalculate_positions`, assert the resulting position and assignment records
  are correct.

---

### Task 6: Streamlit app shell and Dashboard page

- **Objective:** Get the app running in a browser with working navigation and the
  first real page.
- **Implementation:**
  - `app.py` — Streamlit multi-page shell with sidebar navigation wiring all pages
  - `charts/premium_charts.py` — bar chart functions (premium by week, premium by
    symbol) using plotly
  - `views/dashboard.py` — Dashboard page (§6): weekly/monthly/total premium, total
    fees, net premium, open positions count, weekly premium bar chart
- **Tests:** None for views (§14.2).
- **Demo:** `streamlit run app.py` opens in browser; Dashboard shows zero-state metrics
  and an empty chart with no errors.

---

### Task 7: Windows installer

- **Objective:** Package the current app shell as a standalone Windows installer so
  testers can validate on machines with no Python environment, and so subsequent
  tasks can be delivered as new installer builds.
- **Implementation:**
  - `launcher.py` — thin Streamlit launcher (§17.4)
  - `financial_tracker.spec` — PyInstaller spec (§17.3): `--onedir`, hidden imports,
    streamlit static assets, `launcher.py` as entry point, `VERSION` file read for
    version string
  - `installer.iss` — Inno Setup script (§17.5): app name/version from `VERSION`,
    install dir `{autopf}\FinancialStrategyTracker`, desktop shortcut, Start Menu
    entry, uninstaller preserves `%APPDATA%\FinancialStrategyTracker\` data directory
- **Tests:** Acceptance criteria from §17.8 verified manually on a clean Windows VM.
- **Demo:** Run `pyinstaller financial_tracker.spec` then `iscc installer.iss`. Install
  on a clean machine, double-click desktop shortcut — browser opens to `localhost:8501`
  showing the Dashboard.

---

### Task 8: Add Trade page and Trades page

- **Objective:** Allow users to enter and manage trades through the UI.
- **Implementation:**
  - `views/add_trade.py` — Add Trade form (§7) with all fields, defaults, uppercase
    symbol, submit saves and triggers recalculation
  - `views/trades.py` — Trades table (§8.1) with formatted columns, DTE logic; edit
    dropdown (§8.2); delete with confirmation (§8.3)
- **Tests:** None for views.
- **Demo:** Add a CSP trade via the form, see it appear in the Trades table with correct
  `total_premium` and DTE. Edit the premium, confirm recalculation fires. Delete the
  trade, confirm it disappears.

---

### Task 9: Positions page

- **Objective:** Show current positions and allow manual position management actions.
- **Implementation:**
  - `views/strategies/wheel/positions.py` — summary metrics (§10.1), positions table
    (§10.2), position management panel (§10.3) with all action behaviors, action
    history expander (§10.4), premium by symbol chart (§10.5)
  - Wire all position actions (`CLOSE_CSP`, `CSP_EXPIRED_UNASSIGNED`, `CSP_ASSIGNED`,
    `KEEP_SHARES`, `SELL_CC`, `ADJUST_PREMIUM`, `Wait for Expiration`) to
    `repository.record_position_action` and `repository.update_position_status`
- **Tests:** None for views.
- **Demo:** After adding a CSP trade with status ASSIGNED, navigate to Positions — see
  the symbol with `COVERED CALLS` status. Trigger "Keep Stocks", confirm status changes
  to `READY FOR CC` and action appears in history.

---

### Task 10: Assignments page and Covered Calls page

- **Objective:** Provide read-only ledger views for assignments and CC lifecycle events.
- **Implementation:**
  - `views/strategies/wheel/assignments.py` — summary metrics (§11.1) and assignment
    ledger table (§11.2) with formatted money columns
  - `views/strategies/wheel/covered_calls.py` — summary metrics (§12.1) and lifecycle
    ledger table (§12.2) with formatted money columns
  - Wire both pages into `app.py` navigation
- **Tests:** None for views.
- **Demo:** After a full CSP→assigned→CC→expired cycle, the Assignments page shows the
  PUT ASSIGNED event with correct `net_stock_basis`, and Covered Calls shows the
  EXPIRED lifecycle event.

---

### Task 11: IB CSV importer and Import Trades page

- **Objective:** Allow users to import trade history from Interactive Brokers.
- **Implementation:**
  - `importers/ib_importer.py` — top-level parser: reads CSV, identifies header/data
    rows, dispatches option rows to wheel importer, emits warnings for stock rows
  - `importers/wheel/ib_importer.py` — wheel-specific row parser: option symbol regex
    (`SYMBOL DDMMMYY STRIKE P|C`), action mapping, status logic (OPEN or EXPIRED based
    on expiration date per §5.4), assignment row handling (§5.5), duplicate detection
    (§5.7)
  - `views/import_trades.py` — Import page (§9): file uploader, parse preview, warning
    expander, selective import with checkboxes, save + recalculate
- **Tests:** `tests/test_ib_importer.py`:
  - Option symbol parsing (P and C)
  - Date parsing
  - Action mapping (negative qty → SELL)
  - Assignment row handling
  - Stock row warning
  - Duplicate detection
  - Commission column mapped to `broker_fee` as positive float
- **Demo:** Upload a sample IB CSV with a mix of puts, calls, and an assignment row.
  Preview table shows parsed trades; warnings panel shows stock rows; import selected
  trades and confirm they appear on the Trades page.
