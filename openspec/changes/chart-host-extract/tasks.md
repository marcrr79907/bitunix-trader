# Tasks: chart-host-extract (issue #146, DEBT-5)

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

Single PR, behavior-equivalent read-only refactor. Only test edit: the DEBT-3
size guard's own exemption list + test (satisfying it IS the deliverable).
138 node + E2E pass with ZERO assertion edits; Python keeps patch 100%.

## Guard/Edge Matrix

- [ ] **C1 same-bucket HA**: `if (!sameBucket) prevHa = lastHa;` moves VERBATIM; node C1 + E2E HA pass, no edit.
- [ ] **#68 single-write-path**: `setData` only in `setCandles`/build; `update` only in `updateCandle`; E2E spy unchanged.
- [ ] **8-key seam**: no new key; `window.marketChart.candleSeries` = module handle; E2E count `=== 8`.
- [ ] **Raw-candle identity**: module holds `let candles`, returns it directly; `Core.upsertCandle` mutates that array.
- [ ] **Build order**: `createCandles(chart, chartType)` sits where ctor lines are (after `createChart`, before `applyScale`).
- [ ] **Route resolves**: `./chart-host-candles.js` → 200 + `text/javascript`; missing allowlist entry → 404 → blank chart.
- [ ] **Size guard**: `ALLOWLIST` empty; real `chart-host.js` ≤ `CEILING`; synthetic >300 non-allowlisted module still fails.
- [ ] **No new dep / CSP**: same-origin ESM only; `script-src 'self' https://unpkg.com` unchanged.

## Phase 1 — Extract the candle module

- [ ] 1.1 **GREEN** Create `chart-host-candles.js` (~70 lines, `web/market/templates/market/`): header doc; `import * as Core from "./chart-core.js"` + `import * as Types from "./chart-types-core.js"`; `CANDLE_CTORS`; `export function createCandles(chart, chartType)` → `{getCandleSeries, getCandles, setCandles, updateCandle, remove}` (owns series, `candles`, `lastHa`/`prevHa`/`lastBarTime`; C1 verbatim per design.md). Acceptance: `createCandles` exported; body byte-matches design.

## Phase 2 — Delegate in the host

- [ ] 2.1 **RED→GREEN** `chart-host.js`: drop `import * as Core` + `CANDLE_CTORS` + `chartType`/HA/`candles` vars; `build()` ctor lines → `candles = createCandles(chart, chartType); candleSeries = candles.getCandleSeries();`; `remove()` adds `candles.remove();`; `getCandleSeries`/`getCandles`/`setCandles`/`updateCandle` delegate. Acceptance: ≤300 lines; `node --test "tests/js/**/*.test.js"` green unchanged.
- [ ] 2.2 **RED→GREEN** Static check: no `CANDLE_CTORS`/HA vars left; `Types` still imported; `Core` gone. Acceptance: grep clean.

## Phase 3 — Wire the route

- [ ] 3.1 **GREEN** `views.py`: `MODULE_ALLOWLIST` += `"chart-host-candles"`. Acceptance: route-coverage test serves 200 + `text/javascript` (fails if absent).
- [ ] 3.2 **GREEN** `chart.html`: add `modulepreload` for `name='chart-host-candles'` next to `chart-host`. Acceptance: tag present.

## Phase 4 — Retire the size exemption

- [ ] 4.1 **RED→GREEN** `test_module_size_guard.py`: `ALLOWLIST` → `frozenset()`; rewrite `test_allowlist_exempts_chart_host_but_not_others` → `test_no_module_is_exempt_and_chart_host_is_within_ceiling`: (1) `over_ceiling({"chart-host.js": "\n"*326}) == {"chart-host.js": 326}`; (2) real `chart-host.js` ≤ `CEILING`; (3) synthetic non-allowlisted >300 fails; docstring. Acceptance: red pre-Phase 2, green after.

## Phase 5 — Verification

- [ ] 5.1 `node --test "tests/js/**/*.test.js"` + `pytest tests/web/` (E2E, UX, size guard, patch 100%) + ruff; confirm no new dep, CSP/`src/` untouched, 8-key seam intact. Acceptance: full net green, no behavior-assertion edit.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~130–160 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | single-pr |
| Chain strategy | stacked-to-main |

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Extract candle channel + delegate + route + guard | PR 1 | Single PR; tests/docs included; base main |
