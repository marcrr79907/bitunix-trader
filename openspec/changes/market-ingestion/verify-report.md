```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:face8ce138663c1e4c160f846aa31499dfede590729da19bedd1e46126400d02
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 7/7
scenarios: 11/14
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:30e2f341a86cda5de5899120417f3c03af46948c7e79dcdaed1ee90c51635104
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:294e67acb32e42bd4c92c6bdcde4e7109a5bf852d6c9871586f4d4f2cf10a159
```

# Verification Report

**Change**: market-ingestion (Phase 3) — chain tip
**Version**: N/A (delta specs)
**Mode**: Strict TDD (openspec `config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Scope**: chain tip `feat/market-worker` (HEAD `6d778b7`); tracker `feat/market-ingestion` (`c23d0ac`); chain diff = tracker…HEAD, 6 files, +675/−22. PR1 `feat/market-data-path` (`570a432`), PR2 `feat/market-worker` (`766d853` + test-only `6d778b7`).

This is an independent verification executed from scratch against the working tree. The apply-progress artifact (Engram `#1340`) was cross-checked, not trusted. Every claimed count, constraint, and edge case was reproduced with throwaway probes in `/tmp`, outside the repo. **No blockers and no critical findings.** Two spec scenarios are only partially covered (empty-API-response semantics; an explicit web→core direction assertion) and one is test-free but manually verified (dependency-file unchanged); these are warnings, not regressions.

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

**Tests**: ✅ 207 passed / ❌ 0 failed / ⚠️ 0 skipped (exit 0)
```text
$ .venv/bin/python -m pytest
...............................................................          [100%]
207 passed in 53.01s
```
New/changed suites: `tests/web/test_ingest.py` 8, `tests/web/test_service_stubs.py` 10 (8 worker + 1 scheduler + 1 signal-handler). Both are Django-DB-backed integration tests (`@pytest.mark.django_db`) over the real ORM; the only stub is the HTTP client and the injectable `sleep`.

**Coverage**: web 94% / threshold 85% → ✅ Above; patch gate 100% → ✅
```text
$ .venv/bin/coverage report --include="web/*" --fail-under=85
TOTAL                               430     24    94%
$ .venv/bin/diff-cover coverage.xml --compare-branch=feat/market-ingestion --fail-under=100
web/trading/ingest.py (100%)   web/trading/models.py (100%)   web/worker.py (100%)
Total: 85 lines, Missing: 0 lines, Coverage: 100%
```

## L1 — Independent Test Evidence

| Check | Command | Result |
|-------|---------|--------|
| Full suite | `.venv/bin/python -m pytest` | ✅ 207 passed, exit 0 |
| Guard suite | `.venv/bin/python -m pytest tests/web/test_ingest.py tests/web/test_service_stubs.py` | ✅ 18 passed, exit 0 |
| Lint | `.venv/bin/ruff check .` | ✅ All checks passed, exit 0 |
| Format | `.venv/bin/ruff format --check .` | ✅ 70 files formatted, exit 0 |
| Migrations | `.venv/bin/python web/manage.py makemigrations --check --dry-run` | ✅ No changes detected, exit 0 |
| Boundary | `.venv/bin/python -m pytest tests/test_boundary.py` | ✅ 4 passed, exit 0 |
| Core-isolation grep | AST scan of `src/` for `django` | ✅ 0 offenders |
| Reverse-direction grep | `web/ → src/` imports only (`worker.py`, `trading/ingest.py`) | ✅ intended direction only |

Migration↔model parity: `0002_market_snapshots.py` declares exactly the fields/constraints in `models.py` (`UniqueConstraint(symbol, ts)`, no FK); `makemigrations --check` confirms zero drift.

## L2 — Coverage Gates

| Gate | Command | Result |
|------|---------|--------|
| Coverage XML | `.venv/bin/python -m pytest --cov --cov-report=xml` | ✅ exit 0, `coverage.xml` written |
| Web gate (R4) | `.venv/bin/coverage report --include="web/*" --fail-under=85` | ✅ exit 0, TOTAL 94% |
| Patch gate (tracker) | `.venv/bin/diff-cover coverage.xml --compare-branch=feat/market-ingestion --fail-under=100` | ✅ exit 0, 85 lines, 0 missing, 100% |

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
| R3 | Empty input | `test_persist_market_empty_input_is_a_noop`, `test_fetch_market_empty_symbols_yields_nothing` | ⚠️ PARTIAL — covers empty *symbols*, not empty *API response* (see WARNING 2) |
| R4 | One cycle ingests | `test_worker_one_cycle_ingests_and_returns_zero` | ✅ COMPLIANT |
| R4 | Backoff then recovery | `test_worker_backs_off_on_bitunix_error_then_recovers`, `test_worker_backs_off_on_request_exception_then_recovers`, `test_worker_backoff_is_capped_at_300_seconds` + probe `[60,120,240,300,300]` | ✅ COMPLIANT |
| R4 | Clean stop | `test_worker_stop_exits_between_cycles`, `test_worker_stop_set_before_first_cycle_ingests_nothing` | ✅ COMPLIANT |
| R5 | Both services boot | `test_worker_main_boots_one_iteration`, `test_scheduler_boots_one_iteration`, `test_install_signal_handlers_returns_unset_event`, `test_signal_handler_sets_stop_event` | ✅ COMPLIANT |
| R6 | Core has no Django import | `test_no_django_import_in_core` (+ `test_scanner_flags_a_django_violation`) | ✅ COMPLIANT |
| R6 | Web may depend on core | (no dedicated boundary test) — exercised implicitly: importing `trading.ingest`/`worker` imports `src.monitor`/`src.client`/`src.config` at runtime | ⚠️ PARTIAL — direction proven by import success, not by an explicit assertion (see WARNING 3) |
| R7 | No order endpoint in new code | `test_no_order_surface_in_web_and_src` (scans `web/`+`src/`, now incl. ingest/worker) | ✅ COMPLIANT |
| R7 | Dependency file unchanged | (no test) — manually verified: chain diff touches no `requirements*.txt`/`pyproject.toml`/`setup.cfg` | ❌ UNTESTED — verified by inspection (WARNING 4) |

**Compliance summary**: 7 requirements, **7 complete**. 14 scenarios, **11 compliant / 2 partial / 1 untested**.

## Independent Adversarial Probes (executed from `/tmp`)

All probes ran against the real tree via `/tmp/opencode/probe_market.py`; 7/7 passed and left the repo unchanged.

| Probe | Method | Result |
|-------|--------|--------|
| Idempotent counts | persist same rows twice | ✅ second call returns `(0,0)`, row counts stay 2/2 |
| **Design bug confirmed-fixed** | `len(bulk_create(ignore_conflicts=True))` on a duplicate set | ✅ returned **2 attempted** while inserting 0 → design's `len(...)` formula was wrong; shipped row-count-delta is **correct** |
| UTC + raw epoch | persisted `ts` tz-aware UTC; `next_funding_time` int | ✅ `utcoffset()==0`, `isinstance(int)`, `row.ts == expected UTC instant` |
| Constraint introspection | `_meta.constraints` names/fields; `get_field("user")` | ✅ `uniq_funding_symbol_ts`/`uniq_ticker_symbol_ts`, fields `("symbol","ts")`, no `user` |
| Empty symbols | `fetch_market(stub, [])` | ✅ `{"funding": [], "tickers": []}`, `(0,0)`, no raise |
| **Empty API response** | `fetch_market(stub(empty payload), ["BTCUSDT","ETHUSDT"])` | ⚠️ emits **2 rows** (one per symbol) with defaults — `funding_rate=0.0`, `interval=8`, `next_funding_time=0`, prices `None`; persists `(2,2)`. Contradicts the spec's literal "empty API response → persists 0 rows" (see WARNING 2) |
| `src/` framework-free | AST scan for `django` in all `src/*.py` | ✅ 0 offenders |
| Import safety | fresh interpreter `import worker` | ✅ `django` NOT in `sys.modules` — importing `worker` does not force `django.setup()`; `scheduler` import stays light |
| `run_loop(iterations=None)` | flipping `stop` (True on 4th call) | ✅ terminates after 3 cycles, returns 0, 3 rows |
| Backoff progression | 5 consecutive failures | ✅ sleeps exactly `[60,120,240,300,300]`; reset to 30 after recovery |

`iterations=None` with a `stop` that never flips loops forever — that is the **intended deployed behavior** (long-running worker), not a busy-loop defect.

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | apply-progress `#1340` has a full RED→GREEN table for WU1 and WU2. |
| All tasks have tests | ✅ | WU1 8 tests, WU2 9 tests; all 13 Guard-Matrix rows carry a covering test. |
| RED confirmed (tests exist) | ✅ | `test_ingest.py` (8) and `test_service_stubs.py` (10) exist. |
| GREEN confirmed (tests pass) | ✅ | 207/207 pass on independent execution. |
| Triangulation adequate | ✅ | Two symbols; three backoff cases (BitunixError, RequestException, 300s cap); stop-before-first and mid-loop; both models' unique constraints. |
| Safety Net for modified files | ✅ | `test_service_stubs.py` was a rewrite over a live baseline (199); full suite green before and after. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (pure service/loop logic) | 8 | 2 | pytest |
| Integration / DB (Django ORM, `django_db`) | 10 | 2 | pytest, pytest-django |
| **New/changed total** | **18** | **2** | |
| Full suite | 207 | 15 | pytest, pytest-django, pytest-cov |

### Changed-File Coverage

| File | Line % | Uncovered Lines | Rating |
|------|--------|-----------------|--------|
| `web/trading/ingest.py` | 100% | — | ✅ Excellent |
| `web/trading/models.py` | 100% | — | ✅ Excellent |
| `web/worker.py` | 97% | 122 (infinite idle sleep), 127 (`__main__`) | ✅ Excellent |

**Average changed file coverage**: 99%.

### Assertion Quality

Scanned both changed test files (Step 5f). No tautologies, no assertion without production-code execution, no ghost loops (the only loops are `for model in (...)` over hard-coded model tuples with a concrete assertion each). Empty-collection assertions (`market == {"funding": [], ...}`, `persist_market([], []) == (0,0)`) each have paired non-empty companions (`test_fetch_market_splits_and_maps_two_symbols`, `test_persist_market_round_trip`). `sleep.calls == [...]` asserts a spec-required observable (backoff sequence), not an internal detail. No mocks; the HTTP client is an injected stub.

**Assertion quality**: ✅ All assertions verify real behavior.

### Quality Metrics
**Linter**: ✅ No errors (ruff exit 0)
**Type Checker**: ➖ Not configured in this project
**Format**: ✅ 70 files formatted

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R1 global models | ✅ Implemented | `FundingSnapshot`/`TickerSnapshot` are plain `models.Model`, no `user`, unique `(symbol, ts)`. |
| R2 idempotent persistence | ✅ Implemented | `bulk_create(ignore_conflicts=True)` in one `transaction.atomic()`; **row-count delta**, not `len()` — the design's formula was wrong and was corrected in apply. |
| R3 ingestion | ✅ Implemented | `fetch_market` reuses `src.monitor.fetch_rows` 1:1; `datetime.fromtimestamp(ms/1000, tz=UTC)` once; `next_funding_time` raw ms. Empty *symbols* → `(0,0)`. Empty *response* diverges from spec wording (WARNING 2). |
| R4 worker loop | ✅ Implemented | `INGEST_POLL_SECONDS` (default 30), `min(backoff*2, 300)`, per-cycle log, injectable `iterations`/`stop`/`sleep`, SIGTERM/SIGINT `Event`. |
| R5 scheduler stub | ✅ Implemented | `scheduler.py` unchanged, shares `worker.idle_loop`. |
| R6 boundary | ✅ Implemented | `src/` framework-free; first `web/→src/` import is the intended direction only. |
| R7 read-only + no dep | ✅ Implemented | No order verb/path in new code; `requirements.txt` unchanged (git diff empty). |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 app = `trading` | ✅ Yes | Models added to the existing installed/migrated app. |
| D2 ship-without-prune, flagged | ✅ Yes | Documented in `design.md:33-34`, `proposal.md:62`, `explore.md:175`. No silent accumulation. |
| D3 reuse `src.monitor.fetch_rows` | ✅ Yes | `ingest.py:15,23`; no forked parser. |
| D4 plain loop, no RQ | ✅ Yes | No new runtime dependency; `requirements.txt` untouched. |
| Design `persist_market` code block | ⚠️ Deviation (good) | `design.md:64-67` shows the incorrect `len(bulk_create(...))` count; shipped code uses a row-count delta and is **correct**. Design doc is now stale (SUGGESTION 1). |
| `_MAX_BACKOFF_SECONDS` constant | ✅ Yes (minor) | Apply extracted the literal to a named module constant — behavior identical. |
| `idle_loop` unchanged for scheduler | ✅ Yes | `worker.py:114-123` byte-compatible contract with `scheduler.py`. |

## Issues Found

**CRITICAL**: None.

**WARNING 1 (LOW) — `tasks.md` checkboxes are all `[ ]` despite completed work.**
`openspec/changes/market-ingestion/tasks.md` shows `[ ]` for all 13 Guard-Matrix rows and WU1/WU2 tasks (29 unchecked, 0 checked), though every item is present and verified. Apply recorded completion in Engram `#1340` rather than the tracker-branch artifact. **Fix:** flip `[x]` for WU1 1.1–1.7, WU2 2.1–2.6, and the completed Guard-Matrix rows during archive.

**WARNING 2 (MEDIUM) — empty API response persists default rows, not 0; spec says 0.**
R3's "Empty input" scenario states: *"GIVEN an empty symbols list **or API response**, WHEN ingestion runs, THEN it does not raise and persists 0 rows."* Reproduced: an empty API payload (`tickers=[]`, `funding=[]`) with a non-empty symbol list makes `fetch_rows` emit **one row per requested symbol** (`funding_rate=0.0`, `funding_interval=8`, `next_funding_time=0`, prices `None`), and `persist_market` returns `(2,2)`. If the API ever returns an empty body without raising, the worker would write zero-valued rows into the time series. The scenario is only tested for the empty-*symbols* half; the empty-*response* half is untested. The design documents the row-per-symbol behavior, so spec and design conflict — the spec wording is the stricter claim. **Fix trigger:** either narrow the spec scenario to empty-symbols (record the row-per-symbol default as intended), or guard `fetch_market` to drop rows whose ticker+funding payloads are both empty before persisting. Not a crash, not a regression; a data-quality concern.

**WARNING 3 (LOW) — R6 "Web may depend on core" has no explicit boundary test.**
`tests/test_boundary.py` asserts only the forbidden direction (`src/` imports no Django) and the stdlib-only pure modules. The permitted direction is proven only implicitly: `test_ingest.py`/`test_service_stubs.py` import `trading.ingest`/`worker`, which import `src.monitor`/`src.client`/`src.config`, and those imports succeed. No test asserts the direction is allowed (or that `src/ → web/` is forbidden). **Fix trigger:** add a small boundary test asserting `src/` does not import `web`/`trading`/`scheduler` — cheap and closes the reverse direction the proposal explicitly calls a guard.

**WARNING 4 (LOW) — R7 "Dependency file unchanged" is untested.**
No test asserts `requirements.txt` is unchanged; verified here only by `git diff` (empty across the chain). Pre-existing pattern (the archived report had the same gap for R11). **Fix trigger:** if the dependency invariant matters, add a guard test that no new runtime import appears in `web/`/`src/` outside the declared set.

**SUGGESTION 1 — update `design.md` to match the shipped `persist_market`.**
The design snippet (`design.md:62-68`) uses `len(bulk_create(..., ignore_conflicts=True))` as the inserted count. That formula is wrong (Django returns all attempted objects); the shipped code correctly uses a row-count delta. The implementation is right — the design document should be corrected so future readers don't reintroduce the bug.

**SUGGESTION 2 — note the infinite-loop deployed behavior explicitly.**
`run_loop(iterations=None)` with no signal loops forever by design. It is the correct production behavior, but worth a one-line docstring note so it is not mistaken for a hang.

## Verdict

**PASS WITH WARNINGS**

Reproduced independently from scratch: **207/207 tests pass** (exit 0), `ruff check`/`ruff format --check` exit 0 (70 files), `makemigrations --check` clean, boundary green (4 passed), web coverage 94% (≥85), patch coverage 100% (0 missing on 85 lines). Every R1/R2/R4/R5 core scenario is COMPLIANT, and all 7 requirements are implemented. The design's `len(bulk_create(...))` count was a genuine bug; an adversarial probe confirms the **shipped row-count-delta is correct**. `src/` remains framework-free, the `web/→src/` direction is the intended one only, no order surface exists, and `requirements.txt` is unchanged. Open items are non-blocking: two partial scenarios (empty-API-response semantics — medium data-quality warning; an implicit web→core direction assertion), one untested-but-manually-verified dependency invariant, stale `tasks.md` checkboxes, and design-doc drift. **Archive decision: READY** — no blockers or criticals; address WARNING 2 before relying on the ingester against a flaky API, and fix the `tasks.md`/`design.md` hygiene during archive.

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
| Commits | `570a432` (PR1), `766d853` + `6d778b7` (PR2) |
| Chain diff | `feat/market-ingestion...feat/market-worker`, 6 files, +675/−22, sha256 `face8ce1…` |
