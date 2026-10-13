# Tasks: chart-legend (issue #114, Fase F1)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium/High

All slice PRs base on the tracker `feat/chart-legend`; merge each slice into the
tracker before branching the next. Base boundaries: PR1 base = tracker;
PR2 base = PR1 branch. Strict TDD (`node --test` + E2E). Read-only, single-source:
the legend formats server-shaped values and recomputes nothing. JS is outside the
Python patch gate (`diff-cover` Python-only) → the net is `node --test` + E2E.

## Guard/Edge Matrix

- [ ] **single-source (no recompute)**: `legend-core.js` imports nothing and defines no window/EMA/RSI/ATR logic; values only from `param.seriesData` / `host.getSeriesData()` / `host.getCandles()`; `changePct` is the only arithmetic (vs `prevClose`).
- [ ] **rAF / no jank**: one pending frame max; `textContent` on a fixed node set only, never `innerHTML`.
- [ ] **re-subscribe on `chart:built` (no stale handler)**: controller re-binds `host.subscribeCrosshairMove(onMove)` on the NEW chart each build; prior handler dies with `chart.remove()`.
- [ ] **no 9th seam key (R18)**: legend writes DOM only; E2E asserts `Object.keys(window.marketChart).length === 8`.
- [ ] **a11y idle-only aria-live**: `role="status" aria-live="polite"` updated only on state change / idle refresh, debounced ≥300ms; never per mousemove; signed `.num` cue not color-only.
- [ ] **allowlist route**: `legend-core` in `MODULE_ALLOWLIST`, `legend` in `CONTROLLER_ALLOWLIST`; missing → 404 → blank chart; `test_import_graph_routes_resolve` derives routes automatically.
- [ ] **no new dep / CSP**: ESM + `theme.css` only, no inline, no npm; `script-src 'self' https://unpkg.com` unchanged.
- [ ] **responsive**: `max-width:min(90%,320px)`, wrap/clip; verified at 375px; no layout shift (`pointer-events:none`).
- [ ] **off-bar null-safe**: `param.point === undefined` → last-value fallback; missing series → `PLACEHOLDER` (`"–"`), no throw.

## Slice 1 — Pure core + host seam + serving (PR1)

Base tracker; branch `feat/chart-legend-core`; deps none. Rollback: revert `legend-core.js`,
host method, allowlist/preload entries, `legend-core.test.js` → chart behavior unchanged. ~220 lines.

- [ ] 1.1 **RED** `tests/js/legend-core.test.js`: assert `DECIMALS` frozen exact map, `formatValue` known/unknown/placeholder, `formatOhlc` strings + `dir`, `rows` deep-equal determinism, `lastValues` dataKey recompute + empty inputs. Acceptance: fails pre-1.2.
- [ ] 1.2 **GREEN** create `web/market/templates/market/legend-core.js`: export `DECIMALS` (frozen), `PLACEHOLDER="–"`, `formatValue(token,value)`, `formatOhlc(candle)→{open,high,low,close,dir}`, `rows(entries,activeSeries,candle)→{ohlc,series[]}`, `lastValues(activeSeries,seriesData,candles)→{candle,entries[]}`. Pure, chart-lib/DOM-free, never throws. Acceptance: 1.1 green.
- [ ] 1.3 **GREEN** `chart-host.js`: add `subscribeCrosshairMove(fn){ if (chart) chart.subscribeCrosshairMove(fn); }` mirroring `subscribeClick`; export in return object. Files: `chart-host.js`. Acceptance: host unit green.
- [ ] 1.4 **GREEN** `web/market/views.py`: `MODULE_ALLOWLIST += "legend-core"`. `chart.html`: add `modulepreload` for `legend-core`. Acceptance: route 200 + `text/javascript`.
- [ ] 1.5 **REFACTOR** `node --test "tests/js/**/*.test.js"` green (legend-core added, existing assertions unedited); ruff clean; patch 100% on Python lines. Acceptance: Slice 1 suite green.

## Slice 2 — Controller + overlay + E2E (PR2)

Base PR1 branch; deps Slice 1. Rollback: revert `controllers/legend.js`, `main.js` line,
`theme.css` block, E2E test → Slice 1 state (no overlay). ~205 lines.

- [ ] 2.1 **RED** `tests/js/chart-controllers.test.js`: add pure-helper cases for the controller's snapshot shaper (entries from `seriesData` Map + leave fallback). Acceptance: fails pre-2.2.
- [ ] 2.2 **GREEN** create `web/market/templates/market/controllers/legend.js`: `create({store,bus,host,config})`; inject `<div class="chart-legend" role="status" aria-live="polite" aria-label="Chart legend">` + `.lg-ohlc` + `.lg-row` into `#chart`; subscribe bus `chart:built` → `host.subscribeCrosshairMove(onMove)` + idle render; re-render idle on `candle:closed`/`history:loaded`; rAF-coalesced `textContent`; never import `main`. Acceptance: 2.1 green.
- [ ] 2.3 **GREEN** `main.js`: `import { createLegend }` + `createLegend({store,bus,host,config})` after `createToolbar`. Files: `main.js`. Acceptance: legend binds without editing `buildChart`.
- [ ] 2.4 **GREEN** `web/market/views.py`: `CONTROLLER_ALLOWLIST += "legend"`; `chart.html` preload; `theme.css`: `#chart{position:relative}` + `.chart-legend`/`.lg-token`/`.up`/`.dn` block. Acceptance: overlay styled same-origin.
- [ ] 2.5 **RED** `tests/web/test_market_e2e.py`: ADD one DOM-only test — boot → `page.mouse.move` over `#chart` → `.chart-legend` shows OHLC + one row per active series; leave → last values; `marketChart` still 8 keys. No edits to existing. Acceptance: fails pre-2.2.
- [ ] 2.6 **REFACTOR** `node --test` + `pytest -m e2e` green; verify overlay at 375px (Playwright/`/impeccable`); no module > ~300 lines; patch 100% on Python lines. Acceptance: Slice 2 suite green.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | Slice1 ~220, Slice2 ~205 → ~425 |
| 400-line budget risk | Medium/High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (core + host seam + serving) → PR2 (controller + overlay + E2E) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Each slice is autonomous with its own verification and trivial rollback; PR1 bases
on the tracker `feat/chart-legend`, PR2 bases on the PR1 branch (retarget/rebase if
a child diff shows Slice 1).
