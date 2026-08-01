# Financial Strategy Tracker — Requirements

## Overview

A desktop web application (Streamlit) for tracking financial trading strategies.
The first supported strategy is the **Wheel Options Strategy** — a cycle of selling
cash-secured puts (CSP) on a stock, accepting assignment if exercised, then selling
covered calls (CC) on the shares until they are called away, then restarting the cycle.

The application is designed to be **strategy-agnostic at its core**: new strategies
(e.g. Iron Condor, LEAPS, covered stock positions) can be added without modifying
shared infrastructure. Each strategy is an independent plugin that provides its own
trade types, recalculation engine, position states, UI views, and importers.

The application tracks trades, computes positions and cost basis, records assignment
events, and provides a dashboard with premium income summaries.

---

## 0. Wheel Strategy Workflow

The following describes the full lifecycle of the wheel strategy as defined in the
architecture diagram (`doc-ressources/wheel-structure-architecture.drawio`).

### 0.1 Workflow Overview

![Wheel Strategy Architecture](doc-ressources/wheel-structure-architecture.jpg)

### 0.2 State Transitions

| Event                          | From status      | To status        | Side effect                          |
|--------------------------------|------------------|------------------|--------------------------------------|
| New position created           | —                | `CSP`            | Initialise position record           |
| Sell CSP                       | `CSP`            | `CSP`            | Accumulate premium, record trade     |
| CSP expires without assignation| `CSP`            | `CSP`            | Record `CSP_EXPIRED_UNASSIGNED`      |
| Close trade (Buy CSP)          | `CSP`            | `CSP`            | Subtract buy cost, record `CLOSE_CSP` |
| CSP expires with assignation   | `CSP`            | `COVERED CALLS`  | Shares added, record `CSP_ASSIGNED`  |
| Keep stocks (no CC yet)        | `COVERED CALLS`  | `READY FOR CC`   | Record `KEEP_SHARES`                 |
| Sell CC                        | `READY FOR CC`   | `CC OPEN`        | Accumulate premium, record `SELL_CC` |
| CC expires without assignation | `CC OPEN`        | `READY FOR CC`   | Reduce cost basis, loop to Sell CSP  |
| Close trade (Buy CC)           | `CC OPEN`        | `READY FOR CC`   | Subtract buy cost, record close      |
| CC expires with assignation    | `CC OPEN`        | `CSP`            | Shares called away, reset position   |
| Sell stock (exit position)     | `COVERED CALLS`  | —                | End of trade, calculate profit/loss  |

### 0.3 Premium Accumulation Points

Premium (and cost basis adjustment) is recorded at two points in the cycle:

1. **After Sell CSP** — `Add premium value (and calculate stock basis price)`:
   Premium received is added to `premium_collected`; cost basis is set to
   `strike − premium_per_share` on assignment.

2. **After Sell CC** — `Add premium value (and calculate stock basis price)`:
   Premium received is added to `premium_collected`; cost basis per share is
   reduced by `premium_value / (contracts × 100)` each time a CC is processed.

### 0.4 Cycle End

The trade cycle ends at **End of trade (Calculate total profit/loss)** when either:
- The CSP was bought back (closed early), or
- The shares were sold outright after assignment.

Total profit/loss = sum of all premium collected − cost to close any positions.

---

## 1. Data Model

### 1.1 Trade

A trade is the core record entered by the user.

| Field           | Type    | Required | Constraints                                              |
|-----------------|---------|----------|----------------------------------------------------------|
| id              | int     | auto     | Primary key, auto-increment                              |
| strategy_type   | str     | yes      | Plugin identifier, e.g. `"wheel"`. Determines which engine processes this trade. |
| symbol          | str     | yes      | Uppercase ticker, e.g. "SOFI"                            |
| strategy        | str     | yes      | Trade sub-type within the strategy, e.g. `CSP`, `CC`    |
| action          | str     | yes      | One of: `SELL`, `BUY`                                    |
| trade_date      | date    | yes      | ISO 8601 format (YYYY-MM-DD)                             |
| expiration      | date    | yes      | ISO 8601 format, must be >= trade_date                   |
| strike          | float   | yes      | > 0                                                      |
| premium         | float   | yes      | >= 0, per-share price                                    |
| contracts       | int     | yes      | >= 1                                                     |
| broker_fee      | float   | no       | >= 0, total broker commission/fee paid for this trade. Defaults to `0.0`. |
| status          | str     | yes      | One of: `OPEN`, `CLOSED`, `ASSIGNED`, `EXPIRED`          |
| notes           | str     | no       | Free text                                                |

> The `strategy_type` field is the **dispatch key** used by the recalculation engine
> to route each trade to the correct strategy plugin. Trades belonging to different
> strategies coexist in the same table and are never mixed during recalculation.

### 1.2 Position

Derived from trades via the recalculation engine. One record per `(symbol, strategy_type)` pair.

| Field              | Type   | Description                                                   |
|--------------------|--------|---------------------------------------------------------------|
| symbol             | str    | Composite primary key (with strategy_type)                    |
| strategy_type      | str    | Plugin identifier — which strategy owns this position         |
| shares             | int    | Current shares held                                           |
| cost_basis         | float  | Current cost basis per share                                  |
| premium_collected  | float  | Total net premium collected (all time)                        |
| total_fees_paid    | float  | Cumulative broker fees paid across all trades for this position |
| status             | str    | Strategy-defined status string (e.g. `CSP`, `CC OPEN`, etc.) |

### 1.3 Assignment

An event created when a trade reaches `ASSIGNED` status. One record per assignment event.

| Field           | Type   | Description                                        |
|-----------------|--------|----------------------------------------------------|
| id              | int    | Primary key                                        |
| trade_id        | int    | Foreign key to trades                              |
| symbol          | str    |                                                    |
| assignment_date | date   | Expiration date of the assigned option             |
| strategy        | str    | `CSP` or `CC`                                      |
| assignment_type | str    | `PUT ASSIGNED` or `CALL ASSIGNED`                  |
| strike          | float  |                                                    |
| premium         | float  | Per-share premium of the original trade            |
| contracts       | int    |                                                    |
| broker_fee      | float  | Broker fee paid for the original trade             |
| shares          | int    | Positive for PUT ASSIGNED, negative for CALL ASSIGNED |
| stock_value     | float  | strike × abs(shares)                               |
| premium_value   | float  | Net premium cashflow of the trade                  |
| net_stock_basis | float  | See calculation rules below                        |
| notes           | str    |                                                    |

### 1.4 Covered Call Lifecycle Event

One record per CC trade, tracking the lifecycle of each covered call cycle.

| Field           | Type   | Description                                        |
|-----------------|--------|----------------------------------------------------|
| id              | int    | Primary key                                        |
| trade_id        | int    | Foreign key to trades                              |
| symbol          | str    |                                                    |
| cycle_number    | int    | Incremented each time a PUT is assigned            |
| trade_date      | date   |                                                    |
| expiration      | date   |                                                    |
| action          | str    | `SELL` or `BUY`                                    |
| lifecycle_stage | str    | One of: `OPEN`, `CLOSED`, `EXPIRED`, `CALLED AWAY` |
| strike          | float  |                                                    |
| premium         | float  |                                                    |
| contracts       | int    |                                                    |
| broker_fee      | float  | Broker fee paid for this CC trade                  |
| shares_covered  | int    | contracts × 100                                    |
| premium_value   | float  | Net premium cashflow of the trade                  |
| notes           | str    |                                                    |

### 1.5 Position Action

A manual action recorded by the user on a position (e.g. closing a CSP early,
keeping shares, initiating a CC).

| Field              | Type     | Description                                    |
|--------------------|----------|------------------------------------------------|
| id                 | int      | Primary key                                    |
| strategy_type      | str      | Plugin identifier                              |
| symbol             | str      |                                                |
| action_date        | datetime | When the action was recorded                   |
| action_type        | str      | Strategy-defined action type string            |
| previous_status    | str      | position status before the action              |
| new_status         | str      | position status after the action               |
| adjusted_premium   | float    | New total premium after adjustment             |
| adjusted_cost_basis| float    | New cost basis after adjustment                |
| notes              | str      |                                                |

**Wheel action types:** `CLOSE_CSP`, `CSP_EXPIRED_UNASSIGNED`, `CSP_ASSIGNED`,
`KEEP_SHARES`, `SELL_CC`, `ADJUST_PREMIUM`

> Other strategies define their own action type vocabularies independently.

---

## 2. Calculation Rules

### 2.1 Premium Cashflow

The gross premium cashflow for a single trade (before fees):

```
premium_value = premium × contracts × 100
```

- If `action == "SELL"`: cashflow is **positive** (income)
- If `action == "BUY"`: cashflow is **negative** (expense, closing a position)

### 2.2 Net Premium Cashflow (fee-adjusted)

The net cashflow after subtracting the broker fee. This is the value used in all
P&L and cost basis calculations:

```
net_premium_value = premium_value - broker_fee
```

`broker_fee` is always positive and always reduces net income regardless of trade
direction (fees are a cost on both buys and sells).

> Wherever `premium_value` is used in engine state-machine logic (accumulating
> `premium_collected`, adjusting `cost_basis`, computing `net_stock_basis`), the
> value substituted is `net_premium_value`.

### 2.3 Total Premium (display)

```
total_premium = premium × contracts × 100
```

This is always the **gross** value (unsigned, before fees) used for display in trade
lists. Use `net_premium_value` wherever actual P&L is computed.

### 2.4 Days to Expiration (DTE)

```
dte = (expiration - today).days
```

Only shown for trades with `status == "OPEN"`. Null/empty for all other statuses.

### 2.5 Net Stock Basis on PUT Assignment

When a CSP is assigned, fees are added to the cost of acquiring the shares:

```
shares_added     = contracts × 100
stock_value      = strike × shares_added
net_stock_basis  = stock_value - net_premium_value   # net_premium_value is positive (SELL)
```

Because `net_premium_value < premium_value`, the net stock basis is **higher** than
without fees — reflecting the true cost of entry.

### 2.6 Net Stock Basis on CALL Assignment

When a CC is assigned (shares called away), fees reduce the net proceeds:

```
shares_called_away = contracts × 100
stock_value        = strike × shares_called_away
net_stock_basis    = stock_value + net_premium_value  # net_premium_value is positive (SELL)
```

### 2.7 Cost Basis Adjustment from Covered Calls

Each time a CC trade is processed (status OPEN, CLOSED, or EXPIRED), the
fee-adjusted premium reduces the cost basis:

```
cost_basis_per_share -= net_premium_value / (contracts × 100)
```

### 2.8 Total Net P&L (position close)

When a position cycle ends (CSP bought back or shares sold after assignment),
the total net profit/loss is:

```
total_net_pnl = premium_collected - total_fees_paid
```

Where:
- `premium_collected` is the running sum of all `net_premium_value` entries
  accumulated during recalculation (already fee-adjusted per trade)
- `total_fees_paid` is the running sum of all `broker_fee` values across all trades
  for the position

> Since each `net_premium_value = premium_value - broker_fee`, and
> `premium_collected` accumulates `net_premium_value`, fees are already embedded in
> `premium_collected`. `total_fees_paid` is stored separately for reporting
> transparency (so the UI can display gross premium, total fees, and net P&L
> independently).

---

## 3. Position Recalculation Engine

Positions are fully recalculated from scratch by replaying all trades in
chronological order (`trade_date ASC`). Existing `positions`, `assignments`,
and `covered_call_lifecycle` records are deleted and rebuilt on each recalculation.

The engine is **strategy-agnostic**: it dispatches each trade to the correct
strategy plugin based on `trade.strategy_type`. Each plugin owns its own state
machine and produces positions, assignments, and lifecycle events independently.

### 3.0 Strategy Plugin Interface

Every strategy plugin must implement the following interface:

```python
class StrategyPlugin:
    strategy_type: str          # unique identifier, e.g. "wheel"
    display_name: str           # human-readable, e.g. "Wheel Strategy"

    def initial_position_state(self, symbol: str) -> dict:
        """Return the blank position dict for a new symbol."""

    def process_trade(self, trade: Trade, state: dict) -> PluginResult:
        """
        Apply one trade to the running position state.
        Returns updated state plus any Assignment / lifecycle events to persist.
        """

    def get_available_actions(self, position: Position) -> list[str]:
        """Return the action types available for the current position status."""
```

`PluginResult` is a plain dataclass:

```python
@dataclass
class PluginResult:
    state: dict                        # updated position state
    assignments: list[Assignment]      # new assignment events (may be empty)
    lifecycle_events: list[Any]        # strategy-specific lifecycle rows (may be empty)
```

Plugins are registered in `engine.py` at startup:

```python
STRATEGY_PLUGINS: dict[str, StrategyPlugin] = {
    "wheel": WheelPlugin(),
    # "iron_condor": IronCondorPlugin(),   # future
}
```

Adding a new strategy = creating a new plugin class and adding one entry to this dict.
No other core file needs to change.

### 3.1 Initial State Per Symbol

When a symbol is first seen:

```
shares            = 0
cost_basis        = 0.0
premium_collected = 0.0
total_fees_paid   = 0.0
wheel_status      = "CSP"
cycle_number      = 0
```

### 3.2 CSP Trade Processing

For every trade with `strategy == "CSP"`:

1. Compute `net_premium_value = premium_value - broker_fee`
2. Accumulate `net_premium_value` into `premium_collected`
3. Accumulate `broker_fee` into `total_fees_paid`
4. If `status == "ASSIGNED"`:
   - `shares += contracts × 100`
   - `cost_basis = strike - (net_premium_value / (contracts × 100))` (per-share basis, fee-adjusted)
   - `wheel_status = "COVERED CALLS"`
   - `cycle_number += 1`
   - Create an **Assignment** event with `assignment_type = "PUT ASSIGNED"`, carrying `broker_fee`

### 3.3 CC Trade Processing

For every trade with `strategy == "CC"`:

1. Compute `net_premium_value = premium_value - broker_fee`
2. Accumulate `net_premium_value` into `premium_collected`
3. Accumulate `broker_fee` into `total_fees_paid`
4. Create a **Covered Call Lifecycle** event, carrying `broker_fee`
5. If `status` is `OPEN`, `CLOSED`, or `EXPIRED`:
   - Reduce `cost_basis` by `net_premium_value / (contracts × 100)`
   - If shares > 0: `wheel_status = "CC OPEN"` when OPEN, else `"READY FOR CC"`
6. If `status == "ASSIGNED"` (shares called away):
   - `shares -= contracts × 100` (floor at 0)
   - If `shares == 0`: `cost_basis = 0`, `wheel_status = "CSP"`
   - If `shares > 0`: `wheel_status = "READY FOR CC"`
   - Create an **Assignment** event with `assignment_type = "CALL ASSIGNED"`, carrying `broker_fee`

### 3.4 Covered Call Lifecycle Stage Mapping

| Trade status | Lifecycle stage |
|--------------|-----------------|
| OPEN         | OPEN            |
| CLOSED       | CLOSED          |
| EXPIRED      | EXPIRED         |
| ASSIGNED     | CALLED AWAY     |

### 3.5 Recalculation Trigger

Recalculation is triggered after any of the following operations:
- Adding a trade
- Updating a trade
- Deleting a trade
- Importing trades

---

## 4. Trade Repository

All database access goes through the repository layer. No SQL outside this layer.

### 4.1 Required Operations

| Operation              | Description                                         |
|------------------------|-----------------------------------------------------|
| `add_trade`            | Insert a new trade record                           |
| `update_trade`         | Update all fields of an existing trade by id        |
| `delete_trade`         | Delete a trade by id                                |
| `get_trades`           | Return all trades ordered by `trade_date DESC`      |
| `get_trade_by_id`      | Return a single trade by id                         |
| `get_positions`        | Return all positions ordered by `premium_collected DESC` |
| `get_position_by_symbol` | Return a single position by symbol               |
| `get_assignments`      | Return all assignments ordered by `assignment_date DESC` |
| `get_covered_call_lifecycle` | Return all CC lifecycle events ordered by `trade_date DESC` |
| `get_position_actions` | Return all position actions, optionally filtered by symbol |
| `record_position_action` | Insert a position action record                   |
| `update_position_status` | Update `wheel_status` on a position              |
| `adjust_position_premium` | Add a delta to `premium_collected` and recalculate `cost_basis` |

### 4.2 Recalculate Positions

The `recalculate_positions` operation:
1. Loads all trades in chronological order
2. Clears the `positions`, `assignments`, and `covered_call_lifecycle` tables
3. Replays trades according to the engine rules (Section 3)
4. Writes the resulting positions, assignments, and lifecycle events

---

## 5. IB Importer

### 5.1 Input Format

An Interactive Brokers transaction history CSV with rows in the format:

```
Transaction History,Header,Date,Transaction Type,Description,Symbol,Quantity,Price,Commission,...
Transaction History,Data,2026-05-01,BUY,"SOFI 01MAY26 16 P",SOFI,-1,0.25,-1.05,...
```

- Rows prefixed with `Transaction History,Header` define the column names
- Rows prefixed with `Transaction History,Data` contain transaction data
- All other rows are ignored

The `Commission` column (or equivalent fee column in the IB export) is mapped to
`broker_fee`. The value is stored as a positive float — if IB exports it as a
negative number (a debit), take the absolute value.

### 5.2 Option Symbol Parsing

Options are identified by a description matching the pattern:

```
SYMBOL DDMMMYY STRIKE P|C
```

Examples: `SOFI 01MAY26 16 P`, `NKE 24APR26 46.5 C`

Parsing rules:
- `P` → strategy `CSP`, type `PUT`
- `C` → strategy `CC`, type `CALL`
- Two-digit year → 2000 + year (e.g. `26` → `2026`)

### 5.3 Action Mapping

| IB quantity | Trade action |
|-------------|--------------|
| Negative    | SELL         |
| Positive    | BUY          |

### 5.4 Status Assignment on Import

All imported option trades are given status `OPEN` by default.
The user is expected to update status manually after import if needed.

> **Note (current code):** The existing importer assigns `CLOSED` when action is `SELL`.
> The rebuilt importer should assign `OPEN` for all imports unless the expiration
> date is in the past, in which case status should be `EXPIRED`.

### 5.5 Assignment Rows

Rows where the description contains `"Assignment"` or `"Assignation"` are imported
as trades with `strategy = "CSP"`, `status = "ASSIGNED"`, `premium = 0.0`, and
`broker_fee` mapped from the `Commission` column (absolute value, default `0.0`).

### 5.6 Stock Transaction Rows

Rows with `Transaction Type` of `BUY` or `SELL` that are not options or assignments
are emitted as **warnings** and are not imported. The user must add them manually.

### 5.7 Duplicate Detection

Before adding a trade, check against existing trades for a match on:
`symbol + trade_date + expiration + strike + strategy`.
Duplicates are skipped and counted in warnings.

### 5.8 Return Value

The importer returns `(trades: list[dict], warnings: list[str])`.
It does not write to the database directly. The caller is responsible for saving.

---

## 6. Dashboard Page

Displays summary metrics and a chart. No user input.

### 6.1 Metrics

| Metric           | Calculation                                              |
|------------------|----------------------------------------------------------|
| Weekly Premium   | Sum of `total_premium` for trades in the current week   |
| Monthly Premium  | Sum of `total_premium` for trades in the current month  |
| Total Premium    | Sum of all `total_premium` (gross, before fees)          |
| Total Fees       | Sum of all `broker_fee` across all trades                |
| Net Premium      | Total Premium − Total Fees                               |
| Open Positions   | Count of trades with `status == "OPEN"`                 |

Week is defined as `YYYY-W<week_number>` using `strftime("%Y-W%U")`.
Month is defined as `YYYY-MM`.

### 6.2 Chart

Bar chart of total premium collected grouped by week (`week` column on X axis,
`total_premium` sum on Y axis).

---

## 7. Add Trade Page

A form for entering a single trade manually.

### 7.1 Fields

All fields from the Trade model (Section 1.1) except `id`.
Default values:
- Symbol: `"SOFI"`
- Strike: `25.0`
- Premium: `0.50`
- Contracts: `1`
- Broker Fee: `0.0`
- Trade Date: today
- Expiration: today
- Strategy: `CSP`
- Action: `SELL`
- Status: `OPEN`

### 7.2 Behavior

- Symbol is always stored as uppercase
- On submit: save trade, trigger recalculation, display confirmation with total premium
- Form does not reset automatically (Streamlit default behavior)

---

## 8. Trades Page

Displays all trades and allows editing or deleting a selected trade.

### 8.1 Trade Table

Shows all trades with these columns:
`id, symbol, strategy, action, trade_date, expiration, strike, premium,
contracts, broker_fee, status, days_to_expiration, total_premium, notes`

- `trade_date` and `expiration` formatted as `YYYY-MM-DD`
- `strike`, `premium`, `broker_fee`, `total_premium` formatted as `$X,XXX.XX`
- `days_to_expiration` is blank for non-OPEN trades

### 8.2 Edit Trade

Select a trade from a dropdown. All fields are editable.
On submit: update trade, trigger recalculation, refresh page.

### 8.3 Delete Trade

A delete button with a confirmation step ("Are you sure?").
On confirm: delete trade, trigger recalculation, refresh page.

---

## 9. Import Trades Page

Upload a CSV file from Interactive Brokers.

### 9.1 Behavior

1. User uploads a CSV file
2. App parses the file using the IB importer
3. App shows count of trades found and any warnings
4. App shows a preview table of trades to be imported
5. User can import all trades or select specific trades to import
6. On import: save trades, trigger recalculation, show success message

### 9.2 Warnings Panel

Warnings from the importer (duplicate skips, stock transactions, parse errors)
are shown in a collapsible expander.

---

## 10. Positions Page

Displays current positions and allows manual position management.

### 10.1 Summary Metrics

| Metric             | Calculation                                              |
|--------------------|----------------------------------------------------------|
| Total Premium      | Sum of `premium_collected` across all positions (net, fee-adjusted) |
| Total Fees Paid    | Sum of `total_fees_paid` across all positions            |
| Net P&L            | Total Premium (already net) — shown alongside Total Fees for transparency |
| Tracked Symbols    | Count of positions                                       |
| Assigned Positions | Count of positions where `shares > 0`                    |

### 10.2 Positions Table

Columns: `symbol, shares, cost_basis, premium_collected, total_fees_paid, wheel_status`
- `premium_collected`, `total_fees_paid`, and `cost_basis` formatted as `$X,XXX.XX`

### 10.3 Position Management Panel

User selects a symbol. The panel shows:
- Shares, Cost Basis/Share, Net Premium (fee-adjusted), Total Fees Paid, Status (as metrics)
- A dropdown of available next actions based on current `wheel_status`

#### Available Actions by Status

| wheel_status   | Available actions                                        |
|----------------|----------------------------------------------------------|
| CSP            | Close CSP (Buy back), CSP Expires Without Assignment, CSP Expires With Assignment |
| COVERED CALLS  | Adjust Premium, Keep Stocks, Sell CC                     |
| CC OPEN        | Adjust Premium, Wait for Expiration, Close CC            |
| READY FOR CC   | Sell CC, Adjust Premium                                  |

#### Action Behaviors

- **Close CSP (Buy back):** Prompts for cost to close. Subtracts cost from premium.
  Records action `CLOSE_CSP`. Status stays `CSP`.
- **CSP Expires Without Assignment:** Records action `CSP_EXPIRED_UNASSIGNED`.
  Status stays `CSP`.
- **CSP Expires With Assignment:** Prompts for assignment strike.
  Records action `CSP_ASSIGNED`. Status becomes `COVERED CALLS`.
- **Keep Stocks:** Records action `KEEP_SHARES`. Status becomes `READY FOR CC`.
- **Sell CC:** Records action `SELL_CC`. Status becomes `CC OPEN`.
  Shows instructions to go to Add Trade page.
- **Adjust Premium:** Prompts for adjustment amount (positive or negative delta).
  Applies delta to `premium_collected` and recalculates `cost_basis`.
  Records action `ADJUST_PREMIUM`.
- **Wait for Expiration:** Shows informational message only. No state change.

### 10.4 Action History

Collapsible expander showing the `position_actions` history for the selected symbol.
Columns: `action_date, action_type, previous_status, new_status, adjusted_premium, notes`

### 10.5 Premium by Symbol Chart

Bar chart of `premium_collected` per symbol.

---

## 11. Assignments Page

Read-only view of all assignment events.

### 11.1 Summary Metrics

| Metric             | Calculation                                                   |
|--------------------|---------------------------------------------------------------|
| Assignment Events  | Total count of assignment records                             |
| Shares Assigned    | Sum of `shares` where `shares > 0` (PUT assignments)          |
| Shares Called Away | Sum of abs(`shares`) where `shares < 0` (CALL assignments)    |
| Net Stock Basis    | Sum of `net_stock_basis` across all assignments               |
| Total Fees         | Sum of `broker_fee` across all assignment records             |

### 11.2 Assignment Ledger Table

Columns: `id, trade_id, symbol, assignment_date, strategy, assignment_type,
strike, premium, contracts, broker_fee, shares, stock_value, premium_value, net_stock_basis, notes`

Money columns formatted as `$X,XXX.XX`: `strike, premium, broker_fee, stock_value, premium_value, net_stock_basis`

---

## 12. Covered Calls Page

Read-only view of all covered call lifecycle events.

### 12.1 Summary Metrics

| Metric       | Calculation                                            |
|--------------|--------------------------------------------------------|
| Open Calls   | Count where `lifecycle_stage == "OPEN"`                |
| Closed Calls | Count where `lifecycle_stage == "CLOSED"`              |
| Expired Calls | Count where `lifecycle_stage == "EXPIRED"`            |
| Called Away  | Count where `lifecycle_stage == "CALLED AWAY"`         |
| CC Premium   | Sum of `premium_value` (net, fee-adjusted)             |
| Total Fees   | Sum of `broker_fee` across all CC lifecycle records    |

### 12.2 Lifecycle Ledger Table

Columns: `id, trade_id, symbol, cycle_number, trade_date, expiration, action,
lifecycle_stage, strike, premium, contracts, broker_fee, shares_covered, premium_value, notes`

Money columns formatted as `$X,XXX.XX`: `strike, premium, broker_fee, premium_value`

---

## 13. Architecture Constraints

### 13.1 Module Boundaries

| Module                              | Responsibility                                             | May import               |
|-------------------------------------|------------------------------------------------------------|--------------------------|
| `config.py`                         | Paths and constants only                                   | stdlib only              |
| `models.py`                         | Dataclasses for Trade, Position, Assignment, PluginResult, etc. | stdlib only         |
| `database.py`                       | DB connection and schema initialization only               | config                   |
| `repository.py`                     | All SQL queries. No business logic.                        | config, models, database |
| `engine.py`                         | Plugin registry + recalculation orchestration. No SQL.     | models, strategies/*     |
| `strategies/base.py`                | `StrategyPlugin` abstract base class and `PluginResult`    | models                   |
| `strategies/wheel/engine.py`        | Wheel-specific position state machine                      | models, strategies/base  |
| `strategies/wheel/calculations.py`  | Wheel-specific pure math functions                         | stdlib, pandas           |
| `strategies/<name>/engine.py`       | Future strategy state machine (same interface)             | models, strategies/base  |
| `calculations.py`                   | Shared pure math functions (premium, DTE, etc.)            | stdlib, pandas           |
| `importers/base.py`                 | `StrategyImporter` abstract base class                     | models                   |
| `importers/ib_importer.py`          | IB CSV parsing. Dispatches to per-strategy importers.      | stdlib, models           |
| `importers/wheel/ib_importer.py`    | Wheel-specific IB row parsing                              | stdlib, models           |
| `charts/`                           | Chart creation functions only                              | plotly, pandas           |
| `views/`                            | Streamlit UI rendering only                                | everything above         |
| `views/strategies/<name>/`          | Strategy-specific pages (positions, lifecycle, etc.)       | strategies/*, views/     |
| `app.py`                            | Entry point. Wires pages together.                         | streamlit, views         |

### 13.2 Strategy Isolation

Each strategy is fully contained in `strategies/<name>/`. It must not import from
another strategy's package. Shared logic lives in `calculations.py` or `models.py`.

### 13.3 No Business Logic in Views

Views call repository and engine functions. They do not contain calculation logic,
SQL, or position state transitions.

### 13.4 No SQL Outside Repository

All SQL queries live in `repository.py`. Plugins receive plain Python objects
(dataclasses or dicts), not database connections.

### 13.5 Pure Functions in Engines and Calculations

`engine.py`, `strategies/*/engine.py`, and `calculations.py` functions take inputs
and return outputs with no side effects. This makes them unit-testable without a database.

### 13.6 Adding a New Strategy

To add a new strategy, a contributor must:

1. Create `strategies/<name>/engine.py` implementing `StrategyPlugin`
2. Create `strategies/<name>/calculations.py` for strategy-specific math (if any)
3. Create `importers/<name>/` for any broker-specific import logic (if needed)
4. Create `views/strategies/<name>/` for the strategy's UI pages
5. Register the plugin in `engine.py`: add one entry to `STRATEGY_PLUGINS`
6. Register the views in `app.py`: add the pages to the navigation

No existing module outside `engine.py` and `app.py` needs to be modified.

---

## 14. Test Requirements

### 14.1 What Must Be Tested

| Module                           | Test focus                                                                   |
|----------------------------------|------------------------------------------------------------------------------|
| `calculations.py`                | Premium cashflow sign (SELL vs BUY), net_premium_value with and without broker_fee, DTE computation, total premium |
| `strategies/wheel/engine.py`     | CSP open/closed/expired/assigned, CC open/closed/expired/called away, cost basis reduction uses net_premium_value, cycle number increment, shares floor at 0, total_fees_paid accumulation, broker_fee propagated to Assignment and lifecycle events |
| `strategies/wheel/calculations.py` | Wheel-specific math if any                                                 |
| `strategies/base.py`             | Plugin interface contract: all required methods present and typed correctly  |
| `importers/ib_importer.py`       | Option symbol parsing (P and C), date parsing, action mapping, assignment row handling, stock row warnings, duplicate detection, Commission column mapped to broker_fee as positive float |
| `repository.py`                  | CRUD operations using an in-memory SQLite database                           |

### 14.2 What Is Not Unit Tested

Streamlit view functions are not unit tested. Acceptance is done by manual review.

### 14.3 Test Framework

`pytest`. Tests live in a `tests/` directory at the project root.
Each module has a corresponding test file: `tests/test_calculations.py`,
`tests/strategies/test_wheel_engine.py`, etc.

---

## 15. Configuration

| Constant   | Value                              | Description               |
|------------|------------------------------------|---------------------------|
| `BASE_DIR` | `Path(__file__).parent`            | Project root directory    |
| `DATA_DIR` | `BASE_DIR / "data"`                | Directory for SQLite file |
| `DB_NAME`  | `DATA_DIR / "tracker.db"`          | SQLite database path      |

---

## 16. Build & Run

- **Run:** `streamlit run app.py`
- **Dependencies:** `streamlit`, `pandas`, `plotly`, `openpyxl`
- **Python:** 3.11+
- **Database:** SQLite, file-based, auto-created on first run
