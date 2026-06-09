# Ptrade Order Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cross-platform PySide6 desktop tool that imports Ptrade after-hours JSON, lets the user prepare confirmed trading orders, and exports clean `order_data/YYYYMMDD.json` files for `in-app.py`.

**Architecture:** Use a Python desktop app with focused data modules and Qt UI modules. The data layer owns parsing, validation, Tushare caches, draft persistence, inheritance, and export; the UI layer only edits draft state through explicit services. SQLite stores stock basics, trade calendar, per-date drafts, order confirmation state, and export metadata.

**Tech Stack:** Python 3.11+, PySide6, SQLite, pytest, pydantic or dataclasses, python-dotenv, tushare, pypinyin, PyInstaller.

---

## File Structure

- Create `pyproject.toml`: package metadata, dependencies, pytest settings.
- Create `README.md`: run instructions, environment variables, expected data directories.
- Create `src/ptrade_order_tool/__init__.py`: package marker.
- Create `src/ptrade_order_tool/main.py`: app entry point.
- Create `src/ptrade_order_tool/config.py`: app config load/save and default user-data paths.
- Create `src/ptrade_order_tool/models.py`: typed dataclasses for fund, holdings, orders, warnings, drafts.
- Create `src/ptrade_order_tool/data/db.py`: SQLite schema creation and connection helper.
- Create `src/ptrade_order_tool/data/ptrade_importer.py`: parse and validate Ptrade after-hours JSON.
- Create `src/ptrade_order_tool/data/stock_master.py`: Tushare `stock_basic` cache, pinyin fields, search.
- Create `src/ptrade_order_tool/data/trade_calendar.py`: Tushare `trade_cal` cache and previous-trading-day lookup.
- Create `src/ptrade_order_tool/data/draft_store.py`: create/load/update latest editable draft and read-only historical drafts.
- Create `src/ptrade_order_tool/data/order_exporter.py`: validate draft and export clean order JSON.
- Create `src/ptrade_order_tool/ui/main_window.py`: main desktop window, top account strip, tabs/filter modules.
- Create `src/ptrade_order_tool/ui/stock_card.py`: per-stock unit with order groups and warnings.
- Create `src/ptrade_order_tool/ui/order_row.py`: one editable order row with confirm/delete/undo integration.
- Create `src/ptrade_order_tool/ui/digit_input.py`: custom digit input widget for price and shares.
- Create `tests/fixtures/ptrade_20260225.json`: copy of `/Users/mark/.Trash/Stock_0316/data/ptrade_data/20260225.json`.
- Create `tests/fixtures/order_20260224.json`: small previous-day order fixture for inheritance tests.
- Create `tests/test_ptrade_importer.py`: parser and account calibration tests.
- Create `tests/test_stock_master.py`: stock match and pinyin search tests.
- Create `tests/test_trade_calendar.py`: trading day and previous-day tests.
- Create `tests/test_draft_store.py`: draft creation, history read-only, confirmation state tests.
- Create `tests/test_order_exporter.py`: export schema and validation tests.

---

## Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/ptrade_order_tool/__init__.py`
- Create: `src/ptrade_order_tool/main.py`

- [ ] **Step 1: Add package metadata and dependencies**

Create `pyproject.toml` with:

```toml
[project]
name = "ptrade-order-tool"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "PySide6>=6.7",
  "python-dotenv>=1.0",
  "tushare>=1.4",
  "pypinyin>=0.51",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-qt>=4.4",
  "pyinstaller>=6.0",
]

[project.scripts]
ptrade-order-tool = "ptrade_order_tool.main:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Add a minimal entry point**

Create `src/ptrade_order_tool/main.py` with a `main()` function that starts a PySide6 `QApplication` and imports `MainWindow` from `ptrade_order_tool.ui.main_window`.

- [ ] **Step 3: Add initial README**

Document:
- how to install with `pip install -e ".[dev]"`
- how to run with `python -m ptrade_order_tool.main`
- where `.env` can live
- required `TUSHARE_TOKEN`
- expected `ptrade_data` and `order_data` directories

- [ ] **Step 4: Verify package import**

Run:

```bash
python3 -m pip install -e ".[dev]"
python3 -c "import ptrade_order_tool; print('ok')"
```

Expected: `ok`.

---

## Task 2: Models and Config

**Files:**
- Create: `src/ptrade_order_tool/models.py`
- Create: `src/ptrade_order_tool/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Define domain models**

Create dataclasses:
- `FundSnapshot(cash, positions_value, portfolio_value, stock_positions_value, calibrated_cash)`
- `Holding(ts_code, stock_code, stock_name, current_amount, enable_amount, last_price, cost_price, market_value, profit_ratio, income_balance)`
- `OrderDraft(order_type, price, shares, confirmed, source, warning)`
- `StockDraft(ts_code, stock_name, is_holding, holding, orders)`
- `SessionDraft(manage_date, expected_trade_date, fund, stocks, export_state)`

Use `Decimal` for prices and money fields where possible; convert to JSON floats only in exporter.

- [ ] **Step 2: Implement user data paths**

`config.py` should resolve:
- macOS: `~/Library/Application Support/PtradeOrderTool`
- Windows: `%APPDATA%/PtradeOrderTool`
- fallback: `~/.ptrade_order_tool`

The config file is `config.json` and stores:
- `ptrade_data_dir`
- `order_data_dir`
- `last_opened_manage_date`
- `window_geometry`

- [ ] **Step 3: Write config tests**

Test that config round-trips JSON and missing config returns empty defaults.

Run:

```bash
pytest tests/test_config.py -v
```

Expected: all tests pass.

---

## Task 3: SQLite Schema

**Files:**
- Create: `src/ptrade_order_tool/data/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Create schema initializer**

Create tables:
- `app_meta(key text primary key, value text not null)`
- `stock_basic(ts_code text primary key, symbol text, name text, name_pinyin text, name_initials text, list_status text, updated_on text)`
- `trade_calendar(cal_date text primary key, is_open integer not null, updated_on text)`
- `sessions(manage_date text primary key, expected_trade_date text, ptrade_json_path text, export_json_path text, export_state text, created_at text, updated_at text)`
- `fund_snapshots(manage_date text primary key, cash real, positions_value real, portfolio_value real, stock_positions_value real, calibrated_cash real)`
- `holdings(manage_date text, ts_code text, stock_code text, stock_name text, current_amount integer, enable_amount integer, last_price real, cost_price real, market_value real, profit_ratio real, income_balance real, is_stock integer, primary key(manage_date, ts_code))`
- `orders(id integer primary key autoincrement, manage_date text, ts_code text, stock_name text, order_type text, price real, shares integer, confirmed integer, source text, warning text, sort_order integer)`

- [ ] **Step 2: Test schema creation**

Open an in-memory SQLite connection, run schema creation, assert all expected tables exist.

Run:

```bash
pytest tests/test_db.py -v
```

Expected: all tests pass.

---

## Task 4: Ptrade JSON Importer

**Files:**
- Create: `tests/fixtures/ptrade_20260225.json`
- Create: `src/ptrade_order_tool/data/ptrade_importer.py`
- Test: `tests/test_ptrade_importer.py`

- [ ] **Step 1: Add fixture**

Copy `/Users/mark/.Trash/Stock_0316/data/ptrade_data/20260225.json` into `tests/fixtures/ptrade_20260225.json`.

- [ ] **Step 2: Write importer tests**

Cover:
- parses top-level `Fund` and `Hold`
- rejects missing `Fund`
- rejects missing `Hold`
- converts float amounts like `2800.0` to integer `2800`
- keeps `131990 标准券` as non-stock candidate before stock-master filtering
- computes calibrated account values from stock vs non-stock holdings

Expected calibrated values for fixture:
- `portfolio_value = 88381.86`
- `stock_positions_value = 55020.0`
- `calibrated_cash = 33361.86`

- [ ] **Step 3: Implement importer**

Implement `parse_ptrade_json(path, stock_matcher) -> ImportedPtradeData`.

Rules:
- `Fund.cash`, `Fund.positions_value`, `Fund.portfolio_value` are required.
- `Hold` must be a dict.
- a holding is stock only if `stock_matcher.resolve(ts_code_or_stock_code)` returns a Tushare stock.
- non-stock market value is added to calibrated cash.
- stock holdings are returned for the UI.

- [ ] **Step 4: Verify importer**

Run:

```bash
pytest tests/test_ptrade_importer.py -v
```

Expected: all tests pass.

---

## Task 5: Tushare Stock Master Cache and Search

**Files:**
- Create: `src/ptrade_order_tool/data/stock_master.py`
- Test: `tests/test_stock_master.py`

- [ ] **Step 1: Write tests with local stock rows**

Use rows:
- `002153.SZ`, `002153`, `石基信息`
- `300162.SZ`, `300162`, `雷曼光电`
- `300251.SZ`, `300251`, `光线传媒`

Assert searches:
- `002153` finds 石基信息
- `002153.SZ` finds 石基信息
- `石基` finds 石基信息
- `shijixinxi` finds 石基信息
- `sjxx` finds 石基信息
- `131990` does not match

- [ ] **Step 2: Implement cache and pinyin generation**

Implement:
- `upsert_stock_basic(rows)`
- `resolve_stock(query)`
- `search_stocks(query, limit=20)`
- `needs_update(today, is_trade_day, has_any_stock_data)`

Button state outputs:
- `generate` when no local data
- `update_enabled` when trade day and not updated
- `updated_disabled` when updated today
- `update_disabled_non_trade_day` when non-trading day and cache exists

- [ ] **Step 3: Implement Tushare fetch wrapper**

Read token from:
- environment variable `TUSHARE_TOKEN`
- `.env` in executable directory
- `.env` in user data directory

If missing token, raise a user-facing `MissingTushareToken` exception.

- [ ] **Step 4: Verify stock master**

Run:

```bash
pytest tests/test_stock_master.py -v
```

Expected: all tests pass.

---

## Task 6: Trade Calendar Cache

**Files:**
- Create: `src/ptrade_order_tool/data/trade_calendar.py`
- Test: `tests/test_trade_calendar.py`

- [ ] **Step 1: Write calendar tests**

Use local rows:
- `20260223 is_open=1`
- `20260224 is_open=1`
- `20260225 is_open=1`
- `20260226 is_open=1`
- `20260228 is_open=0`

Assert:
- `is_trade_day("20260225") is True`
- `is_trade_day("20260228") is False`
- `previous_trade_day("20260225") == "20260224"`

- [ ] **Step 2: Implement cache**

Implement:
- `upsert_trade_calendar(rows)`
- `is_trade_day(date_str)`
- `previous_trade_day(date_str)`
- `ensure_calendar_coverage(today)`

- [ ] **Step 3: Verify calendar**

Run:

```bash
pytest tests/test_trade_calendar.py -v
```

Expected: all tests pass.

---

## Task 7: Draft Creation and Inheritance

**Files:**
- Create: `src/ptrade_order_tool/data/draft_store.py`
- Create: `tests/fixtures/order_20260224.json`
- Test: `tests/test_draft_store.py`

- [ ] **Step 1: Add previous order fixture**

Create `tests/fixtures/order_20260224.json` with:

```json
{
  "002153.SZ": {
    "stock_name": "石基信息",
    "sell_profit": [{"price": 12.65, "shares": 2800}],
    "sell_loss": [{"price": 10.99, "shares": 2800}],
    "buy_limit": [{"price": 11.4, "shares": 1400}]
  }
}
```

- [ ] **Step 2: Write draft tests**

Assert:
- creating a draft for `20260225` imports holdings.
- if `order_data/20260224.json` exists, only `sell_profit` and `sell_loss` are inherited.
- inherited order quantity is adjusted to current `enable_amount`.
- inherited orders are `confirmed = false`.
- `buy_limit` and `buy_stop` are not inherited.
- opening an existing draft does not overwrite edited orders.
- older dates are read-only when a newer manage date exists.

- [ ] **Step 3: Implement draft store**

Implement:
- `create_or_open_latest_draft(ptrade_json_path)`
- `reimport_draft(manage_date, ptrade_json_path)`
- `load_draft(manage_date)`
- `save_order_change(order_id, price, shares, order_type)` and set `confirmed=false`
- `confirm_order(order_id)`
- `delete_order(order_id)`
- `restore_deleted_order(snapshot)`
- `is_read_only(manage_date)`

- [ ] **Step 4: Verify drafts**

Run:

```bash
pytest tests/test_draft_store.py -v
```

Expected: all tests pass.

---

## Task 8: Export Validation and Clean JSON Writer

**Files:**
- Create: `src/ptrade_order_tool/data/order_exporter.py`
- Test: `tests/test_order_exporter.py`

- [ ] **Step 1: Write validation tests**

Cover:
- clean export contains only `stock_name` and `price/shares`.
- stocks with no confirmed orders are omitted.
- any unconfirmed order blocks export.
- invalid price blocks export.
- invalid share count blocks export.
- holding `sell_profit` total mismatch creates warning, not block.
- holding `sell_loss` total mismatch creates warning, not block.
- opening stock sell totals different from buy totals creates warning, not block.
- overwrite existing file requires explicit `allow_overwrite=True`.

- [ ] **Step 2: Implement exporter**

Implement:
- `validate_export(draft) -> ExportValidation(blockers, warnings)`
- `build_order_json(draft) -> dict`
- `export_order_json(draft, output_path, allow_overwrite=False)`

Order groups:
- `buy_stop`
- `buy_limit`
- `sell_profit`
- `sell_loss`

Each exported order item:

```json
{"price": 12.65, "shares": 2800}
```

- [ ] **Step 3: Verify exporter**

Run:

```bash
pytest tests/test_order_exporter.py -v
```

Expected: all tests pass.

---

## Task 9: Digit Input Widget

**Files:**
- Create: `src/ptrade_order_tool/ui/digit_input.py`
- Test: `tests/test_digit_input.py`

- [ ] **Step 1: Write widget tests**

Use `pytest-qt` to assert:
- price input starts as `0000.00`
- share input starts as `0000`
- adding one high digit shifts integer digits right.
- deleting an added high digit shifts back.
- keyboard entry fills visible digits left to right.
- share input rejects non-zero tens and ones on confirmation.
- price value serializes to two decimals.

- [ ] **Step 2: Implement widget**

Implement:
- `DigitInput(kind="price" | "shares")`
- `value()`
- `set_value(value)`
- `add_high_digit()`
- `remove_high_digit()`
- digit click popup for `0-9`
- drag/wheel digit changes
- emits `valueChanged`

- [ ] **Step 3: Verify digit input**

Run:

```bash
pytest tests/test_digit_input.py -v
```

Expected: all tests pass.

---

## Task 10: Main Qt UI

**Files:**
- Create: `src/ptrade_order_tool/ui/main_window.py`
- Create: `src/ptrade_order_tool/ui/stock_card.py`
- Create: `src/ptrade_order_tool/ui/order_row.py`
- Test: `tests/test_ui_smoke.py`

- [ ] **Step 1: Implement main window shell**

Main window includes:
- top account strip: total, stock market value, calibrated cash.
- stock-basic update button with four states.
- date label and export state label.
- tabs or segmented control: `全部`, `开仓`, `持仓`.
- scrollable stock-card area.
- export button.

- [ ] **Step 2: Implement stock card**

Each stock card includes:
- header: `ts_code + stock_name`
- holding summary if holding.
- order groups by type with color:
  - breakthrough buy
  - pullback buy
  - profit sell
  - loss sell
- warning chips for mismatched quantities.

- [ ] **Step 3: Implement order row**

Each row includes:
- order type selector
- price digit input
- shares digit input
- confirm button
- delete button
- temporary undo message after delete

- [ ] **Step 4: Implement UI smoke tests**

Test that the main window opens with a fixture draft and renders:
- account totals
- three stock cards from the fixture
- no card for `131990 标准券`

- [ ] **Step 5: Verify UI**

Run:

```bash
pytest tests/test_ui_smoke.py -v
```

Expected: all tests pass.

---

## Task 11: App Startup Flow

**Files:**
- Modify: `src/ptrade_order_tool/main.py`
- Modify: `src/ptrade_order_tool/ui/main_window.py`
- Test: `tests/test_startup_flow.py`

- [ ] **Step 1: Write startup tests**

Assert:
- latest valid `ptrade_data/YYYYMMDD.json` is selected.
- existing draft is opened, not overwritten.
- no configured directory opens empty state.
- manual reimport replaces current draft only after explicit confirmation.

- [ ] **Step 2: Implement startup orchestration**

On launch:
- load config.
- start async stock-basic/calendar update.
- find latest Ptrade JSON in configured directory.
- create or open latest draft.
- render draft in UI.

- [ ] **Step 3: Verify startup**

Run:

```bash
pytest tests/test_startup_flow.py -v
```

Expected: all tests pass.

---

## Task 12: Packaging

**Files:**
- Create: `scripts/build_macos.sh`
- Create: `scripts/build_windows.ps1`
- Create: `ptrade-order-tool.spec`

- [ ] **Step 1: Add PyInstaller spec**

Configure:
- entry: `src/ptrade_order_tool/main.py`
- app name: `PtradeOrderTool`
- include package data if added.

- [ ] **Step 2: Add macOS build script**

Run:

```bash
pyinstaller ptrade-order-tool.spec --clean --noconfirm
```

- [ ] **Step 3: Add Windows build script**

Run:

```powershell
pyinstaller ptrade-order-tool.spec --clean --noconfirm
```

- [ ] **Step 4: Verify local packaging path**

On macOS, run:

```bash
bash scripts/build_macos.sh
```

Expected: `dist/PtradeOrderTool.app` exists and launches.

---

## Task 13: End-to-End Manual Verification

**Files:**
- Use: `/Users/mark/.Trash/Stock_0316/data/ptrade_data/20260225.json`
- Use: generated SQLite database in user-data directory

- [ ] **Step 1: Start the app**

Run:

```bash
python3 -m ptrade_order_tool.main
```

Expected:
- latest `20260225` draft opens.
- top account strip shows total `88381.86`, stock market value `55020.00`, calibrated cash `33361.86`.
- stock list shows 石基信息, 雷曼光电, 光线传媒.
- standard bond `131990 标准券` is not shown.

- [ ] **Step 2: Add and confirm orders**

For 石基信息:
- add `sell_profit` price `12.65`, shares `2800`, confirm.
- add `sell_loss` price `10.99`, shares `2800`, confirm.
- add `buy_limit` price `11.40`, shares `1400`, confirm.

- [ ] **Step 3: Export**

Export to `order_data/20260225.json`.

Expected JSON:

```json
{
  "002153.SZ": {
    "stock_name": "石基信息",
    "buy_limit": [{"price": 11.4, "shares": 1400}],
    "sell_profit": [{"price": 12.65, "shares": 2800}],
    "sell_loss": [{"price": 10.99, "shares": 2800}]
  }
}
```

- [ ] **Step 4: Validate with `in-app.py` expectations**

Run:

```bash
python3 -m json.tool order_data/20260225.json
```

Expected: valid JSON with only `stock_name` and order `price/shares`.

---

## Self-Review

- Spec coverage: covered desktop app, Ptrade import, account calibration, Tushare stock cache, trade calendar, stock search, draft persistence, historical read-only behavior, inheritance, order confirmation, digit input, warnings/blockers, export format, and packaging.
- Placeholder scan: no `TBD`, `TODO`, or undefined future requirements are intentionally left in the task list.
- Type consistency: order types are consistently `buy_stop`, `buy_limit`, `sell_profit`, `sell_loss`; dates use `YYYYMMDD`; exported JSON excludes all internal draft fields.
