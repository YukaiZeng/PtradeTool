# Pullback Inheritance and Digit Alignment Implementation Plan

> **For agentic workers:** Execute tasks in order with test-first checkpoints. Keep changes local for this iteration; do not commit, push, or package.

**Goal:** Carry a failed prior-trading-day pullback-buy plan into the new draft and restore natural digit spacing once every order input returns to the same width.

**Architecture:** `DraftStore` will retain the existing three-trading-day holding sell-order loader and add a separate, single-file pullback-plan loader. `StockCard` will clear each input's visual-width override when all inputs of a kind share the same natural width.

**Tech Stack:** Python, SQLite, PySide6, pytest.

---

### Task 1: Pullback-buy inheritance

**Files:**
- Modify: `src/ptrade_order_tool/data/draft_store.py`
- Test: `tests/test_draft_store.py`

- [x] Add a failing test that imports a date with no holding for a stock whose immediately preceding order JSON contains `buy_limit`, `sell_profit`, and `sell_loss`; assert the new draft contains a non-holding stock with all three inherited, unconfirmed orders.
- [x] Add a failing test that proves an active current holding does not receive a duplicate inherited `buy_limit` while retaining the current sell-order inheritance behavior.
- [x] Implement a dedicated previous-file loader which accepts only valid `buy_limit` bundles, copies same-file `sell_profit`/`sell_loss` entries, and inserts the stock into `draft_stocks` before adding inherited orders.
- [x] Run `python -m pytest -q tests/test_draft_store.py` and verify all tests pass.

### Task 2: Strict previous-day selection

**Files:**
- Modify: `src/ptrade_order_tool/app_service.py`
- Test: `tests/test_startup_flow.py`

- [x] Add a failing startup test with a pullback plan only in the second-previous order file; assert no non-holding plan is inherited for the new date.
- [x] Pass the immediate prior order path separately from the existing three-path holding inheritance list.
- [x] Run `python -m pytest -q tests/test_startup_flow.py` and verify all tests pass.

### Task 3: Natural-width recovery

**Files:**
- Modify: `src/ptrade_order_tool/ui/stock_card.py`
- Test: `tests/test_ui_smoke.py`

- [x] Add a failing multi-row test: increase every row's price and share width, delete each added highest digit, then assert visual widths equal natural widths and no alignment placeholders remain.
- [x] Update stock-card alignment to clear the visual-width override for an input kind once all natural widths are equal; preserve maximum-width alignment otherwise.
- [x] Run `python -m pytest -q tests/test_ui_smoke.py` and verify all tests pass.

### Task 4: Final verification

**Files:**
- Verify: `tests/`

- [x] Run `python -m pytest -q`.
- [x] Run `python -m compileall -q src tests`.
- [x] Run `git diff --check`.
