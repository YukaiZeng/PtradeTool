# Prefixed JSON Filenames Implementation Plan

> **For agentic workers:** Execute the tasks in order with test-first checkpoints. This change intentionally removes legacy filename compatibility after migration.

**Goal:** Switch all PTrade and order JSON files from bare date names to `ptrade_YYYYMMDD.json` and `order_YYYYMMDD.json`, migrate existing configured-directory files safely, and keep SQLite paths consistent.

**Architecture:** Add one filename/migration module containing prefix constants, strict filename builders, and an atomic legacy-file migration result. `AppService` runs migration when configured and rewrites matching `sessions` paths; all desktop finders then accept only prefixed names. The PTrade runtime script uses the same literal protocol directly because it runs in the external PTrade environment.

**Tech Stack:** Python, pathlib, SQLite, PySide6, pytest.

---

### Task 1: Filename and migration contracts

**Files:**
- Create: `src/ptrade_order_tool/data/file_naming.py`
- Test: `tests/test_file_naming.py`

- [ ] Add tests for prefixed builders, strict date parsing, legacy rename, identical collision cleanup, and conflicting collision preservation.
- [ ] Implement atomic same-directory rename using `Path.replace`, with no overwrite on differing target content.
- [ ] Return explicit moved/conflict mappings so the service can repair persisted database paths and log conflicts.

### Task 2: Desktop path protocol and persisted paths

**Files:**
- Modify: `src/ptrade_order_tool/app_service.py`
- Modify: `src/ptrade_order_tool/bootstrap.py`
- Test: `tests/test_startup_flow.py`, `tests/test_app_service_actions.py`, `tests/test_draft_store.py`, `tests/test_settings_and_history.py`

- [ ] Change all desktop builders/finders/inheritance paths to prefixed names and strict prefix-specific regexes.
- [ ] Run configured-directory migration during service setup and after directory configuration changes.
- [ ] Rewrite exact old `sessions.ptrade_json_path` and `sessions.export_json_path` values using migration mappings before normal loads.
- [ ] Ensure latest/earliest date extraction uses the date captured from the prefixed filename, not `Path.stem`.

### Task 3: Runtime and documentation protocol

**Files:**
- Modify: `src/ptrade_order_tool/runtime/in-app.py`
- Modify: `README.md`
- Test: `tests/test_runtime_contract.py`

- [ ] Read `order_YYYYMMDD.json` and write `ptrade_YYYYMMDD.json` in the runtime script.
- [ ] Update runtime log paths and user documentation.
- [ ] Do not retain fallback reads or writes for bare date filenames.

### Task 4: Regression verification

**Files:**
- Modify: all affected tests and fixtures paths only.

- [ ] Replace test-created protocol paths with prefixed paths.
- [ ] Run targeted migration/finder/runtime tests.
- [ ] Run full pytest, compileall, and `git diff --check`.
- [ ] Leave changes local and unpushed; do not run the Windows packaging script.
