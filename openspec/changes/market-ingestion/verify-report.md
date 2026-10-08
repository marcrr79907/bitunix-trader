```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:34b6c6078c2d18e4c50dffc2a7c19ae44529d6014c135fe73e41bfe54f3f9962
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 7/7
scenarios: 12/14
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:428b1be5bf128f7731cf504e8f181f6a0ec2007d123b98f0ffb757d59cb414be
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:294e67acb32e42bd4c92c6bdcde4e7109a5bf852d6c9871586f4d4f2cf10a159
```

# Verification Report

**Change**: market-ingestion (Phase 3) — chain tip
**Version**: N/A (delta specs)
**Mode**: Strict TDD (openspec `config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Scope**: chain tip `feat/market-worker` (HEAD `fb7c492`); tracker `feat/market-ingestion` (`67440f1`); chain diff = tracker…HEAD, 6 files, +781/−22. PR1 `feat/market-data-path` (`71e3f4e`), PR2 `feat/market-worker` (`fb7c492`, incl. `16f7bf5` + test-only `fb7c492`).

This is a **focused re-verification** of the fix for WARNING 2 (MEDIUM) from the prior report: `web/trading/ingest.py::fetch_market` now skips a row when all three price fields (`last_price`, `mark_price`, `index_price`) are `None`. The prior report's other warnings (1, 3, 4) were re-checked. Everything was reproduced from scratch against the working tree; probes ran from `/tmp`, outside the repo. **WARNING 2 is closed** — the empty-API-response case now persists 0 rows, and a legitimate `funding == 0.0` with prices is still kept. An adversarial probe surfaced one **theoretical** over-filter (a funding payload with no prices at all is dropped), but the live public API carries `markPrice` on 907/907 funding rows, so the case is unreachable in practice. It is reported honestly as a LOW warning with evidence, not a regression.

## Re-verification of the WARNING 2 fix (independently reproduced)

Fix commit: `71e3f4e` on `feat/market-data-path` (contained in the tip branch).

**Guard under test** (`web/trading/ingest.py:33-38`):
```python
if (
    r["last_price"] is None
    and r["mark_price"] is None
    and r["index_price"] is None
):
    continue
```

**Independent adversarial probes** (throwaway `/tmp/opencode/probe_fix_market.py`, in-memory sqlite, repo untouched) — 6/7 pass:

| Probe | Scenario | Result |
|-------|----------|--------|
| a1 | `fetch_market(stub([], []), ["BTCUSDT","ETHUSDT"])` | ✅ `{"funding": [], "tickers": []}` — no fabricated rows |
| a2 | `persist_market(empty)` on that result | ✅ `(0, 0)` |
| a3 | DB row counts after a2 | ✅ `0/0` — nothing persisted |
| b | legit `fundingRate="0"` **with** prices | ✅ row kept, `funding_rate == 0.0` |
| c1 | funding WITH `markPrice`/`indexPrice`, no ticker | ✅ kept, `funding_rate == 0.0003` |
| d | funding WITHOUT any price, no ticker | ❌ **DROPPED** — real funding lost (see WARNING 2b) |
| e | ticker-only (no funding) | ✅ kept, `last_price == 50000.0` |

**Fix verdict: CORRECT for the reported defect.** The prior WARNING 2 reproduction (`(2,2)` fabricated rows) now yields `(0,0)`. The `None`-price signal — not `funding == 0.0` — is used, so a genuine zero funding rate survives. New tests `test_fetch_market_empty_api_response_yields_nothing`, `test_persist_market_empty_api_response_is_a_noop`, `test_fetch_market_keeps_legit_zero_funding_with_present_prices`, `test_fetch_market_keeps_ticker_only_row`, `test_fetch_market_keeps_mark_price_only_row` pin all five behaviors and pass.

**WARNING 2 — CLOSED.**

### Adversarial probe on the live API (reachability of probe d)

Probe (d) drops a row whose funding payload carries a real rate but no price fields. To decide whether this is a real regression or a theoretical one, the live public endpoint was checked:

```text
$ curl -s https://fapi.bitunix.com/api/v1/futures/market/funding_rate/batch
rows=907 missing markPrice=0 missing indexPrice=1 (TONUSD)
```

Every funding row in the live payload carries `markPrice` (907/907). The funding-less-prices case is therefore **not reachable against the real API** — it is a fragility, not an active data-loss bug.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (Guard Matrix + WU1 + WU2 + Phase 3) | 32 |
| Tasks complete (present in tree + verified here) | 29 |
| Tasks incomplete | 3 (Phase 3: 3.1–3.3 = this verification) |

WU1 (1.1–1.7), WU2 (2.1–2.6) and all 13 Guard-Matrix rows are present and verified in the tree. `tasks.md` checkboxes remain `[ ]` (29 unchecked, 0 checked) — WARNING 1: apply intentionally left `openspec/**` untouched on the tracker branch.

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
70 files already formatted
$ .venv/bin/python web/manage.py makemigrations --check --dry-run
No changes detected
```

**Tests**: ✅ 212 passed / ❌ 0 failed / ⚠️ 0 skipped (exit 0)
```text
$ .venv/bin/python -m pytest
212 passed in 57.75s
```
Prior report baseline was 207; the fix added **5** tests in `tests/web/test_ingest.py` (8 → 13). New/changed suites: `tests/web/test_ingest.py` 13, `tests/web/test_service_stubs.py` 10. Both are Django-DB-backed integration tests (`@pytest.mark.django_db`) over the real ORM; the only stub is the HTTP client and the injectable `sleep`.

**Coverage**: web 94% / threshold 85% → ✅ Above; patch gate 100% → ✅
```text
$ .venv/bin/coverage report --include="web/*" --fail-under=85
TOTAL                               432     24    94%
$ .venv/bin/diff-cover coverage.xml --compare-branch=feat/market-ingestion --fail-under=100
web/trading/ingest.py (100%)   web/trading/models.py (100%)   web/worker.py (100%)
Total: 87 lines, Missing: 0 lines, Coverage: 100%
```

## L1 — Independent Test Evidence

| Check | Command | Result |
|-------|---------|--------|
| Full suite | `.venv/bin/python -m pytest` | ✅ 212 passed, exit 0 |
| Guard suite | `.venv/bin/python -m pytest tests/web/test_ingest.py tests/web/test_service_stubs.py` | ✅ 23 passed, exit 0 |
| Lint | `.venv/bin/ruff check .` | ✅ All checks passed, exit 0 |
| Format | `.venv/bin/ruff format --check .` | ✅ 70 files formatted, exit 0 |
| Migrations | `.venv/bin/python web/manage.py makemigrations --check --dry-run` | ✅ No changes detected, exit 0 |
| Boundary | `.venv/bin/python -m pytest tests/test_boundary.py` | ✅ 4 passed, exit 0 |
| Core-isolation grep | AST scan of `src/` for `django` | ✅ 0 offenders |
| Reverse-direction grep | `web/ → src/` imports only (`worker.py`, `trading/ingest.py`) | ✅ intended direction only |
| Fix probe | `/tmp/opencode/probe_fix_market.py` | ✅ 6/7 (probe d = theoretical, see WARNING 2b) |

Migration↔model parity: `0002_market_snapshots.py` declares exactly the fields/constraints in `models.py` (`UniqueConstraint(symbol, ts)`, no FK); `makemigrations --check` confirms zero drift.

## L2 — Coverage Gates

| Gate | Command | Result |
|------|---------|--------|
| Coverage XML | `.venv/bin/python -m pytest --cov --cov-report=xml` | ✅ exit 0, `coverage.xml` written |
| Web gate (R4) | `.venv/bin/coverage report --include="web/*" --fail-under=85` | ✅ exit 0, TOTAL 94% |
| Patch gate (tracker) | `.venv/bin/diff-cover coverage.xml --compare-branch=feat/market-ingestion --fail-under=100` | ✅ exit 0, 87 lines, 0 missing, 100% |

`web/trading/ingest.py` 100%, `web/trading/models.py` 100%, `web/worker.py` 97% (missing `122` = infinite-`idle_loop` sleep, `127` = `__main__`; both outside the patch-diff gate).

## Spec Compliance Matrix

### market-ingestion (R1–R7, 14 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 | Global models carry no owner | `test_global_snapshots_have_no_owner` + probe `_meta.get_field("user")` raises / `constraints` introspection | ✅ COMPLIANT |
| R1 | (symbol, ts) is unique | `test_duplicate_symbol_ts_rejected` (both models) + probe `UniqueConstraint` names/fields | ✅ COMPLIANT |
| R2 | Re-persist is a no-op | `test_persist_market_twice_is_a_noop` | ✅ COMPLIANT |
| R3 | Round-trip | `test_persist_market_round_trip` + probe `persist_market` twice → `(2,2)` then `(0,0)` | ✅ COMPLIANT |
| R3 | UTC persisted, epoch kept raw | `test_persist_market_round_trip` (`ts.tzinfo`/`utcoffset()==0`; `isinstance(next_funding_time,int)`) + probe | ✅ COMPLIANT |
| R3 | Empty input | `test_fetch_market_empty_symbols_yields_nothing`, `test_persist_market_empty_input_is_a_noop`, `test_fetch_market_empty_api_response_yields_nothing`, `test_persist_market_empty_api_response_is_a_noop` + probe (a1–a3) | ✅ COMPLIANT — **empty-API-response half now covered and passing; WARNING 2 closed** |
| R4 | One cycle ingests | `test_worker_one_cycle_ingests_and_returns_zero` | ✅ COMPLIANT |
| R4 | Backoff then recovery | `test_worker_backs_off_on_bitunix_error_then_recovers`, `test_worker_backs_off_on_request_exception_then_recovers`, `test_worker_backoff_is_capped_at_300_seconds` + probe `[60,120,240,300,300]` | ✅ COMPLIANT |
| R4 | Clean stop | `test_worker_stop_exits_between_cycles`, `test_worker_stop_set_before_first_cycle_ingests_nothing` | ✅ COMPLIANT |
| R5 | Both services boot | `test_worker_main_boots_one_iteration`, `test_scheduler_boots_one_iteration`, `test_install_signal_handlers_returns_unset_event`, `test_signal_handler_sets_stop_event` | ✅ COMPLIANT |
| R6 | Core has no Django import | `test_no_django_import_in_core` (+ `test_scanner_flags_a_django_violation`) | ✅ COMPLIANT |
| R6 | Web may depend on core | (no dedicated boundary test) — exercised implicitly: importing `trading.ingest`/`worker` imports `src.monitor`/`src.client`/`src.config` at runtime | ⚠️ PARTIAL — direction proven by import success, not by an explicit assertion (see WARNING 3) |
| R7 | No order endpoint in new code | `test_no_order_surface_in_web_and_src` (scans `web/`+`src/`, now incl. ingest/worker) | ✅ COMPLIANT |
| R7 | Dependency file unchanged | (no test) — manually verified: chain diff touches no `requirements*.txt`/`pyproject.toml`/`setup.cfg` | ❌ UNTESTED — verified by inspection (WARNING 4) |

**Compliance summary**: 7 requirements, **7 complete**. 14 scenarios, **12 compliant / 1 partial / 1 untested** (was 11/2/1; the empty-API-response scenario moved from PARTIAL to COMPLIANT).

## Independent Adversarial Probes (executed from `/tmp`)

All probes ran against the real tree via `/tmp/opencode/probe_fix_market.py` (in-memory sqlite) and left the repo unchanged.

| Probe | Method | Result |
|-------|--------|--------|
| Empty API response | `fetch_market(stub(empty payload), ["BTCUSDT","ETHUSDT"])` | ✅ `{"funding": [], "tickers": []}`; `persist_market` → `(0,0)`; DB `0/0` |
| Legit zero funding | `fundingRate="0"` with prices | ✅ row kept, `funding_rate == 0.0` |
| Funding + markPrice, no ticker | funding payload without ticker | ✅ kept, real rate preserved |
| Funding, no prices, no ticker | funding payload with no `markPrice`/`indexPrice` | ⚠️ **dropped** — theoretical over-filter; live API always sets `markPrice` (see WARNING 2b) |
| Ticker-only | prices, no funding | ✅ kept |
| Idempotent counts | persist same rows twice | ✅ second call returns `(0,0)`, row counts stay 2/2 |
| Design bug confirmed-fixed | `len(bulk_create(ignore_conflicts=True))` on a duplicate set | ✅ returned **2 attempted** while inserting 0 → design's `len(...)` formula was wrong; shipped row-count-delta is **correct** |
| UTC + raw epoch | persisted `ts` tz-aware UTC; `next_funding_time` int | ✅ `utcoffset()==0`, `isinstance(int)`, `row.ts == expected UTC instant` |
| Constraint introspection | `_meta.constraints` names/fields; `get_field("user")` | ✅ `uniq_funding_symbol_ts`/`uniq_ticker_symbol_ts`, fields `("symbol","ts")`, no `user` |
| Live funding payload shape | `curl` real `funding_rate/batch` | ✅ 907/907 rows carry `markPrice` |
| `src/` framework-free | AST scan for `django` in all `src/*.py` | ✅ 0 offenders |
| Import safety | fresh interpreter `import worker` | ✅ `django` NOT in `sys.modules` |
| `run_loop(iterations=None)` | flipping `stop` (True on 4th call) | ✅ terminates after 3 cycles, returns 0, 3 rows |
| Backoff progression | 5 consecutive failures | ✅ sleeps exactly `[60,120,240,300,300]`; reset to 30 after recovery |

`iterations=None` with a `stop` that never flips loops forever — that is the **intended deployed behavior** (long-running worker), not a busy-loop defect.

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | apply-progress `#1340` has a full RED→GREEN table for WU1 and WU2; fix commit `71e3f4e` adds the failing empty-response tests with the guard. |
| All tasks have tests | ✅ | WU1 8 tests (+5 fix), WU2 9 tests; all 13 Guard-Matrix rows carry a covering test. |
| RED confirmed (tests exist) | ✅ | `test_ingest.py` (13) and `test_service_stubs.py` (10) exist. |
| GREEN confirmed (tests pass) | ✅ | 212/212 pass on independent execution. |
| Triangulation adequate | ✅ | Two symbols; three backoff cases; stop-before-first and mid-loop; both unique constraints; empty-symbols vs empty-API-response; zero-funding-with-prices vs ticker-only vs mark-price-only. |
| Safety Net for modified files | ✅ | Live baseline 207; full suite green before and after the fix. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (pure service/loop logic) | 13 | 2 | pytest |
| Integration / DB (Django ORM, `django_db`) | 10 | 2 | pytest, pytest-django |
| **New/changed total** | **23** | **2** | |
| Full suite | 212 | 15 | pytest, pytest-django, pytest-cov |

### Changed-File Coverage

| File | Line % | Uncovered Lines | Rating |
|------|--------|-----------------|--------|
| `web/trading/ingest.py` | 100% | — | ✅ Excellent |
| `web/trading/models.py` | 100% | — | ✅ Excellent |
| `web/worker.py` | 97% | 122 (infinite idle sleep), 127 (`__main__`) | ✅ Excellent |

**Average changed file coverage**: 99%.

### Assertion Quality

Scanned both changed test files (Step 5f). No tautologies, no assertion without production-code execution, no ghost loops. `test_fetch_market_empty_api_response_yields_nothing` asserts the exact empty contract and has paired non-empty companions (`test_fetch_market_splits_and_maps_two_symbols`, `test_fetch_market_keeps_legit_zero_funding_with_present_prices`). The three over-filter guards (`legit zero funding`, `ticker-only`, `mark-price-only`) each assert a concrete kept-row shape; none is redundant. `sleep.calls == [...]` asserts a spec-required observable. No mocks; the HTTP client is an injected stub.

**Assertion quality**: ✅ All assertions verify real behavior.

### Quality Metrics
**Linter**: ✅ No errors (ruff exit 0)
**Type Checker**: ➖ Not configured in this project
**Format**: ✅ 70 files formatted

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R1 global models | ✅ Implemented | `FundingSnapshot`/`TickerSnapshot` are plain `models.Model`, no `user`, unique `(symbol, ts)`. |
| R2 idempotent persistence | ✅ Implemented | `bulk_create(ignore_conflicts=True)` in one `transaction.atomic()`; **row-count delta**, not `len()`. |
| R3 ingestion | ✅ Implemented | `fetch_market` reuses `src.monitor.fetch_rows`; guard drops rows with all-None prices → empty *symbols* and empty *response* both persist `(0,0)`. **Fix verified.** |
| R4 worker loop | ✅ Implemented | `INGEST_POLL_SECONDS` (default 30), `min(backoff*2, 300)`, per-cycle log, injectable `iterations`/`stop`/`sleep`, SIGTERM/SIGINT `Event`. |
| R5 scheduler stub | ✅ Implemented | `scheduler.py` unchanged, shares `worker.idle_loop`. |
| R6 boundary | ✅ Implemented | `src/` framework-free; first `web/→src/` import is the intended direction only. |
| R7 read-only + no dep | ✅ Implemented | No order verb/path in new code; `requirements.txt` unchanged (git diff empty). |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 app = `trading` | ✅ Yes | Models added to the existing installed/migrated app. |
| D2 ship-without-prune, flagged | ✅ Yes | Documented in `design.md:33-34`, `proposal.md:62`, `explore.md:175`. No silent accumulation. |
| D3 reuse `src.monitor.fetch_rows` | ✅ Yes | `ingest.py:15,32`; no forked parser. |
| D4 plain loop, no RQ | ✅ Yes | No new runtime dependency; `requirements.txt` untouched. |
| Design `persist_market` code block | ⚠️ Deviation (good) | `design.md:64-67` shows the incorrect `len(bulk_create(...))` count; shipped code uses a row-count delta and is **correct**. Design doc is now stale (SUGGESTION 1). |
| `_MAX_BACKOFF_SECONDS` constant | ✅ Yes (minor) | Apply extracted the literal to a named module constant — behavior identical. |
| `idle_loop` unchanged for scheduler | ✅ Yes | `worker.py:114-123` byte-compatible contract with `scheduler.py`. |
| Empty-data guard | ✅ Yes (new) | Fix keeps price-bearing rows and drops all-None-price rows; matches the spec's "empty response → 0 rows" claim that the design previously contradicted. |

## Issues Found

**CRITICAL**: None.

**WARNING 1 (LOW) — `tasks.md` checkboxes are all `[ ]` despite completed work.**
`openspec/changes/market-ingestion/tasks.md` shows `[ ]` for all 13 Guard-Matrix rows and WU1/WU2 tasks (29 unchecked, 0 checked), though every item is present and verified. Apply recorded completion in Engram `#1340` rather than the tracker-branch artifact. **Fix:** flip `[x]` for WU1 1.1–1.7, WU2 2.1–2.6, and the completed Guard-Matrix rows during archive. (Classified SUGGESTION per this re-verification's scope — planning-artifact hygiene, not a code defect.)

**WARNING 2 (MEDIUM) — CLOSED.** Empty API response now persists 0 rows; legitimate zero funding with prices is kept. Verified by `71e3f4e`, the 5 new tests, and probes a1–a3 + b.

**WARNING 2b (LOW) — guard over-filters funding when a funding row carries NO price fields.**
The guard keys on the three price fields alone. A `funding_rate/batch` row with a real `fundingRate` but no `markPrice`/`indexPrice` (and no ticker row) would have all three price fields `None` and be dropped, losing real funding. **Probe (d) reproduces the drop** (`[]`). **Reachability: not reachable against the live API** — `curl` of the real `funding_rate/batch` shows `markPrice` present on 907/907 rows (`indexPrice` missing on 1 of 907, `TONUSD`). So this is a **fragility**, not an active data-loss bug. However, the guard is coarser than its own stated intent ("no real market data"): a row with zero prices but a non-default funding rate is not "no market data". **Fix trigger:** make the guard require *all* of `last_price`, `mark_price`, `index_price` **and** a default funding trio (`funding == 0.0` from a missing payload) — or test the funding-side signal explicitly (`next_funding_time == 0` as the absence marker). Low priority given live reachability; worth a one-line comment or a `funding_rate != 0.0` escape hatch. Not a regression: the prior behavior persisted a *false* zero for missing rows; this filter only risks dropping a *real* funding value in a payload shape the API does not currently emit.

**WARNING 3 (LOW) — R6 "Web may depend on core" has no explicit boundary test.**
`tests/test_boundary.py` asserts only the forbidden direction (`src/` imports no Django) and the stdlib-only pure modules. The permitted direction is proven only implicitly. No test asserts the direction is allowed (or that `src/ → web/` is forbidden). **Fix trigger:** add a boundary test asserting `src/` does not import `web`/`trading`/`scheduler`.

**WARNING 4 (LOW) — R7 "Dependency file unchanged" is untested.**
No test asserts `requirements.txt` is unchanged; verified here only by `git diff` (empty across the chain). **Fix trigger:** add a guard test that no new runtime import appears in `web/`/`src/` outside the declared set.

**SUGGESTION 1 — update `design.md` to match the shipped `persist_market`.**
The design snippet (`design.md:62-68`) uses `len(bulk_create(..., ignore_conflicts=True))` as the inserted count. That formula is wrong; the shipped code correctly uses a row-count delta. Correct the design doc so future readers don't reintroduce the bug.

**SUGGESTION 2 — note the infinite-loop deployed behavior explicitly.**
`run_loop(iterations=None)` with no signal loops forever by design. Correct production behavior, but worth a one-line docstring note.

**SUGGESTION 3 — document the empty-data guard's funding-without-price limitation.**
The docstring already explains the `None`-price signal. Adding the WARNING 2b ceiling (a row with a real funding rate but all-None prices is dropped) would make the tradeoff explicit.

## Verdict

**PASS WITH WARNINGS**

The WARNING 2 fix is independently verified: **212/212 tests pass** (exit 0, +5 over the prior baseline), `ruff check`/`ruff format --check` exit 0 (70 files), `makemigrations --check` clean, boundary green (4 passed), web coverage 94% (≥85), and patch coverage 100% (0 missing on 87 lines). The empty-API-response probe that previously produced `(2,2)` fabricated rows now returns `{"funding": [], "tickers": []}` and persists `(0,0)`; a legitimate `funding == 0.0` with prices is kept; ticker-only and mark-price-only rows survive. R3's "Empty input" scenario is now **COMPLIANT** (12/14 scenarios, up from 11/14). An honest adversarial probe found one **theoretical** over-filter — a funding row with no prices at all is dropped — but the live `funding_rate/batch` payload carries `markPrice` on 907/907 rows, so it is not reachable in production; it is recorded as LOW WARNING 2b with the upgrade path. Remaining items are non-blocking: two partial/untested scenarios (implicit web→core direction; untested dependency invariant), stale `tasks.md` checkboxes, design-doc drift, and the theoretical guard coarseness. **Archive decision: READY** — no blockers or criticals; WARNING 2 is closed, and WARNING 2b is a documented, low-priority hardening note.

## Traceability

| Artifact | Reference |
|----------|-----------|
| Proposal | `openspec/changes/market-ingestion/proposal.md` |
| Design | `openspec/changes/market-ingestion/design.md` (D1–D4, Retention D2) |
| Tasks | `openspec/changes/market-ingestion/tasks.md` |
| Delta spec | `specs/market-ingestion/spec.md` (R1–R7) |
| Code | `web/trading/models.py`, `web/trading/ingest.py`, `web/trading/migrations/0002_market_snapshots.py`, `web/worker.py`, `web/scheduler.py` (unchanged) |
| Tests | `tests/web/test_ingest.py`, `tests/web/test_service_stubs.py`, `tests/test_boundary.py`, `tests/web/test_no_order_surface.py` |
| Reused core | `src/monitor.py::fetch_rows`, `src/config.py::SYMBOLS`, `src/client.py` |
| Apply evidence | Engram `#1340` (`sdd/market-ingestion/apply-progress`) |
| Fix commit | `71e3f4e` (skip rows with no market data in `fetch_market`) |
| Commits | `7d4204a` (PR1 base), `71e3f4e` (PR1 fix), `16f7bf5` + `fb7c492` (PR2) |
| Chain diff | `feat/market-ingestion...feat/market-worker`, 6 files, +781/−22, sha256 `34b6c607…` |
