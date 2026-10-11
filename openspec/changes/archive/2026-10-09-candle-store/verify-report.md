```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:741bbba89d39b345df279c2cd72008b9dd3b86ff1f7cfb2918241eef20b80dd6
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 9/9
scenarios: 33/34
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:d91a37537064b12ee88a099916795cc7e2b729e7c3b25a7f050fcdc5347c68bb
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
```

# Verification Report

**Change**: candle-store (issue #43) — single-PR delivery
**Version**: N/A (delta specs)
**Mode**: Strict TDD (openspec `config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Scope**: branch `feat/candle-store` (HEAD `cfcb8fe`), base `develop` (`3e187d4`). Commits: `3c24b99` (WU1), `b465d04` (WU2), `a97ac42` (WU3), `cfcb8fe` (patch-gate test). Diff vs `develop`: 22 files, +1728/−7 (code+docs+tests+specs).

This is an **adversarial, from-scratch verification** of the frozen branch. Everything below was reproduced independently: the full suite, lint/format, migration check, boundary/order scanners, the coverage and patch gates, and 14 throwaway probes executed from `/tmp` against the real tree (in-memory SQLite, repo untouched, working tree clean throughout). Apply's report was treated as a claim, not evidence. **No blockers, no critical findings.** Two honest warnings: a robustness gap in the backfill cursor loop (unreachable against the live API, which does honor `endTime`), and the recurring untested "requirements unchanged" invariant. Verdict: **PASS WITH WARNINGS**.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (Guard Matrix 16 + WU1 7 + WU2 5 + WU3 8 + Phase 4 3) | 39 |
| Tasks complete (present in tree + verified here) | 39 |
| Tasks incomplete | 0 |

All Guard-Matrix rows, WU1 1.1–1.7, WU2 2.1–2.5, WU3 3.1–3.8 and Phase-4 4.1–4.3 are present and independently verified. `tasks.md` checkboxes remain `[ ]` (0 checked / 39 unchecked) — apply intentionally left `openspec/**` planning artifacts untouched per its hard contract; see WARNING 3.

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
89 files already formatted
$ .venv/bin/python web/manage.py makemigrations --check --dry-run
No changes detected
```

**Tests**: ✅ 281 passed / ❌ 0 failed / ⚠️ 1 deselected (exit 0)
```text
$ .venv/bin/python -m pytest
281 passed, 1 deselected in 42.28s
```
The single deselection is the pre-existing `e2e` marker (`pyproject.toml` `addopts = "-q -m 'not e2e'"`), unchanged by this change. Baseline before this change was 242; the change adds **39** collected tests (apply reported 38 by its own arithmetic; the actual collected delta is 39, consistent with the patch-gate test `cfcb8fe` added last).

**Coverage**: web 96% / threshold 85% → ✅ Above; patch gate 100% → ✅
```text
$ .venv/bin/python -m pytest --cov --cov-report=xml
$ .venv/bin/coverage report --include="web/*" --fail-under=85
TOTAL   621   24   96%
$ .venv/bin/diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100
src/client.py (100%)  web/market/quotes.py (100%)  web/trading/candles.py (100%)
web/trading/management/commands/backfill_candles.py (100%)  web/trading/models.py (100%)  web/worker.py (100%)
Total: 122 lines, Missing: 0 lines, Coverage: 100%
```

## L1 — Independent Test Evidence

| Check | Command | Result |
|-------|---------|--------|
| Full suite | `.venv/bin/python -m pytest` | ✅ 281 passed, exit 0 |
| Lint | `.venv/bin/ruff check .` | ✅ All checks passed, exit 0 |
| Format | `.venv/bin/ruff format --check .` | ✅ 89 files formatted, exit 0 |
| Migrations | `.venv/bin/python web/manage.py makemigrations --check --dry-run` | ✅ No changes detected, exit 0 |
| Boundary | `.venv/bin/python -m pytest tests/test_boundary.py` | ✅ 4 passed, exit 0 |
| Core-isolation | `grep -rn django src/` | ✅ 0 offenders |
| Requirements diff | `git diff develop..HEAD -- requirements.txt` | ✅ empty |
| Order scanner | `.venv/bin/python -m pytest tests/web/test_no_order_surface.py` | ✅ 36 passed, exit 0 |

Migration↔model parity: `0003_candle.py` declares exactly the fields/constraints/index in `models.py`; `makemigrations --check` confirms zero drift. `sqlmigrate trading 0003` emits a single `CREATE TABLE trading_candle (...)` **plus** `CREATE INDEX ix_candle_symbol_interval_time ON trading_candle (symbol, interval, time)` — the composite index is really created (see Probe H); the unique constraint is inline. Additive only; no other table touched.

## L2 — Coverage Gates

| Gate | Command | Result |
|------|---------|--------|
| Coverage XML | `.venv/bin/python -m pytest --cov --cov-report=xml` | ✅ exit 0, `coverage.xml` written |
| Web gate | `.venv/bin/coverage report --include="web/*" --fail-under=85` | ✅ exit 0, TOTAL 96% |
| Patch gate | `.venv/bin/diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` | ✅ exit 0, 122 lines, 0 missing, 100% |

All six changed source files are at 100% patch coverage. `web/worker.py` is 97% project-wide (missing lines are the pre-existing `idle_loop` sleep and `__main__`, outside the patch diff). `web/config/settings/prod.py` 0% is pre-existing and unrelated.

## L3 — Spec Compliance Matrix

### candle-store (R1–R7, 20 scenarios)

| Requirement | Scenario | Test / Evidence | Result |
|-------------|----------|-----------------|--------|
| R1 | Global model carries no owner | `test_candle_is_global_not_owned` + probe `_meta.get_field("user")` raises | ✅ COMPLIANT |
| R1 | Unique key is (symbol, interval, time) | `test_unique_symbol_interval_time_rejects_duplicate` + `test_same_time_different_series_is_allowed` | ✅ COMPLIANT |
| R1 | Composite index present | `test_composite_index_present` + `sqlmigrate` DDL + Probe H | ✅ COMPLIANT |
| R2 | Schema check green | `makemigrations --check --dry-run` → No changes detected | ✅ COMPLIANT |
| R2 | No destructive operation | `sqlmigrate 0003` = one `CREATE TABLE` + one `CREATE INDEX`; no ALTER/DROP | ✅ COMPLIANT |
| R3 | Backward pagination advances the cursor | `test_backfill_advances_cursor_from_oldest_row` + Probe D | ✅ COMPLIANT |
| R3 | Empty page ends the series | `test_backfill_empty_page_stops_series_without_error` + Probe D | ✅ COMPLIANT |
| R3 | `--start` bounds the earliest candle | `test_backfill_start_bounds_earliest_candle`, `test_backfill_start_after_all_data_persists_nothing` | ✅ COMPLIANT |
| R3 | Idempotent re-run | `test_backfill_rerun_is_idempotent` + Probe D | ✅ COMPLIANT |
| R3 | Resume from oldest stored time | `test_backfill_resumes_from_oldest_stored_time` + Probe D | ✅ COMPLIANT |
| R3 | `--dry-run` persists nothing | `test_backfill_dry_run_persists_nothing` + Probe D | ✅ COMPLIANT |
| R3 | Throttle without real sleeps | `test_backfill_persists_all_rows_and_logs_pages` (`sleep.calls == [0.15]`) | ✅ COMPLIANT |
| R4 | Forming candle not persisted | `test_fetch_closed_candles_drops_forming_and_tags_series` + `test_run_once_persists_closed_candle_and_keeps_tick_counts` | ✅ COMPLIANT |
| R4 | Closed candle persisted | `test_run_once_persists_closed_candle_and_keeps_tick_counts` + Probe B | ✅ COMPLIANT |
| R4 | Tick ingestion unaffected | `test_run_once_candle_failure_does_not_break_ticks`, `test_run_once_unexpected_candle_error_is_isolated`, `test_run_loop_survives_candle_failure` + Probe B | ✅ COMPLIANT |
| R4 | Repeat cycle is idempotent | `test_persist_candles_idempotent` + Probe E | ✅ COMPLIANT |
| R5 | No order surface added | `test_no_order_surface_in_web_and_src` (36 passed; recursively scans `web/`+`src/`, so `candles.py`/command are in scope) | ✅ COMPLIANT |
| R6 | Core boundary green | `tests/test_boundary.py` (4 passed); `grep django src/` empty | ✅ COMPLIANT |
| R6 | No runtime dependency added | `git diff develop..HEAD -- requirements.txt` empty — **by inspection, no test** | ⚠️ PARTIAL (see WARNING 2) |
| R7 | Volumetry figures recorded | `docs/deployment.md` "Candle store volumetry": per-interval table, 623,676/yr, ~1.87M backfill, ~1,709/day | ✅ COMPLIANT |

### market-chart delta (R1, R3, 14 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 | Correct URL and params | `test_kline_hits_public_path_unsigned` | ✅ COMPLIANT |
| R1 | Mapping ms→s, floats, quote_vol | `test_kline_maps_ms_to_unix_seconds_and_floats`, `test_kline_maps_quote_vol_when_present` | ✅ COMPLIANT |
| R1 | Range params pass through | `test_kline_range_params_pass_through_when_set` | ✅ COMPLIANT |
| R1 | Range params omitted when None | `test_kline_range_params_omitted_when_none`, `test_kline_defaults_match_spec` | ✅ COMPLIANT |
| R1 | Missing quoteVol → None | `test_kline_maps_ms_to_unix_seconds_and_floats` (exact dict asserts `quote_vol: None`) | ✅ COMPLIANT |
| R1 | API error → BitunixError | `test_kline_api_code_ne_zero_raises`, `test_kline_http_ne_200_raises` | ✅ COMPLIANT |
| R1 | Empty upstream → [] | `test_kline_empty_data_returns_empty_list`, `test_kline_null_data_returns_empty_list` | ✅ COMPLIANT |
| R3 | Payload candle exactly five fields | `test_payload_strips_quote_vol_to_exactly_five_keys`, `test_endpoint_200_exact_shape` + Probe C | ✅ COMPLIANT |
| R3 | Candles sorted and deduplicated | `test_payload_dedupes_and_sorts_ascending_last_wins`, `test_endpoint_200_exact_shape` | ✅ COMPLIANT |
| R3 | Overlay gaps omitted | `test_payload_overlays_are_time_value_pairs_without_nulls` | ✅ COMPLIANT |
| R3 | Invalid interval → 400 | `test_endpoint_invalid_interval_is_400` | ✅ COMPLIANT |
| R3 | Invalid symbol → 400 | `test_endpoint_upstream_api_reject_is_400` | ✅ COMPLIANT |
| R3 | Empty upstream → 200 empty | `test_endpoint_empty_upstream_is_200_empty` | ✅ COMPLIANT |
| R3 | Unauthenticated → redirect | `test_endpoint_anonymous_redirects_to_login` | ✅ COMPLIANT |

**Compliance summary**: 9 requirements, **9 implemented**. 34 scenarios, **33 compliant / 1 partial** (R6 dependency-file invariant verified by inspection only).

## Independent Adversarial Probes (executed from `/tmp`)

14 probes across `/tmp/opencode/probe_candles.py` (10) and `/tmp/opencode/probe_edge.py` (4 executed + reachability checks), repo untouched.

| # | Probe | Method | Result |
|---|-------|--------|--------|
| A | `is_closed` exact boundary | `t+span-1`→False, `t+span`→True for 5m/1h/1d/1M | ✅ exact, no off-by-one |
| A2 | Forming at exact now | `is_closed(t, "1h", t)` | ✅ False |
| B | Worker candle raise isolation | `run_once` with `kline` raising `RuntimeError` | ✅ ticks persist, result stays `(1,1)`, 0 candles |
| B2 | `run_once` signature | `inspect.signature` | ✅ `(client, symbols)`, return contract `(funding, ticker)` unchanged |
| C | Payload exactly five keys | `get_kline_payload` with `quote_vol` present | ✅ every candle `{time,open,high,low,close}`; overlays `{time,value}` |
| D | Backfill full contract | bounded stub: fill / re-run 0 / resume from `Min(time)` / dry-run 0 / empty-stop / `--start` bound / cursor advances | ✅ 7/7 |
| D2 | Cursor terminates (finite series) | stub exhausting a 5-row series without `--start` | ✅ terminates via empty page, ≤6 calls |
| E | Duplicate rows in one page | `persist_candles([row, row])` | ✅ inserted == 1 |
| F | `quote_vol` numeric-zero fidelity | `quoteVol=0`/`0.0`/`""` vs `"0"`/absent | ⚠️ numeric 0 → None (see SUGGESTION 1) |
| G | Non-advancing cursor | stub ignoring `endTime`, same row forever | ❌ **infinite loop** (see WARNING 1) |
| H | Migrations really create index | `sqlmigrate trading 0003` | ✅ `CREATE INDEX ix_candle_symbol_interval_time` present |
| I | Live `endTime` honored | `curl` real kline with `endTime` | ✅ returns strictly earlier rows; WARNING 1 unreachable live |
| J | Live `quoteVol` shape | `curl` real kline | ✅ always a non-empty string → numeric-0 path unreachable live |
| K | Broad except audit | grep `except` across new code | ✅ only the two intended isolated sites |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | apply-progress `#1367` has a full RED→GREEN→TRIANGULATE table for WU1/WU2/WU3. |
| All tasks have tests | ✅ | WU1 10, model 5, WU2 12, WU3 11 (candles 7 + worker 4), market-api +2; all 16 Guard-Matrix rows carry a covering test. |
| RED confirmed (tests exist) | ✅ | All named test files exist in the tree. |
| GREEN confirmed (tests pass) | ✅ | 281/281 pass on independent execution, exit 0. |
| Triangulation adequate | ✅ | Same-time/different-series; 4 `is_closed` boundaries + 1M=31d; both error classes; BitunixError+ValueError; payload vs endpoint five-key assertions. |
| Safety Net for modified files | ✅ | Full suite green before/after; `test_client_kline.py`/`test_market_api.py` modified, existing cases preserved. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (pure: `is_closed`, `kline` mapping/params, payload projection) | 18 | 3 | pytest |
| Integration / DB (Django ORM, `django_db`, `call_command`) | 23 | 4 | pytest, pytest-django |
| E2E | 0 | 0 | not applicable |
| **Change total** | **39** | **7** | pytest, pytest-django, pytest-cov |
| Full suite | 281 | 39 | pytest, pytest-django, pytest-cov |

### Changed-File Coverage

| File | Line % (patch) | Uncovered Lines | Rating |
|------|----------------|-----------------|--------|
| `src/client.py` | 100% | — | ✅ Excellent |
| `web/trading/models.py` | 100% | — | ✅ Excellent |
| `web/trading/candles.py` | 100% | — | ✅ Excellent |
| `web/trading/management/commands/backfill_candles.py` | 100% | — | ✅ Excellent |
| `web/market/quotes.py` | 100% | — | ✅ Excellent |
| `web/worker.py` | 100% | — | ✅ Excellent |

**Average changed file coverage (patch)**: 100% on 122 changed lines.

### Assertion Quality

Scanned all 7 changed/created test files (Step 5f). No tautologies, no assertions without production-code execution, no ghost loops (every `for`/`all` iterates a literal non-empty list). Notable checks:

- `test_fetch_closed_candles_drops_forming_and_tags_series` asserts the kept candle's `time`, `symbol`, `interval` (value assertions, not just length); paired with `test_fetch_closed_candles_queries_limit_2_every_interval` covering the query fan-out.
- `test_backfill_advances_cursor_from_oldest_row` asserts the exact next `endTime` (`oldest*1000-1`) — the spec-critical cursor contract, not a mock call count.
- `test_run_once_*` assert the real DB row counts plus the `(1,1)` return contract; `test_run_once_unexpected_candle_error_is_isolated` deliberately drives `ValueError` to pin the broad-except isolation.
- `test_payload_strips_quote_vol_to_exactly_five_keys` asserts the exact dict list and `"quote_vol" not in c` — the exactness the delta spec pins.
- Endpoint test `_upstream_rows` was changed to inject `quote_vol`, and `test_endpoint_200_exact_shape` still asserts `set(candle) == {time,open,high,low,close}` — a silent weakening would have failed; it does not.

**Assertion quality**: ✅ All assertions verify real behavior.

### Quality Metrics
**Linter**: ✅ No errors (ruff exit 0)
**Type Checker**: ➖ Not configured in this project
**Format**: ✅ 89 files formatted

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R1 global Candle | ✅ Implemented | Plain `models.Model`, no `user`; `UniqueConstraint` + composite `Index` both present and in the migration DDL. |
| R2 additive migration | ✅ Implemented | `0003_candle`, depends `0002_market_snapshots`, one table only. |
| R3 backfill | ✅ Implemented | `run()` seam; backward `endTime` cursor `min*1000-1`; resume from `Min(time)`; `--start` filter+stop; `ignore_conflicts`; injectable `throttle`/`out`; error aborts only that series. |
| R4 continuous ingestion | ✅ Implemented | `is_closed` wall-clock rule; `limit=2` drops forming; `run_once` appends isolated candle cycle after `persist_market`, returns `(funding, ticker)`. |
| R5 read-only | ✅ Implemented | No order verb/path in new model/command/worker; scanner recursive over new files. |
| R6 boundary + no dep | ✅ Implemented | `src/client.py` imports only stdlib+requests; `requirements.txt` untouched. |
| R7 volumetry | ✅ Implemented | `docs/deployment.md` table + totals + backfill estimate. |
| market-chart R1/R3 | ✅ Implemented | `kline()` gains optional range params + `quote_vol`; `get_kline_payload` projects to `CHART_KEYS` so quote_vol never reaches the response. |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| ADR-a direct persist per interval | ✅ Yes | `fetch_closed_candles` iterates `CANDLE_INTERVALS`, no aggregation. |
| ADR-b closure `now >= time + INTERVAL_SECONDS` | ✅ Yes | 1M=2678400 (31d) exactly as pinned; boundary proven by probe A. |
| ADR-c `candles.py` deep module | ✅ Yes | Present, snapshot-focused `ingest.py` untouched. |
| ADR-d strip in `get_kline_payload` | ✅ Yes | `CHART_KEYS` projection at the sole chart seam; client keeps `quote_vol`. |
| Isolation in `run_once` | ✅ Yes | `try/except Exception` after persist, `ponytail` comment present; return contract preserved. |
| Design `candles.py` in WU3 | ⚠️ Deviation (benign) | Created in WU2 because the command imports its constants/`persist_candles`; single PR so no ordering issue. Documented by apply. |
| Design `--sleep` → throttle/delay split | ⚠️ Deviation (benign) | `_backfill_series` takes `throttle` callable + `delay` float to avoid `sleep(sleep)` shadowing; behavior identical. Documented by apply. |
| `1M` partial-candle safety | ✅ Yes | 31d guarantee honored; ≤3-day delay tradeoff is documented. |

## Issues Found

**CRITICAL**: None.

**WARNING 1 (LOW–MEDIUM) — backfill cursor loop has no defense against a server that ignores `endTime`.**
`_backfill_series` sets `cursor = oldest_time * 1000 - 1` and loops until an empty page. If the upstream ever returned a page whose oldest row is `>=` the requested cursor (i.e. `endTime` not honored), the cursor would not advance and the command would spin forever while consuming the shared 10 req/s budget. **Probe G reproduces an infinite loop** (capped at 50 calls) with a stub that ignores `endTime`. **Reachability: not reachable against the live API** — probe I confirms `GET /kline?...&endTime=1700000000000` returns rows strictly below the cursor, so the loop always advances today. This is a robustness gap, not an active defect: the design explicitly relies on the backward-pagination contract. **Fix trigger:** break when the new cursor is not strictly less than the previous one (one guard line), or cap pages per series. Low priority given live behavior; worth a defensive assert.

**WARNING 2 (LOW) — R6 "requirements.txt unchanged" is untested.**
No test asserts the dependency invariant; verified here only by `git diff develop..HEAD -- requirements.txt` (empty). Recurrence of the prior market-ingestion WARNING 4. **Fix trigger:** add a guard test that the declared runtime import set does not grow (or an explicit `requirements.txt` hash/absence test).

**WARNING 3 (LOW) — `tasks.md` checkboxes are all `[ ]` despite completed work.**
`openspec/changes/candle-store/tasks.md` shows 0 checked / 39 unchecked, though every item is present and verified. Apply recorded completion in Engram `#1367` rather than the tracker-branch artifact, per its hard "do not edit openspec/**" contract. Planning-artifact hygiene, not a code defect. **Fix:** flip `[x]` during archive.

**SUGGESTION 1 — `quote_vol` falsy guard drops a numeric/empty `quoteVol`.**
`float(r["quoteVol"]) if r.get("quoteVol") else None` maps a numeric `0`/`0.0`/`""` to `None`. The live API emits `quoteVol` as a non-empty **string** (probe J), so `"0"` maps correctly to `0.0` and the numeric-empty path is unreachable. It is a latent fidelity wrinkle, not a spec violation (spec says missing → None; a numeric type never occurs). **Fix trigger:** use `r.get("quoteVol") is not None` if the upstream type ever changes. Acknowledged in the spot; no change required now.
**Where**: `src/client.py:147`.

**SUGGESTION 2 — composite index is redundant with the unique constraint.**
`ix_candle_symbol_interval_time` duplicates the covering index Postgres already builds for `uniq_candle_symbol_interval_time`. The design acknowledges this and keeps it because spec R1 mandates both (`design.md:21-22`, `ponytail:` note). No action; recorded for the archive reviewer.

**SUGGESTION 3 — R6 permitted web→core direction has no explicit boundary test.**
`tests/test_boundary.py` asserts only the forbidden direction (`src/` imports no Django); the allowed `web/ → src/` direction is proven implicitly by imports succeeding. Same note as the prior report (WARNING 3 there). Informational.

## Verdict

**PASS WITH WARNINGS**

All gates reproduced green on a clean working tree: **281/281 tests pass** (exit 0, +39 over the 242 baseline), `ruff check`/`ruff format --check` exit 0 (89 files), `makemigrations --check` clean, boundary 4/4 and order scanner 36/36 green, web coverage 96% (≥85), and patch coverage **100%** on 122 changed lines. `requirements.txt` is untouched and `src/` stays framework-free. Migration DDL was inspected directly: the `candles` table, the unique constraint, and the composite index are all really created. Every one of the 34 spec scenarios maps to a passing covering test except the dependency-file invariant, which is verified by diff inspection. 14 independent probes from `/tmp` confirmed `is_closed` boundaries exactly, worker candle-failure isolation (ticks survive, `(funding, ticker)` contract intact), the exact five-key payload projection, and the full backfill contract (idempotent, resumable, dry-run, `--start` bound, empty-stop, cursor advance). Two honest warnings remain — a defensive gap in the backfill loop for a hypothetical server that ignores `endTime` (proven unreachable against the live API) and the untested dependency invariant — plus planning-artifact hygiene and two acknowledged design notes. No blockers, no criticals. **Archive decision: READY.**

## Traceability

| Artifact | Reference |
|----------|-----------|
| Proposal | `openspec/changes/candle-store/proposal.md` |
| Design | `openspec/changes/candle-store/design.md` (ADR-a/b/c/d, closure map) |
| Tasks | `openspec/changes/candle-store/tasks.md` |
| Delta specs | `specs/candle-store/spec.md` (R1–R7), `specs/market-chart/spec.md` (R1, R3) |
| Code | `web/trading/models.py`, `web/trading/candles.py`, `web/trading/management/commands/backfill_candles.py`, `web/trading/migrations/0003_candle.py`, `web/worker.py`, `web/market/quotes.py`, `src/client.py` |
| Docs | `docs/deployment.md` (volumetry) |
| Tests | `tests/test_client_kline.py`, `tests/web/test_candles_model.py`, `tests/web/test_candles.py`, `tests/web/test_backfill_candles.py`, `tests/web/test_worker_candles.py`, `tests/web/test_market_api.py` |
| Apply evidence | Engram `#1367` (`sdd/candle-store/apply-progress`) |
| Commits | `3c24b99` (WU1), `b465d04` (WU2), `a97ac42` (WU3), `cfcb8fe` (patch-gate test) |
| Branch diff | `origin/develop...HEAD`, 22 files, +1728/−7, sha256 `741bbba8…` |
| Probes | `/tmp/opencode/probe_candles.py` (10 pass), `/tmp/opencode/probe_edge.py` (edge/reachability) |


## Post-verify fix (by orchestrator)

- WARNING 1 (backfill cursor monotonic guard) was fixed in `bd3b0b3`: the loop now breaks when the new cursor is not strictly older than the previous one, plus a regression test (`test_backfill_stops_when_upstream_ignores_endtime`). Patch gate stays 100% (125 lines). WARNING 2 (dep-invariant inspection-only) and SUGGESTIONS remain non-blocking; tasks.md checkboxes flipped at archive.
