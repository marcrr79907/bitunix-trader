# Tasks: setup-ledger

Strict TDD: each RED task writes its failing assertion first. `[S1]`/`[S2]` = slice. `(n)` = changed lines.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 429 (S1 265 + S2 164) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 = Slice 1, PR 2 = Slice 2 |

Decision needed before apply: No (resolved: feature-branch-chain)
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Base |
|------|------|----|------|
| Tracker | `feat/setup-ledger` accumulate | — | `develop` |
| 1 | Pure core + model + `0018` | 1 | tracker |
| 2 | Seam + worker | 2 | PR 1 branch |

## Phase 1: Pure core — Slice 1

- [x] 1.1 `[S1]` RED: `tests/test_smc_capture.py` — `SMC_ENGINE_VERSION` non-empty `str`, `capture_setups` exists; import fails (70)
- [x] 1.2 `[S1]` GREEN: add `SMC_ENGINE_VERSION = "1"` to `src/smc/config.py` (3)
- [x] 1.3 `[S1]` RED: `anchor_time == times[i]`, `atr` vs `src.indicators.atr`, `atr is None` in warm-up, `[]` on empty/mismatched, fields equal `find_setups`, determinism, no mutation (0)
- [x] 1.4 `[S1]` GREEN: add `SetupRecord` + `capture_setups(...)` to `src/smc/signals.py`; `Setup`/`find_setups` byte-identical (40)
- [x] 1.5 `[S1]` `test_boundary.py` green, NO edit (already in `PURE_MODULES`); `test_smc_signals.py` unmodified (0)

## Phase 2: Model + migration — Slice 1

- [x] 2.1 `[S1]` RED: `tests/web/test_setups_model.py` — no `user`, absent from `OWNED_MODELS`, unique key includes `engine_version`, index present, six excluded fields absent (55)
- [x] 2.2 `[S1]` GREEN: `Setup` in `web/trading/models.py` — plain `models.Model`, `engine_version` Char(16), `created_at` auto_now_add, unique `(symbol, interval, anchor_time, engine_version)`, matching index (30)
- [x] 2.3 `[S1]` RED: migration source has one `CreateModel` `Setup`, no destructive ops, depends on `0017_charttemplate` (0)
- [x] 2.4 `[S1]` GREEN: `makemigrations trading` → `web/trading/migrations/0018_setup.py` (52)
- [x] 2.5 `[S1]` Gate: `ruff check .`, `ruff format --check .`, `makemigrations --check --dry-run`, `python -m pytest` (0)

## Phase 3: Seam + worker — Slice 2

- [x] 3.1 `[S2]` RED: `tests/web/test_setups_capture.py` — one matching row; rerun = 0; version bump adds a row, old intact; `[]` = 0; bad env `ValueError` names offender; no client call (75)
- [x] 3.2 `[S2]` GREEN: `web/trading/setups.py` — `SETUP_CANDLE_WINDOW = 100`, intervals validated against `CANDLE_INTERVALS`, `run_setup_capture(symbols) -> int` via `_db_rows` + `capture_setups` + `bulk_create(ignore_conflicts=True)` (62)
- [x] 3.3 `[S2]` RED: `tests/web/test_worker_setups.py` — capture runs after candles; forced failure leaves funding/ticker/private/alerts green and the return tuple unchanged (30)
- [x] 3.4 `[S2]` GREEN: isolated `try/except` in `web/worker.py` after the candle block; imports INSIDE the `try` (D3); log `setup capture failed: %s` (12)

## Phase 4: Gates and archive

- [x] 4.1 `[S2]` Gate: `ruff check .`, `ruff format --check .`, `makemigrations --check --dry-run`, `python -m pytest` (0)
- [x] 4.2 `[S2]` `test_no_order_surface.py` + `test_owned_model_guard.py` green unedited; no new dependency (0)
- [ ] 4.3 Deferred: archive only after `sdd-verify` passes; `git add` selectively, never `-A` (0)

Conventional commits, no AI attribution. S1 (265) ships green alone; S2 (164) targets its branch.
