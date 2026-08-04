# Order View Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Make order-card updates atomic from the user's point of view so adding a take-profit order never exposes a clipped or folded order group.

**Architecture:** Keep card rendering in `StockCard`, and make `MainWindow` responsible only for capturing and restoring viewport state. Remove the `minimumHeight` padding and scroll animation from ordinary order mutations; restore the anchor after the replacement layout reaches its natural scrollbar range. Explicit navigation may still position a card at the top, but it must clamp to the actual scrollbar maximum.

**Tech Stack:** Python 3.11, PySide6, pytest-qt, SQLite-backed `AppService` fixtures.

---

### Task 1: Add failing regression coverage

**Files:**
- Modify: `tests/test_ui_actions.py`
- Modify: `tests/test_ui_smoke.py`

- [ ] Add a test with the fixture service that selects `300251.SZ`, adds a third `sell_profit` order, processes the event loop at the immediate and settled checkpoints, and asserts every `OrderRow` keeps its full height and its input/confirm/delete children remain inside the row.
- [ ] Add a test asserting a single-card order update does not increase `stock_content.minimumHeight` beyond the natural layout height and does not animate the vertical scrollbar.
- [ ] Run the targeted tests and verify they fail against the current implementation for the new invariants.

### Task 2: Remove artificial range mutation from order updates

**Files:**
- Modify: `src/ptrade_order_tool/ui/main_window.py` near `_refresh_after_single_stock_order_update`, `_reserve_stock_scroll_range`, and `_restore_stock_scroll_anchor_after_layout`.

- [ ] Keep anchor capture, but stop calling `_reserve_stock_scroll_range` for single-card order updates.
- [ ] Replace the deferred animation with one post-layout restoration that clamps the desired value to the current scrollbar range and assigns it directly.
- [ ] Ensure the replacement path activates `stock_layout` and updates geometry before reading the new card position.
- [ ] Preserve ordinary selection/filter state and keep explicit stock-jump positioning bounded by the natural scrollbar maximum.

### Task 3: Make the newly added row usable

**Files:**
- Modify: `src/ptrade_order_tool/ui/main_window.py`
- Modify: `tests/test_ui_actions.py`

- [ ] Identify the newly added order in the updated stock draft, locate its `OrderRow`, and call `ensureWidgetVisible` only when the row is outside the viewport.
- [ ] Focus the first editable price digit for a newly added order without moving a card that is already fully visible.
- [ ] Add assertions for the new row's visibility and focus target.

### Task 4: Verify all view-management paths

**Files:**
- Modify: `tests/test_ui_actions.py` only if an uncovered path needs a focused regression test.

- [ ] Run the new targeted tests and the existing order/scroll tests.
- [ ] Run the full suite with `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q` and require zero failures.
- [ ] Run `git diff --check`, inspect the final diff, and confirm only the planned UI, test, and plan/spec files changed.
