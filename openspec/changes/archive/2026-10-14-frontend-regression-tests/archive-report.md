# Archive Report: frontend-regression-tests

**Archived**: 2026-10-14
**Verdict**: `pass_with_warnings` (0 blockers, 0 criticals) — TEST-ONLY change.
**Delivery**: Feature Branch Chain — 3 slices, one per issue, all based on the
tracker branch; tracker PR #155 merged to `develop`. Slices: #152 (#143),
#153 (#144), #154 (#145) → tracker #155.
**Issues**: #143 / #144 / #145 (DEBT-2 / DEBT-3 / DEBT-4) — debt pass before Ola 3.
**Branch**: `feat/frontend-regression-tests` (tracker) → `develop` (merge `c959e88`).

## What Shipped

Commits the 10 throwaway session probes that F1 (chart-legend), F2
(chart-indicator-settings) and F3 (chart-shell) had left unguarded — they shipped
green (`pass_with_warnings`) with these scenarios proven only by session probes —
plus a committed R14 module-size guard. **Test-only: no production file, no
spec-behavior change, no new runtime dependency, CSP unchanged, `window.marketChart`
seam stays 8 keys.**

| Area | Delivered |
|------|-----------|
| #143 F1 legend | `tests/js/legend-core.test.js` — LC2 import/indicator-token purity (comment-stripped source scan). `tests/web/test_market_e2e.py` — LC4 re-subscribe across a second `chart:built` (indicator toggle) with exactly one `.chart-legend`; LC5 `aria-live` idle policy (off during hover, exactly one `aria-live="polite"` transition after debounce); LC6 **exact** 3 `.lg-row` + labels `["SMA 20","EMA 20","RSI"]` (closes the vacuous `>=1`). |
| #144 F2 settings | `tests/js/legend-core.test.js` — W3: `legend-core.js` + `controllers/legend.js` contain no `styles`/`priceFormat` token. `tests/web/test_market_e2e.py` — W2 one rebuild per style change (wraps the CDN global `LightweightCharts.createChart` as a counter, NOT a seam key; `window.__builds === 1`). `tests/web/test_isolation.py` — W5 styled-layout A≠B isolation. `tests/web/test_module_size_guard.py` — **NEW** W4 R14 ceiling guard. |
| #145 F3 shell | `tests/web/test_market_e2e.py` — W1 keyboard chips (`ArrowRight`→activeElement, `Enter`/`Space`→`aria-pressed`+`#interval`); W2 `#chart` follows viewport resize via `autoSize` (delta ≤ 2, `ready` stays true); W3 desktop >820px panel/chip a11y + visible focus outline. |

### Committed tests (10 regression tests + the guard)

| File | Tests |
|------|-------|
| `tests/js/legend-core.test.js` | purity (LC2) + style-independence (W3) source asserts (with negative controls) |
| `tests/web/test_market_e2e.py` | 7 E2E: LC4, LC5, LC6 (#143); W2 rebuild-count (#144); shell W1, W2, W3 (#145) |
| `tests/web/test_isolation.py` | `test_styled_chart_layout_style_never_crosses_users` (W5) |
| `tests/web/test_module_size_guard.py` | **NEW** — R14 guard: `CEILING = 300`, `ALLOWLIST = {"chart-host.js"}` (326 lines, annotated DEBT-5 / #146), `rglob` + `splitlines()`, positive + negative-control + allowlist tests |

## Requirements Satisfied (verification-evidence only)

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-legend | LC2 (MODIFIED) | ✅ Purity now proven by a committed source test (no line-leading `import`/`export … from`; comment-stripped token scan). |
| chart-legend | LC4 (MODIFIED) | ✅ Re-subscribe across rebuilds now proven by committed E2E (2nd `chart:built` via toggle; exactly one `.chart-legend`). |
| chart-legend | LC5 (MODIFIED) | ✅ Idle-vs-per-move a11y policy now proven by committed E2E. |
| chart-legend | LC6 (MODIFIED) | ✅ All-active-series now asserted with **exact** counts/labels (`== 3`, ordered labels). |
| chart-indicator-settings | F2.5 (MODIFIED) | ✅ One-rebuild invariant proven by the `createChart`-counter E2E; legend style-independence proven by committed source asserts. |
| chart-indicator-settings | F2.9 (MODIFIED) | ✅ Style A≠B proven by committed `test_isolation.py` assertions. |
| chart-indicator-settings | F2.10 (ADDED) | ✅ Committed module-size ceiling guard (R14). |
| chart-shell | R20 / R22 / R23 (MODIFIED) | ✅ Resize-follows-container, keyboard chips, and desktop-hidden invariants now each proven by committed E2E. |
| market-chart | R14 (MODIFIED) | ✅ Size rule elevated from inspection-only to a committed executable guard (`test_module_size_guard.py`). |
| per-user-isolation | R14.2 (MODIFIED) | ✅ Cross-user denial extended to a styled `ChartLayout` row. |

All other requirements in each canonical spec preserved untouched. **No requirement
dropped.**

## RED-per-Test Evidence

Each committed regression test was RED-first: the probe/test failed against a
deliberately reverted behavior, then passed once restored. Representative checks
(tasks §1–3): LC2 (add an `import` → fails); LC4 (unwire re-subscribe → stale
handler, no hover update); LC5 (remove debounce → `aria-live` spikes per move);
LC6 (drop `rsi` default → rows ≠ 3); W2 (double-emit → `__builds == 2`); W3 (add a
`styles` read → fails); W4 (synthetic 301-line module → guard fails, names file +
count); W5 (drop owner scoping → B sees A's styled row); shell W1 (drop keydown →
activeElement doesn't move); W2 (remove `autoSize` → canvas detaches on resize);
W3 (drop `:focus-visible`/names → no outline / missing accessible name).

## Notable Finding (pre-existing, documented — DEBT-8 / #149)

3 **pre-existing** WS E2E tests fail LOCALLY with `KeyError: 'route'` — the
Playwright harness `route_web_socket` handler is not invoked (the fixture's route
setup raises before the handler runs). This is **not** introduced by this change:
reproduced identically on a clean `develop`. CI does **not** run E2E
(`addopts = "-m 'not e2e'"`), so it never surfaces in the pipeline. Documented as
part of **DEBT-8 (#149)**; carried as a warning, not a regression of this change.
The new E2E in this change do not depend on `route_web_socket` (they use the
dashboard's live fetch path, not mocked WS pushes), so they are unaffected.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-legend | Updated | LC2/LC4/LC5/LC6 modified — verification-method wording now names the committed tests; LC6 E2E assertion tightened to exact `== 3` + ordered labels. LC1/LC3 preserved. |
| chart-indicator-settings | Updated | F2.5 modified (one-rebuild + legend style-independence now test-proven); F2.9 modified (A≠B styled-layout); **F2.10 ADDED** (R14 module-size ceiling guard, `CEILING = 300` + `chart-host.js` allowlist → DEBT-5 / #146). F2.1–F2.4, F2.6–F2.8 preserved. |
| chart-shell | Updated | R20/R22/R23 modified — resize/keyboard/desktop invariants now proven by committed E2E. R21, R24–R26 preserved. |
| market-chart | Updated | R14 modified — size rule enforced by the committed guard (was inspection-only). R1–R13, R15–R21 preserved. |
| per-user-isolation | Updated | R14.2 modified — denial now also proven for a styled `ChartLayout`; added the styled-layout scenario. R14.1, R14.3–R14.5 preserved. |

## Warnings Carried (non-blocking)

- **DEBT-8 / #149** — 3 pre-existing WS E2E tests fail locally with
  `KeyError: 'route'` (Playwright `route_web_socket` harness); reproduced on clean
  `develop`; CI does not run E2E. Not a regression of this change.
- **E2E is dev-only** (deselected in CI via `addopts = "-m 'not e2e'"`) — the
  JS/template layer has no CI test signal; accepted status quo (same as
  F0/F1/F2/F3, DEBT-2/3/4 origin). Revisit if the JS layer gains its own runner.
- **`chart-host.js` at 326 lines** remains over the ~300 R14 target and is
  explicitly allowlisted by the new guard, annotated DEBT-5 / #146 — the tracked
  refactor. The guard blocks further growth elsewhere.

## Carry-forward

- **DEBT-8 (#149)** — the `route_web_socket` `KeyError: 'route'` harness issue is
  open; the local E2E WS coverage gap persists until fixed.
- **DEBT-5 (#146)** — `chart-host.js` refactor remains the tracked resolution of
  the allowlisted `CEILING` exception.
- Frozen seams (layered ESM inventory, 8-key `window.marketChart`,
  `window.SmcOverlayCore`, #68 single-write-path, per-user ownership) remain in
  force.

## SDD Cycle Complete

Planned (explore/proposal/specs/design/tasks) → implemented (chain #152/#153/#154 →
tracker #155) → verified (`pass_with_warnings`) → merged to `develop` → archived.

Traceability: `openspec/changes/archive/2026-10-14-frontend-regression-tests/`
(explore, proposal, specs, design, tasks, archive-report); engram
`sdd/frontend-regression-tests/{archive-report,proposal,spec,design,tasks}`.
