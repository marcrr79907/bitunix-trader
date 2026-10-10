# Archive Report: test-debt

**Archived**: 2026-10-09
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 criticals) — 3/3 requirements, 13/13 scenarios, 315/315 tests
**Delivery**: single PR — PR #55 (`feat/test-debt`) → `develop`
**Merged commit range**: `ae64c06`…`f294aaf` on `develop` (PR #55 merge `f294aaf`; branch commits `ae64c06` planning, `5360d19` guard, `5349dc8` E2E, `2e22dee` doc, `64707fa` scan assertion, `8508c57` tasks done + verify report)

## What Shipped

Issue #46 closes the three LOW verification debts from the Phase-4 (market-chart)
verify so R5 and R7 carry real evidence instead of static inspection, and the
`manage.py` coverage omission is a documented contract. Test/doc-only — zero
`web/`/`src/` production lines and `requirements.txt` byte-identical.

| Area | Delivered |
|------|-----------|
| E2E (W1) | `tests/web/test_market_e2e.py` — `page.route_web_socket("wss://fapi.bitunix.com/**")` installs a mocked socket **before** `goto`; asserts parsed `unsubscribe(market_kline_1min)`→`subscribe(market_kline_5m)` frame order on `#interval` switch, and same-bucket in-place update (length +1, last `time` unchanged); bounded `_poll` for boot frames, no fixed long sleep |
| Guard (W2) | `tests/test_dependency_guard.py` (new) — AST `ast.walk` roots over `web/**`+`src/**` (52 files), allowlist = `sys.stdlib_module_names ∪ declared ∪ derived local`; positive/negative controls; requirements-sync test fails on an unmapped declared dist; `test_guard_actually_scans_the_tree` (added `64707fa`) asserts `scanned > 10` so the guard cannot pass vacuously |
| Doc (R9) | `pyproject.toml` `[tool.coverage.run].omit` — comment names `tests/web/test_manage_boot.py` as `web/manage.py`'s contract; the omit entry is kept |
| Spec | `openspec/specs/market-chart/spec.md` — R5/R7 verification methods updated, R9 added |
| Reused as-is | `chart.js` (`sendSubscribe`/`onPush`/`bucket`/`backoff`/`switchTo`, unchanged), `tests/test_boundary.py` idiom, `tests/web/test_manage_boot.py` contract |

## Requirement Outcomes

| Req | Domain | Outcome | Notes |
|-----|--------|---------|-------|
| R5 | market-chart | ✅ Green | Two live-candle scenarios now driven by mocked `route_web_socket` (parsed frames, deterministic); reconnect inspection-verified per delta wording (single pure capped expression, no in-browser timing) |
| R7 | market-chart | ✅ Green | AST guard passes real 52-file tree; negative control fails on injected `import pandas` against the real tree; stdlib/declared/local/relative ignored; `psycopg[binary]→psycopg`, `dj-database-url→dj_database_url`; sync test fails on unmapped dist; `web`/`src` + `requirements.txt` diffs empty |
| R9 | market-chart | ✅ Green | `pyproject.toml` omit kept, comment names `tests/web/test_manage_boot.py`; boot behavior locked by the passing subprocess test |

**Legend**: ✅ green · ⚠️ partial (invariant holds; test-coverage gap).

## Carry-Forward Items

1. **E2E is dev-only (not in CI)** — the mocked-socket R5 scenarios run only under
   `-m e2e`; CI never downloads a browser and `chart.js` is not coverage-instrumented,
   so the JS layer keeps no CI signal. Accepted by design; revisit if the JS layer
   gains its own test runner.
2. **Dependency allowlist needs manual upkeep (intended friction)** — adding a runtime
   dependency requires a dist→import-root mapping in `tests/test_dependency_guard.py`;
   the requirements-sync test makes the missing mapping fail loudly and actionably.
3. **`chart.js` unrelated SUGGESTIONS stay tracked** — 295 lines vs the original
   ~120–140 design estimate and the `net::` console filter are pre-existing, out of
   scope here; carried from the candle-pagination archive.
4. **SUGGESTION 1 (ordering E2E tail assert is not a bounded poll)** — `ops[-2:]` is
   asserted immediately after the REST-redraw `wait_for_function`; `switchTo` emits
   both frames synchronously on `change` (6/6 runs stable). Not reopened; add a bounded
   poll if it ever flakes.

## Verify Findings (non-blocking)

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| S1 | Suggestion | Guard lacked a scan-nonzero assertion — could pass vacuously if `web`/`src` held no `.py` files | ✅ **Closed by `64707fa`** — `test_guard_actually_scans_the_tree` asserts `scanned > 10` |
| W1 | Low | Patch/coverage gate is vacuous for this change: coverage `source = ["web","src"]`, all changed lines are in `tests/`, so `diff-cover --fail-under=100` reports "No lines with coverage information in this diff" and measures nothing | Accepted by design — test/doc-only change; no production line to protect |
| W2 | Low | Reconnect scenario has no runtime test (inspection-verified) | Accepted per spec — delta explicitly permits inspection; exposing `backoff` would require a production `chart.js` edit |
| W3 | Low | `tasks.md` checkboxes were not updated during apply | ✅ **Closed at archive** — archived copy is 25/25 `[x]` (0 unchecked), verified here; marks restored in `8508c57` |

## SDD Cycle Complete

Planned (`ae64c06`) → implemented (`5360d19`, `5349dc8`, `2e22dee`) → verified
(`pass_with_warnings`, 0 blockers, 0 criticals; `8508c57`) → guard suggestion closed
(`64707fa`) → merged (PR #55 → `develop`, `f294aaf`) → archived.

Delta spec merged into the main spec store (source of truth):

- `openspec/specs/market-chart/spec.md` — R5 and R7 **replaced** with the delta text;
  R9 **added**; R1, R2, R3, R4, R6, R8 **preserved** unchanged. Result: **9
  requirements, 46 scenarios**, coherent, nothing dropped.

No new capability was created (`market-chart` was modified in place). Merge was
non-destructive — verified by heading inventory before/after.

Archive audit trail: `openspec/changes/archive/2026-10-09-test-debt/`
(explore, proposal, specs, design, tasks, verify-report, archive-report).

## Traceability — Engram Observation IDs

| Artifact | Observation ID |
|----------|----------------|
| `sdd/test-debt/explore` | 1390 |
| `sdd/test-debt/proposal` | 1391 |
| `sdd/test-debt/spec` | 1392 |
| `sdd/test-debt/design` | 1393 |
| `sdd/test-debt/tasks` | 1394 |
| `sdd/test-debt/apply-progress` | 1395 |
| `sdd/test-debt/verify-report` | 1396 |
| `sdd/test-debt/archive-report` | 1397 |

Merged specs have no standalone Engram observations — they live in the OpenSpec
file store (`openspec/specs/market-chart/spec.md`).
