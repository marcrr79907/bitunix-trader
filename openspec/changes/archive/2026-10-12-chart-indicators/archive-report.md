# Archive Report: chart-indicators

**Archived**: 2026-10-12
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 criticals) — 6/6 requirements, 41/44 scenarios
**Delivery**: tracker PR #80; feature-branch chain #81 → #82 → #83 → `develop`
**Merged range**: `1a28ef9..develop` (trailing commits after the public-repo prep #79)
**Merged commit**: PR #80 merge `8e81a26` on `develop`

## What Shipped

Configurable, TradingView-style indicators: price overlays + separate sub-panes,
with all math remaining server-side (single source). Issue #70, Fase A1.

| Area | Delivered |
|------|-----------|
| Pure math | `src/indicators.py`: `macd` (12/26/9 → line/signal/histogram), `bollinger` (20, 2σ → upper/middle/lower), `stochastic` (14,3 → %K/%D); same list-in/list-out, leading-`None` warm-up, no-mutation, stdlib-only contract |
| Payload | `web/market/quotes.py`: token registry, selectable `indicators`, derived warm-up `max(20, max first-valid)` (MACD → 33), `want = limit + warmup`, upstream clamp ≤ 200, response gains `panes` + volume; candles stay exactly 5 keys |
| Validation | `web/market/views.py`: unknown token → 400 before payload; flat param validation; MACD ordering `fast >= slow` → 400 |
| Adapter | `chart.js`: static `REGISTRY` + `PANE_ORDER`, v5 `paneIndex` rendering, rebuild-on-toggle (config change → `setData`), generalized `updateLastPoint` for every active series at close |
| UI | `chart.html`: keyboard-operable toggle `<fieldset>` in the side panel (design tokens) |
| Tests | `tests/test_indicators.py` (pure fixtures) + `tests/web/test_market_api.py` (selection/warm-up/shape) + `tests/web/test_market_e2e.py` (pane/toggle E2E) |

Chain commits: PR1 `65b8e5f` (indicators) + `248a39c` (MACD signal fix); PR2
`1df274d` (registry/selection/warm-up) + `043858f` (400 guard); PR3 `d79833c`
(adapter panes, toggles, pane E2E). Chain diff: **9 files, +1224/−80**.

## Verify Findings

Verdict `pass_with_warnings`; 0 blockers, 0 criticals **after** one CRITICAL and
one BLOCKER were found and fixed:

- **CRITICAL (fixed)** — MACD with `fast > slow` caused an unhandled `TypeError`
  in the signal-line EMA slice → HTTP 500. Fixed in the pure function
  (`248a39c`: signal uses the valid suffix, not `slow-1`) **and** guarded at the
  endpoint (`043858f`: `macd_fast >= macd_slow` → 400), with a regression test
  expecting 400. Re-probed: function no-raise for reversed/equal ordering;
  endpoint 400 for `fast >= slow`, 200 for `fast < slow`; default output
  byte-identical.
- **BLOCKER (fixed)** — the CRITICAL fix-rebase silently dropped PR3 (branch tip
  was byte-identical to the payload tip). Found by re-verify; fixed by
  cherry-picking PR3 back (`d79833c`). Re-verified: `d79833c` is an ancestor of
  HEAD, `chart.js` carries the pane registry, E2E 8/8.

Remaining WARNINGS (non-blocking):

- **W1** — R6 "every active series advances" / "no series deforms" and R1
  "deterministic output" are inspection/partial-test only (no call-twice test;
  no per-series advance assertion).
- **W3** — the MACD default-parameter fixture is monotonic
  (`[float(i) for i in range(40)]`), so no test asserts a non-trivial default
  MACD curve.

**Process note**: the SDD sub-agents had intermittent "Bad request" failures
earlier in the session (same class of flakiness as the `chart-live-consistency`
cycle); evidence was gathered inline.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| technical-indicators | R1 pure functions | ✅ `macd`/`bollinger`/`stochastic` added; crash-free for all orderings |
| technical-indicators | R2 warm-up alignment | ✅ 25/33, 19, 13/15 verified |
| technical-indicators | R4 guards | ✅ Bollinger flat-window collapse + stochastic zero-range `None` |
| market-chart | R3 kline endpoint | ✅ selectable set, `{candles,overlays,panes}`, 400 validation, clamp |
| market-chart | R4 derived warm-up | ✅ `max(20, max first_valid)` (MACD → 33) |
| chart-live-stream | R6 active series on close | ✅ generalized `updateLastPoint`; rebuild-on-toggle via the history path |

## Gates

`python -m pytest` 434 passed / 8 deselected (exit 0); E2E `-m e2e` 8 passed;
`node --test tests/js` 9 passed; `ruff check` + `ruff format --check` clean;
migrations clean; patch gate 100% (166 lines, 0 missing); `requirements.txt`,
CSP, and `chart-core.js` unchanged; boundary + order-scanner green.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| technical-indicators | Updated | R1 +3 functions & 5 scenarios; R2 +3 warm-up rows & 2 scenarios; R4 +Bollinger/stochastic guards & 2 scenarios; R3/R5–R8 preserved |
| market-chart | Updated | R3 rewritten (selectable indicators, `panes`, params, clamp; +7 scenarios, 8 preserved); R4 rewritten (derived warm-up; +1 scenario, 4 preserved); R1/R2/R5–R9 preserved |
| chart-live-stream | Updated | R6 generalized to every active overlay/pane series; +3 scenarios (was 1); R1–R5/R7 preserved |

## Carry-forward

- None blocking. W1/W3 are warning-level coverage gaps (inspection-only
  assertions + a monotonic MACD default fixture); the SUGGESTION that
  `_parse_params` rejects the MACD invariant even when `macd` is not selected is
  a safe over-rejection with no UI path.

## SDD Cycle Complete

Planned → implemented (3-PR feature-branch chain) → verified (CRITICAL + BLOCKER
found and fixed) → merged (tracker PR #80) → archived.

Traceability: `openspec/changes/archive/2026-10-12-chart-indicators/`
(explore, proposal, design, specs, tasks, verify-report); engram
`sdd/chart-indicators/{proposal,spec,design,tasks,apply-progress,verify-report}`.
