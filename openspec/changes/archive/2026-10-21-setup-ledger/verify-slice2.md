```yaml
schema: gentle-ai.verify-result/v1
change: setup-ledger
scope: slice-2
evidence_revision: 6e40e6c745d85af48e378022d30910d547e94bd6
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 4/4
scenarios: 8/8
test_command: ".venv/bin/python -m pytest tests/test_smc_capture.py tests/test_boundary.py tests/web/test_setups_capture.py tests/web/test_worker_setups.py tests/web/test_worker_candles.py tests/web/test_worker_alerts.py tests/web/test_worker_private_sync.py tests/web/test_setups_model.py tests/web/test_no_order_surface.py tests/web/test_owned_model_guard.py -p no:randomly"
test_exit_code: 0
test_output_hash: sha256:b5167287847ffb6c97fe6dde7b85fb316e129552631cce4509b7c13be5aba48c
build_command: ".venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py makemigrations --check --dry-run"
build_exit_code: 0
build_output_hash: sha256:c97afb17deccdc1b936639662ee96b4112e0a32ac246f7ac8f3c2297b9aace57
```

# Verification Report — setup-ledger (Slice 2)

**Change**: setup-ledger · **Branch**: `feat/setup-ledger-capture` (2 commits on `feat/setup-ledger-core`) · **Mode**: Strict TDD
**Scope**: Phase 3 (3.1–3.4) + Phase 4 gates (4.1–4.2). Task 4.3 (archive) is deferred by design and not counted.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks in scope (P3 + 4.1/4.2) | 6 |
| Tasks complete | 6 |
| Tasks incomplete | 0 |
| Deferred (4.3 archive) | 1 |
| Diff vs Slice 1 base | 4 files, +421 / −0 |

## Build & Tests Execution

**Build** → exit 0
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
170 files already formatted
$ .venv/bin/python web/manage.py makemigrations --check --dry-run
No changes detected
```

**Tests (authoritative run, root `tests/` modules first)** → exit 0, `156 passed in 18.09s`
```text
$ .venv/bin/python -m pytest tests/test_smc_capture.py tests/test_boundary.py \
    tests/web/test_setups_capture.py tests/web/test_worker_setups.py \
    tests/web/test_worker_candles.py tests/web/test_worker_alerts.py \
    tests/web/test_worker_private_sync.py tests/web/test_setups_model.py \
    tests/web/test_no_order_surface.py tests/web/test_owned_model_guard.py -p no:randomly
156 passed
```

**Full suite** → exit 0, 1266 collected (105 e2e deselected), 0 failures.

**Prescribed ordering** (`tests/web/*` before root `tests/test_*.py`) → **exit 1**, 155 passed + 1 error:
`ERROR tests/web/test_owned_model_guard.py::test_worker_zone_reads_across_users — fixture 'user_a' not found`.
Reproduced identically on a clean `develop` worktree (`test_worker_candles.py test_boundary.py test_owned_model_guard.py` → same error), and on `feat/setup-ledger-core`. **Pre-existing harness quirk, not introduced here** (see W1).

**Coverage** (changed files, `--cov=trading.setups`)
| File | Stmts | Miss | Cover | Missing |
|------|-------|------|-------|---------|
| `web/trading/setups.py` | 36 | 1 | 97% | L74 (falsy-anchor guard) |
| `web/worker.py` | 161 | 92 | 43% | pre-existing paths; the capture block is covered by `test_worker_setups.py` |

## Spec Compliance Matrix

| Req | Scenario | Test / Evidence | Result |
|-----|----------|-----------------|--------|
| R3 | No backfill surface | Diff = 4 files only; no `management/commands/` change (`git diff --name-only … -- web/trading/management/` empty); no setup command exists. Capture is reachable only from `worker.run_once`. | ✅ COMPLIANT |
| R4 | Mixed engines coexist | `test_version_bump_inserts_a_new_row_and_keeps_the_old` — real DB: first run inserts `1`, monkeypatched `engine_version="2"` inserts a second, final `["1","2"]`. Works **because** the unique key carries `engine_version` (Slice 1 constraint verified live: `(symbol, interval, anchor_time, engine_version)`). | ✅ COMPLIANT |
| R5 | One row, then none | `test_capture_persists_one_matching_row` (all 9 persistence fields vs the independent `capture_setups` record), `test_capture_is_idempotent` (1 → 0, count stays 1). | ✅ COMPLIANT |
| R5 | No network, ATR anchored | `test_capture_reads_only_persisted_candles_no_network` — patches `src.client.BitunixClient` to a raising stub **and** `quotes._fetch_window` to raise; capture still persists 1 row. `test_capture_stores_atr_at_the_anchor` computes `atr(HIGHS, LOWS, CLOSES, 14)[record.index]` independently (verified live: 2.819845438398475 == 2.819845438398475 at index 20). | ✅ COMPLIANT |
| R5 | Bad interval fails loudly, safely | `test_bad_interval_raises_and_names_the_offender` (`"1h,bogus"` → `ValueError` matching `bogus`) + `test_bad_intervals_config_disables_capture_without_touching_ingestion` (funding 1, ticker 1, candle 1, setups 0, `"setup capture failed:"` + `"bogus"` logged, return `(1, 1)`). | ✅ COMPLIANT (multi-offender naming untested → W3) |
| R6 | Failure contained | `test_capture_failure_leaves_every_other_step_intact` — `_boom` raising: funding/ticker/candle all persist, setups 0, exact log `"setup capture failed: capture exploded"`, `run_once` returns `(1, 1)`. | ✅ COMPLIANT |
| R6 | Degrades quietly | `test_no_candles_inserts_nothing_and_does_not_raise`, `test_thin_window_inserts_nothing_and_does_not_raise` (2 rows), `test_capture_uses_configured_intervals` (1d configured, 1h seeded → 0). Ad-hoc verified outside the suite: 24 flat bars → `[]`, falsy `anchor_time` → 0 rows, `_db_rows` returning `[]` → 0 rows. | ✅ COMPLIANT |
| R6 | Guards stay green | `tests/test_boundary.py` 4 passed (unmodified), `tests/web/test_no_order_surface.py` 36 passed (unmodified), `tests/web/test_owned_model_guard.py` 25 passed standalone (unmodified). | ✅ COMPLIANT |

**Compliance summary**: 8/8 in-scope scenarios compliant.

## Adversarial Checks (as requested)

| # | Check | Result |
|---|-------|--------|
| 1 | **Zero network** | `grep -nE "requests\|urllib\|http\|socket\|BitunixClient\|kline\|httpx" web/trading/setups.py` → **no matches**. Imports are `os`, `market.quotes._db_rows`, `src.smc.config`, `src.smc.signals.capture_setups`, `trading.candles.CANDLE_INTERVALS`, `trading.models.Setup`. `market/quotes.py:523-545`: `_db_rows` only guards `interval not in CANDLE_INTERVALS` and runs `Candle.objects.filter(...)` — no client parameter, no call. No `BitunixClient` is constructed on the path (`grep -rn "trading.setups\|SETUP_CAPTURE" web/` → only `web/worker.py:97-99`). | ✅ PASS |
| 2 | **Isolation correctness** | `web/worker.py:83-106`: capture `try` is a **sibling** of the candle block (`83-95`), private sync (`107-113`) and alerts (`114-120`), each with its own handler. Import is **inside** the `try` (line 99). `return counts` at line 121 is `(funding, ticker)` unchanged. Capture code never references `_last_poll` — `global _last_poll` is declared only in `run_once` and written only by the candle-success path (line 90). | ✅ PASS |
| 3 | **Interval validation** | Read code + executed live: unset → `('1h',)`; `""` → `('1h',)`; `"  "` → `('1h',)`; `"1h, 4h ,1h"` → `('1h','4h')` (order preserved, deduped, whitespace stripped); `"1h,bogus,xx"` → `ValueError: SETUP_CAPTURE_INTERVALS has unknown interval(s): bogus, xx; valid: 5m, 15m, 1h, 2h, 4h, 1d, 1w, 1M` (**both** offenders named, order preserved); `"5m"` → `('5m',)`. | ✅ PASS (code) / ⚠️ multi-offender not covered by a test (W3) |
| 4 | **Idempotency & version** | Real DB writes under `pytest.mark.django_db` (`Setup.objects.get()`, `.count()`, `values_list`), no mocks on the persistence path. Second run 0; version bump inserts while old survives. Live `Setup._meta.constraints` confirms `engine_version` is in the unique key. | ✅ PASS |
| 5 | **ATR anchoring** | Test calls `atr(HIGHS, LOWS, CLOSES, 14)[record.index]` — no hardcoded number. Live recomputation matched exactly. | ✅ PASS |
| 6 | **Boundary/edge** | no candles → 0 ✓; 2 rows → 0 ✓; `find_setups == []` (flat 24-bar window) → `_records` returns `[]` ✓; unknown interval → `ValueError` at parse (loud, not a silent skip) ✓; falsy `anchor_time` → skipped, 0 inserted ✓ (verified with a temporary test file, then removed). None raised. | ✅ PASS |
| 7 | **No SMC math in Django** | `web/trading/setups.py` only slices row columns and delegates to `capture_setups`. Diff grep for `swing\|structure\|zone\|range\|ob_\|fvg\|scor` in added lines finds only a comment and the `score=` field copy. | ✅ PASS |
| 8 | **Frozen Slice 1** | `git diff feat/setup-ledger-core -- src/smc/ web/trading/models.py web/trading/migrations/` → **0 bytes**. | ✅ PASS |
| 9 | **No scope creep** | `git diff --name-status feat/setup-ledger-core..HEAD` → `A tests/web/test_setups_capture.py`, `A tests/web/test_worker_setups.py`, `A web/trading/setups.py`, `M web/worker.py` (+11). `web/market/` diff 0 bytes; dependency manifests diff 0 bytes; no order surface (36 guard tests green). | ✅ PASS |
| 10 | **Test quality** | `_boom`/`_record_after_candles` stubs are used only to *induce* failure/observation, while every other step asserts real DB state. `test_capture_runs_after_the_candle_cycle` genuinely proves ordering: it records `Candle.objects.count()` **at capture call time** (0 if capture ran earlier). Cross-checked against a `c0462cf` worktree without the worker step → all 3 worker tests RED, so they bite. Nested-inside-the-candle-`try` would also be caught: the exception would be logged as `"candle cycle failed: …"`, failing the caplog assertion. Two weak spots → W3/W4. | ✅ PASS with warnings |
| 11 | **Gates** | ruff 0, format 0, makemigrations 0, targeted tests 0 (156 passed). See W1 for the prescribed ordering variant. | ✅ PASS |
| 12 | **Changed-lines budget** | `git diff --numstat feat/setup-ledger-core..HEAD` = **+421 / −0** (tests 316, `setups.py` 94, `worker.py` 11). Whole change = **+954 / −3**. Forecast was 164 for S2 / 429 total. Covered by the user-accepted `size:exception`. | ✅ PASS with note |

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| `SETUP_CANDLE_WINDOW = 100` | ✅ | `setups.py:24`; passed as `want` to `_db_rows` (line 49). |
| `bulk_create(ignore_conflicts=True)` | ✅ | `setups.py:93`. |
| Row-count delta return | ✅ | `count()` before/after (lines 92-94), same precedent as `persist_candles`. |
| `engine_version` stamped at write | ✅ | `setups.py:87` from `src.smc.config.SMC_ENGINE_VERSION`. |
| Interval list from env only | ✅ | `capture_intervals()` reads only `SETUP_CAPTURE_INTERVALS`; default tuple is `("1h",)`. |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D2 — seam in `web/trading/setups.py` | ✅ Yes | Mirrors `candles.persist_candles`; `market/` untouched. |
| D3 — reject unknown intervals at parse | ⚠️ Partly | Behavior is correct, but the stated *mechanism* is off: validation runs lazily inside `capture_intervals()`, not at module import. See W2. |
| D6 — window 100, ATR 14, step after candle `try`, own `try` | ✅ Yes | `worker.py:96-106`; ATR default `atr_window=14` in the helper. |
| D4/D5 — narrowed field set / version in unique key | ✅ Yes | Unchanged from Slice 1; no duplicated math. |
| Module boundaries | ✅ Yes | `src/` untouched; Django layer holds no SMC logic. |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress-slice2.md` has a cycle table for 3.1–3.4. |
| All tasks have tests | ✅ | 3.1/3.3 map to `test_setups_capture.py` (12) and `test_worker_setups.py` (3). |
| RED confirmed | ✅ | Replayed on `c0462cf` (parent of the worker commit): all 3 worker tests FAIL. Pre-seam import fails with `ModuleNotFoundError` per the progress report. |
| GREEN confirmed | ✅ | 12 + 3 pass on current HEAD. |
| Triangulation adequate | ✅ | 12 distinct seam cases + 3 worker cases with different expected values. |
| Safety Net for modified files | ✅ | Only `web/worker.py` modified; `test_worker_candles.py` (18), `test_worker_alerts.py` (19), `test_worker_private_sync.py` (6) all pass and were not edited. |

**Test layer distribution**: Integration 15 (2 files, real Django ORM/DB) · Unit 0 · E2E 0.
(The seam is a persistence boundary; unit-level mocking would have been the weaker layer.)

### Assertion Quality

| File | Line | Assertion | Issue | Severity |
|------|------|-----------|-------|----------|
| `tests/web/test_setups_capture.py` | 195 | `assert "1h" in CANDLE_INTERVALS` | Constant-vs-constant; passes regardless of `DEFAULT_CAPTURE_INTERVALS` | WARNING |

**Assertion quality**: 0 CRITICAL, 1 WARNING. No tautologies, no ghost loops, no mock-heavy files, no implementation-detail coupling.

## Issues Found

**CRITICAL**: None.

**WARNING**
- **W1 — Prescribed test ordering exits 1 (pre-existing).** `tests/web/test_owned_model_guard.py::test_worker_zone_reads_across_users` cannot see the `user_a` fixture when a `tests/web/*` module precedes a root `tests/test_*.py` module in the same invocation. Reproduced on a clean `develop` worktree and on `feat/setup-ledger-core` → **not attributable to Slice 2**. The file passes standalone (25/25) and in the reordered run. Fix separately (pytest 9 conftest-visibility).
- **W2 — Worker comment / design D3 rationale is factually wrong.** `web/worker.py:97-98` says "a bad `SETUP_CAPTURE_INTERVALS` raises at module import". Verified: `SETUP_CAPTURE_INTERVALS=1h,bogus python -c "import trading.setups"` does **not** raise — parsing is lazy inside `capture_intervals()` at call time. The containment still holds (the call is inside the `try`), so there is no functional risk, but the justification for import placement is incorrect and should be corrected so nobody later "optimizes" the parse to import time assuming it is already lazy-safe.
- **W3 — Multi-offender `ValueError` is untested.** The code names every unknown interval (`bogus, xx`, verified live), but the only test uses a single offender (`"1h,bogus"`). Requirement 3's "EVERY offender" clause has no regression guard. Also untested: `""` and whitespace-only env falling back to `("1h",)` (code is correct; verified ad hoc).
- **W4 — `test_default_capture_interval_is_a_persisted_candle_interval` is a near-tautology.** It asserts a static constant is a member of another static constant; it would pass even if `DEFAULT_CAPTURE_INTERVALS` were `("7h",)`. Replace with an assertion on `capture_intervals()` under `delenv`, or delete (that case is already covered by `test_intervals_default_to_1h`).

**SUGGESTION**
- **S1** — Add `SETUP_CAPTURE_INTERVALS=""` and `"   "` cases next to the unset-env case (cheap, closes W3's second half).
- **S2** — `_records()` returns an unannotated `list`; `list[SetupRecord]` (importing the record type) documents the seam better.
- **S3** — No test exercises more than one symbol × one interval per call; the nested loop in `run_setup_capture` is only exercised on a single element. A 2-symbol case would pin the loop composition (low value, noted only).

## Scope Budget

| Scope | Additions | Deletions | Total |
|-------|-----------|-----------|-------|
| Slice 2 (`feat/setup-ledger-core..HEAD`) | 421 | 0 | **421** |
| Slice 1 (`develop..feat/setup-ledger-core`) | 533 | 3 | 536 |
| Whole change | 954 | 3 | 957 |

Forecast was 164 (S2) / 429 (total). S2 alone exceeds the 400-line review budget; the user-accepted `size:exception` covers it, and the slice is a single coherent work unit (seam + its isolated scheduling + their tests).

## Verdict

**PASS WITH WARNINGS** — Slice 2 implements R3/R5/R6 exactly as specified: zero network, sibling isolated `try`, in-`try` import, loud interval validation, real idempotent DB writes, ATR anchored at the setup index, no SMC math in Django, and a byte-identical frozen Slice 1. All 8 in-scope scenarios have non-trivial passing tests (156 green); lint/format/migrations are clean. Zero CRITICAL. Four WARNINGs, all documentation/test-coverage precision rather than behavior, and one of them (W1) is a pre-existing harness quirk present on `develop`.
