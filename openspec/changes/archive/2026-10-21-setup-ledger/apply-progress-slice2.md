# Apply Progress — setup-ledger (Slice 2)

**Mode**: Strict TDD · **Branch**: `feat/setup-ledger-capture` (off `feat/setup-ledger-core`)
**Scope**: Phase 3 (3.1–3.4) + Phase 4 gates (4.1–4.2). Delivery: chained PR slice 2 of a
feature-branch-chain, per accepted `size:exception` fallback (S2 ≈ 164 lines vs 400 budget).

## Task Status

| Task | Status | Evidence |
|------|--------|----------|
| 3.1 RED `tests/web/test_setups_capture.py` | ✅ | 12 tests; ran RED — `ModuleNotFoundError: No module named 'trading.setups'` |
| 3.2 GREEN `web/trading/setups.py` | ✅ | `capture_intervals` + `run_setup_capture`; 12 passed |
| 3.3 RED `tests/web/test_worker_setups.py` | ✅ | 3 tests; ran RED — 3 failed (no capture step) |
| 3.4 GREEN isolated step in `worker.run_once` | ✅ | import inside `try`; 3 passed |
| 4.1 Gates | ✅ | ruff / format / makemigrations / pytest all exit 0 |
| 4.2 Guards | ✅ | `test_no_order_surface` + `test_owned_model_guard` 61 passed, unedited |

## TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR |
|------|-----|-------|----------|
| 3.1 → 3.2 | `pytest tests/web/test_setups_capture.py` → 11 errors + 1 passed (module missing) | 12 passed after creating `web/trading/setups.py` | ruff I001 import-order fix; removed redundant autouse fixture, switched to `pytestmark = pytest.mark.django_db` |
| 3.3 → 3.4 | `pytest tests/web/test_worker_setups.py` → 3 failed (no capture step, empty caplog) | 3 passed after adding the isolated `try` | dropped an unused `candles` import used only as a linter crutch |

## Files Changed

| File | Action | What |
|------|--------|------|
| `web/trading/setups.py` | Created | Env parsing/validation, `_db_rows` read, `capture_setups` call, `bulk_create(ignore_conflicts=True)`, `engine_version` stamped here |
| `web/worker.py` | Modified | +11 lines: isolated capture `try/except` immediately after the candle block, import INSIDE the `try` (D3) |
| `tests/web/test_setups_capture.py` | Created | Seam contract: one row, idempotency, version bump, thin/empty window, ATR anchor, bad env, zero network |
| `tests/web/test_worker_setups.py` | Created | Ordering after candles, failure isolation, bad-config degradation, `(funding, ticker)` contract |

## Deviations from Design

- **None functional.** `run_setup_capture` takes `symbols` and uses it directly (the in-scope
  variable in `run_once` is `symbols`). Signature unchanged.
- `_records()` helper factors the per-pair window read out of the loop (keeps `run_once`-style
  flatness and stays under ruff's complexity expectations); no new public surface.
- Version bump test monkeypatches the module-level `SMC_ENGINE_VERSION` **name in
  `trading.setups`** (the stamping site), matching R4's "stamped at persistence time".

## Gate Output

| Command | Exit | Output |
|---------|------|--------|
| `.venv/bin/ruff check .` | 0 | `All checks passed!` |
| `.venv/bin/ruff format --check .` | 0 | `170 files already formatted` |
| `.venv/bin/python web/manage.py makemigrations --check --dry-run` | 0 | `No changes detected` |
| targeted pytest (7 files) | 0 | `91 passed in 27.73s` |
| `test_no_order_surface.py` + `test_owned_model_guard.py` | 0 | `61 passed` |
| full suite (`pytest -p no:randomly`) | 0 | all green |

## Notes

- Zero network is enforced by test: `src.client.BitunixClient` replaces with a raising stub and
  `market.quotes._fetch_window` is patched to raise; the seam still persists one row.
- `_db_rows` returns `[]` for a non-`CANDLE_INTERVALS` interval, so an unpersisted interval
  degrades to zero rows without raising (spec edge matrix).
