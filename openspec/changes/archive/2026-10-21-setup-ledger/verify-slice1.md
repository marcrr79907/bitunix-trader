```yaml
schema: gentle-ai.verify-result/v1
change: setup-ledger
scope: slice-1
evidence_revision: c6029a0b0c75002a3a703c440224b6d229b42ade
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 7/9
scenarios: 12/14
test_command: ".venv/bin/python -m pytest tests/test_smc_capture.py tests/test_smc_signals.py tests/test_smc_zones.py tests/test_smc_range.py tests/test_smc_structure.py tests/test_boundary.py tests/test_dependency_guard.py tests/web/test_setups_model.py tests/web/test_owned_model_guard.py tests/web/test_no_order_surface.py -p no:randomly"
test_exit_code: 0
test_output_hash: sha256:f47f8f82bac5314f1258e2a276d85972219915661f7442e3a446707fc8647cd5
build_command: ".venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py makemigrations --check --dry-run"
build_exit_code: 0
build_output_hash: sha256:23f821f9b71bea72c1d9c4313b8a84a589e882d0a96bf0c4a21dc3cf1859508c
```

# Verification Report — setup-ledger (Slice 1)

**Change**: setup-ledger · **Branch**: `feat/setup-ledger-core` (2 commits on `develop`) · **Mode**: Strict TDD
**Scope**: Phase 1 + Phase 2 (tasks 1.1–2.5). Phase 3/4 are Slice 2 → **out of scope, not counted as failures**.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks in scope (P1+P2) | 10 |
| Tasks complete | 10 |
| Tasks incomplete | 0 |
| Out of scope (P3+P4) | 7 (Slice 2) |

## Build & Tests Execution

**.venv/bin/ruff check .** → exit 0, `All checks passed!`
**.venv/bin/ruff format --check .** → exit 0, `167 files already formatted`
**.venv/bin/python web/manage.py makemigrations --check --dry-run** → exit 0, `No changes detected`
**`.venv/bin/python web/manage.py check`** → exit 0, `System check identified no issues (0 silenced).`
**`.venv/bin/python web/manage.py migrate --plan`** → `trading.0018_setup — Create model Setup` (additive leaf)

**Targeted tests** (10 files, run order matters — see W1) → **177 passed, exit 0**.
Per-file standalone: capture 13, setups_model 15, smc_signals 18, zones 27, range 12, structure 21, boundary 4, owned_model_guard 25, no_order_surface 36, dependency_guard 6.
Coverage of changed `src/` files: `src/smc/config.py` 100%, `src/smc/signals.py` 92% (all 8 misses are pre-existing `find_setups` branches; `capture_setups` is fully covered). `web/trading/models.py` not instrumented (Django import path).

## Spec Compliance Matrix

### `smc-setup-ledger`

| Req | Scenario | Evidence | Result |
|-----|----------|----------|--------|
| R1 | Global and minimal | `tests/web/test_setups_model.py::test_setup_is_global_not_owned` (bases = `(Model,)`, no `user`), `test_setup_is_absent_from_owned_models` (AST-reads `OWNED_MODELS`, 10 names, no `Setup`), `test_excluded_fields_are_absent` (6 params). Static: field types match spec exactly (`symbol` 32, `interval`/`direction` 8, `anchor_time` BigInteger, 4 Floats, score PositiveSmallInteger, `atr` null, `engine_version` 16, `created_at` auto_now_add). | ✅ COMPLIANT (type-set assertion gap → S1) |
| R1 | One row per anchor per engine | Unique key `(symbol, interval, anchor_time, engine_version)` asserted by `test_unique_constraint_fields_include_engine_version`; actual DB conflict-ignore behavior is exercised only in Slice 2. | ⚠️ PARTIAL |
| R1 | Index present | `test_symbol_interval_anchor_index_exists` + `_meta.indexes == [('ix_setup_sym_int_anchor', [...])]` | ✅ COMPLIANT |
| R2 | Migration green | `test_migration_creates_only_the_setup_model` (exactly 1 `CreateModel` named `Setup`), `test_migration_is_additive_no_alter_or_delete`, `test_migration_depends_on_0017`, `test_trading_leaf_is_at_least_0018` (uses `>=`), + `makemigrations --check` exit 0 | ✅ COMPLIANT |
| R3 | No backfill surface | `git diff develop --stat` = 6 files, none a command or worker step; no `setup` management command exists | ✅ COMPLIANT |
| R4 | Constant | `test_engine_version_is_a_non_empty_string`; `SMC_ENGINE_VERSION = "1"` at `src/smc/config.py:16`; model column `Char(16)` asserted (`test_engine_version_and_atr_columns`) | ✅ COMPLIANT |
| R4 | Mixed engines coexist | Stamping happens in the Slice 2 seam; `SMC_ENGINE_VERSION` is referenced nowhere in `web/` yet | ➖ NOT YET APPLICABLE |
| R5 | All scenarios | Seam `web/trading/setups.py` does not exist (Slice 2) | ➖ OUT OF SCOPE |
| R6 | Purity/boundary | `tests/test_boundary.py` green unmodified (`smc/signals.py` already in `PURE_MODULES`); imports = stdlib + `src.*` only; no clock, open, or network in signals.py | ✅ COMPLIANT |
| R6 | No order surface | `test_no_order_surface.py` 36 passed, unmodified | ✅ COMPLIANT |
| R6 | Failure containment / degradation (worker) | Worker step is Slice 2; helper-level `[]` degradation covered below | ➖ OUT OF SCOPE |

### `smc-signals` delta

| Req | Scenario | Evidence | Result |
|-----|----------|----------|--------|
| R6 | Constant importable and stable | `test_smc_capture.py::test_engine_version_is_a_non_empty_string` | ✅ COMPLIANT |
| R6 | Scoring untouched | `git diff develop -- tests/test_smc_signals.py` → **empty**; all 18 frozen tests pass | ✅ COMPLIANT |
| R7 | Enriched record matches frozen setup | `test_capture_matches_the_frozen_setup_fields` (7-tuple equality against an independently-composed `find_setups` call) | ✅ COMPLIANT |
| R7 | Anchor time resolved like payload | `test_anchor_time_resolves_from_times` → `anchor_time == TIMES[index]`; code bound rule `0 <= index < n` with `n == len(times)` equals `_time_at`'s `0 <= index < len(times)` | ✅ COMPLIANT |
| R7 | No setup → empty | `test_no_structure_returns_empty`, `test_empty_and_mismatched_ohlc_return_empty`, `test_mismatched_times_return_empty` | ✅ COMPLIANT |
| R7 | ATR nullable and anchored | `test_atr_is_anchored_at_the_setup_index` (expected computed from `src.indicators.atr`, not hardcoded), `test_atr_is_none_inside_the_warm_up` (`atr_window=100` > 24 bars) | ✅ COMPLIANT |
| R7 | Purity preserved | `test_capture_is_deterministic_and_does_not_mutate_inputs` (two runs equal + deepcopy equality) | ✅ COMPLIANT |
| R7 | Edge matrix | Ad-hoc execution: empty, 1 bar, 2 bars, mismatched highs/opens, `times` short/long, `atr_window` 0/1/100/1000, `range_=None` → all return `[]`/`None` with no raise | ✅ COMPLIANT |
| R7 | Record shape | `test_capture_record_shape_is_the_frozen_seven_plus_enrichment` (`_fields` exact) | ✅ COMPLIANT |

**Compliance summary**: 12/14 in-scope scenarios compliant, 2 out of scope (R5, R6-worker), 1 partial (R1 conflict-ignore behavior).

## Adversarial Checks

| # | Check | Result |
|---|-------|--------|
| 1 | `git diff develop -- tests/test_smc_signals.py` | **Empty** (exit 0, no output). The frozen tests still bite: they assert hardcoded entry/stop/TP/RR/score values, so any behavior change in `find_setups` shows. |
| 2 | `_serialize_smc` parity | Chain order identical: `find_swings → find_structure → dealing_range → find_setups` (`quotes.py:782-788` vs `signals.py:184-196`). Index→time identical: `_time_at` guard `0 <= index < len(times)` vs `0 <= index < n` with `len(times) == n` enforced. No divergence in default path. |
| 3 | `range_` override semantics | Default path is byte-identical to `get_smc_payload` (`dealing_range(highs, lows)` always computed, then preferred only when the caller passes a non-None override). A non-None override **can** diverge from the payload by design — it is unused by production code in Slice 1 (S4). |
| 4 | ATR index safety | `atrs[index] if index < len(atrs) else None`. `atr()` always returns a list of length `len(closes)` (`indicators.py:88-110`), and `index < n == len(closes)` is already guaranteed → guard is **unreachable** defensive code, not a bug (S3). |
| 5 | Degenerate inputs | Verified by test read **and** execution (see matrix). Never raises. |
| 6 | Test quality | No tautologies, no ghost loops, no mock-heavy files, no implementation-detail coupling. Hardcoded expectations (`take_profit == 114.5`, `== 110.0`) are behavior-meaningful and break under the wrong implementation. One type-only assertion (W3). |
| 7 | Ownership guard | `git diff develop -- tests/web/test_owned_model_guard.py` **empty**; file passes 25/25. The `OWNED_MODELS` assertion genuinely AST-parses the guard file (confirmed: extracts 10 model names, `Setup` absent) — not a no-op. |
| 8 | No scope creep | `git diff develop --stat` = exactly the 6 declared files. No `web/trading/setups.py`; `git diff develop -- web/worker.py` empty. |
| 9 | Index-name deviation | Empirically proven: `Index.max_name_length == 30`; a live `models.Index(name="ix_setup_symbol_interval_anchor")` yields `models.E034: cannot be longer than 30 characters` (31 chars). `ix_setup_sym_int_anchor` (23) is unambiguous and follows the repo's existing `ix_*` convention. `design.md:78` does **not** carry the impossible name → no doc fix required. |
| 10 | Lint / format / migrations | All exit 0 (see Build section). |
| 11 | Test subset | Working ordering: **177 passed**. The literal prescribed ordering exits 1 (W1). |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `sdd/setup-ledger/apply-progress` (#1692) has a full cycle table |
| All tasks have tests | ✅ | 10/10 in-scope tasks mapped to `test_smc_capture.py` (13) / `test_setups_model.py` (15) |
| RED confirmed | ✅ | Both new test files exist and are the sole source of the new behavior's assertions |
| GREEN confirmed | ✅ | 13 + 15 pass on execution now |
| Triangulation adequate | ✅ | 13 pure cases, 15 model/migration cases; distinct expected values |
| Safety Net for modified files | ⚠️ | `test_smc_signals.py` genuinely unmodified (diff empty) but apply-progress claims "22/22" while the file has **18** tests (W2) |

**Test layer distribution**: Unit 28 (2 files) · Integration 0 · E2E 0 (the Django model tests are unit-level model/migration contracts).

### Assertion Quality

| File | Line | Assertion | Issue | Severity |
|------|------|-----------|-------|----------|
| `tests/test_smc_capture.py` | 27 | `assert callable(capture_setups)` | Type-only smoke; no behavior | WARNING |

**Assertion quality**: 0 CRITICAL, 1 WARNING.

## Issues Found

**CRITICAL**: None.

**WARNING**
- **W1 — Prescribed test command exits 1 (pre-existing harness quirk).** When a `tests/web/*` module is listed *before* a root `tests/test_*.py` module, pytest reports `ERROR ... fixture 'user_a' not found` for `test_worker_zone_reads_across_users`, even though `tests/web/conftest.py` is registered. Reproduced **identically on `develop` (7d671ba)** in a clean worktree with `tests/web/test_candles_model.py tests/test_smc_signals.py tests/web/test_owned_model_guard.py` → same error. Not caused by Slice 1. Running the web tests last gives 177 passed. Fix separately (conftest/fixture-visibility), do not attribute to this PR.
- **W2 — apply-progress safety-net count is wrong**: claims `22/22 (test_smc_signals)`; the file collects 18 tests.
- **W3 — `test_capture_setups_is_callable`** asserts only `callable(...)`; it adds no TDD value beyond the import.

**SUGGESTION**
- **S1** — `test_setups_model.py` asserts `engine_version`/`atr`/`created_at` and the excluded six, but never the full required type set (`symbol` Char(32), `direction`/`interval` Char(8), `anchor_time` BigInteger, `score` PositiveSmallInteger). R1's "exact field set" is currently only statically verified.
- **S2** — `SetupRecord` docstring says `anchor_time` is `None` when the index is outside the window; the code **skips** the record (matching the spec edge matrix). Fix the docstring.
- **S3** — `atrs[index] if index < len(atrs) else None` is unreachable given `atr()` always returns `len(closes)` items.
- **S4** — `range_` is an unused divergence surface: no production caller, and `range_=None` cannot *disable* the range (it falls back to the computed one). Keep only if Slice 2 needs it; otherwise drop.
- **S5** — `web/trading/models.py` has no coverage instrumentation path (Django app); if changed-file coverage gates matter, add `--cov=web` to the Django test run.

## Verdict

**PASS WITH WARNINGS** — all Slice 1 requirements are implemented, tested with non-trivial assertions, and green (177 passed); lint, format, and migration checks are clean; `find_setups` and the frozen fixtures are provably untouched. The only non-green signal is a pre-existing pytest collection quirk (W1) already present on `develop`.
