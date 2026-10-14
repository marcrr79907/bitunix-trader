# Archive Report: chart-host-extract

**Archived**: 2026-10-14
**Verdict**: `pass_with_warnings` (0 blockers, 0 criticals) — behavior-equivalent refactor.
**Delivery**: Single PR #157 (`refactor/chart-host-extract`) → `develop` merged (no chain).
**Issue**: #146 — **DEBT-5** (size-guard exemption retirement).
**Branch**: `refactor/chart-host-extract` → `develop`.

## What Shipped

Extracted the candle channel out of `chart-host.js` (326 → **286 lines**) into a
new **host-layer** sub-module `chart-host-candles.js`. Pure refactor — no
functional change, no new runtime dependency, CSP unchanged, `window.marketChart`
seam frozen at 8 keys, `src/` untouched.

| Area | Delivered |
|------|-----------|
| `chart-host-candles.js` (NEW) | Host-layer factory `createCandles(chart, chartType) → {getCandleSeries, getCandles, setCandles, updateCandle, remove}`. Owns `CANDLE_CTORS`, the candle series, the raw `candles` array, and the HA incremental state (`prevHa`/`lastHa`/`lastBarTime`). Imports pure `chart-core.js` (`upsertCandle`) + `chart-types-core.js` (`heikinAshi`/`nextHeikinAshi`). 82 lines. |
| `chart-host.js` (MODIFIED) | 326 → **286 lines**. Deleted: `import Core`, `CANDLE_CTORS`, HA state vars, the raw `candles` array, and the two full write bodies. `build()` ctor lines → `createCandles(chart, chartType)` at the exact prior position (after `createChart`, before `applyScale`); `remove()`/accessors/writes delegate. |
| `views.py` (MODIFIED) | `MODULE_ALLOWLIST` gains `"chart-host-candles"` (route served 200 / `text/javascript`). |
| `chart.html` (MODIFIED) | `modulepreload` tag for the new module. |
| `test_module_size_guard.py` (MODIFIED) | `ALLOWLIST` emptied to `frozenset()`; the exemption test rewritten to `test_no_module_is_exempt_and_chart_host_is_within_ceiling`. The guard now passes with **no exemption** — DEBT-5 retired. |

### Behavior-equivalence evidence

- **C1 same-bucket HA fix** (`if (!sameBucket) prevHa = lastHa;`) moved **verbatim** — independently reproduced (stable `[11,11,11]` across 3 same-bucket ticks, correct next-bucket chain from the closed bar).
- **#68 single-write-path** preserved: `setData` only in `setCandles`/build; `update` only in `updateCandle`.
- **8-key seam** unchanged — `main.js` literal still 8 keys; E2E asserts `=== 8`.
- **138 node tests pass with ZERO assertion edits** (`git diff origin/develop -- tests/js/chart-host.test.js` empty).
- Raw-candle reference identity preserved — `getCandles()` returns the module's live array that `upsertCandle` mutates.

## Requirements Satisfied (verification-evidence only)

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| market-chart | R14 (MODIFIED) | ✅ Module inventory now includes the host-layer `chart-host-candles.js`; `chart-host.js` ≤ ~300 (286); size guard `ALLOWLIST` empty — no exemption. DEBT-5 retired. Import-graph route test proves the new module serves. |
| chart-scales | CS4 (MODIFIED) | ✅ Candle-series/HA construction relocated to `chart-host-candles.js`; interface frozen; behavior unchanged (HA math still sourced from pure `chart-types-core.js`, raw array by reference, C1 rule verbatim). |
| market-chart | R1–R13, R15–R21 | ✅ Preserved untouched. |
| chart-scales | CS1, CS2, CS3, CS5, CS6, CS7 | ✅ Preserved untouched. |

**No requirement dropped.** No destructive merge (only R14/CS4 requirements replaced in place; all other requirements preserved).

## Warnings Carried (non-blocking)

- **W1 — L2 `diff-cover` gate is inert.** The only changed Python line (`views.py:53`, a `frozenset` element in `MODULE_ALLOWLIST`) is not coverage-instrumentable, so `diff-cover --fail-under=100` returns "No lines with coverage information in this diff" and scores nothing. **Not a coverage gap** — no executable Python path was added; the new route is proven dynamically by `test_import_graph_routes_resolve` (parses the real `./chart-host-candles.js` import → asserts `GET /market/chart-host-candles.js` = 200 + `text/javascript`, fails if the allowlist entry is absent). Recorded so a future reader does not misread L2 as a scored 100%.
- **W3 — E2E env fragility (pre-existing, DEBT-8 / #149).** Three documented WS tests fail locally with `KeyError: 'route'` (Playwright `route_web_socket` harness), identically on `develop`; CI deselects E2E (`addopts = "-m 'not e2e'"`). Additionally, each full-suite run flaked one *rotating* additional test via `wait_for_function` timeout; each passes in isolation. Not a regression of this change.
- **G1 — HA E2E coverage is smoke-only** (carried from chart-scales): the browser suite asserts the seam stays 8 keys but not HA values; the real HA math is carried by the node tests (verified here by an independent probe).
- **G2 — `tasks.md` checkboxes unmarked** (executor contract forbids editing `openspec/**`); consistent with F0–F3 precedent. Every acceptance artifact exists and passes at runtime.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| market-chart | Updated | R14 modified — inventory adds the host-layer `chart-host-candles.js`; `chart-host.js` back ≤ ~300 (286); size guard now passes with an **empty** `ALLOWLIST` (no exemption); new scenarios "New candle sub-module is served" and "No behavior change". R1–R13, R15–R21 preserved. |
| chart-scales | Updated | CS4 modified — module-boundary note: candle-series construction, raw candle array, and HA incremental state now live in `chart-host-candles.js`; interface frozen; behavior byte-identical (C1 verbatim); new scenario "HA live contract is unchanged after extraction". CS1–CS3, CS5–CS7 preserved. |

## Carry-forward

- **DEBT-8 (#149)** — the `route_web_socket` `KeyError: 'route'` harness issue remains open; local E2E WS coverage gap persists until fixed.
- **DEBT-5 (#146)** — **RESOLVED**: the `chart-host.js` size-guard exemption is retired (empty `ALLOWLIST`); no longer carried.
- Frozen seams (layered ESM inventory, 8-key `window.marketChart`, `window.SmcOverlayCore`, #68 single-write-path, per-user ownership) remain in force.

## SDD Cycle Complete

Planned (explore/proposal/specs/design/tasks) → implemented (single PR #157) →
verified (`pass_with_warnings`, 8/8 scenarios) → merged to `develop` → archived.

Traceability: `openspec/changes/archive/2026-10-14-chart-host-extract/`
(explore, proposal, specs, design, tasks, verify-report, archive-report); engram
`sdd/chart-host-extract/{archive-report,proposal,spec,design,tasks}`.
