# Proposal: chart-legend (Fase F1, issue #114)

## Intent

Add a TradingView-style floating legend + crosshair OHLC/indicator readout to the market chart. F0's layered ESM already exposes every seam (host owns chart + seriesData; `chart:built` rebuilds; controllers are DI factories). The legend is a pure read-through: it formats server-shaped values, recomputing nothing.

## Scope

### In Scope
- `legend-core.js` — pure formatters/assemblers (no DOM, no chart lib), `node --test`.
- `controllers/legend.js` — DI overlay controller `create({store,bus,host,config})`.
- `host.subscribeCrosshairMove(fn)` — host-owned, mirrors `subscribeClick`.
- Allowlist entries + `chart.html` preloads; `theme.css` overlay.
- One node test + one DOM-only E2E test.

### Out of Scope
Indicator config/settings UI (F2); pin toggle; legend filtering; custom price/time formatters (stock v5 labels suffice); any indicator/OHLC recompute; no `window.marketChart` 9th key (R18 frozen).

## Capabilities

### New Capabilities
- `chart-legend`: read-only hover/leave readout, pure-core formatting, overlay DOM, crosshair subscription lifecycle.

### Modified Capabilities
- `market-chart`: allowlist gains `legend-core` + `legend`; host gains `subscribeCrosshairMove`.

## Approach

Pure core + one controller + one host seam. `legend-core` never sees a chart object; the controller converts the crosshair `param.seriesData` Map into plain `{token,key,place,pane,value}` entries via `host.getActiveSeries()`. Leave-state values come from `host.getSeriesData()`/`getCandles()` last element. Re-subscribe on every `chart:built`. `rAF`-coalesced `textContent` updates (never `innerHTML`). No new bus event; `main.js` gains ~1 line.

## Affected Areas

- **New**: `legend-core.js`, `controllers/legend.js`, `tests/js/legend-core.test.js`.
- **Modified**: `chart-host.js`, `main.js`, `views.py` + `chart.html`, `theme.css`, `test_market_e2e.py` (add one test, no edits to existing).

## Risks

- **Crosshair perf (High)**: per-mousemove → rAF coalescing, fixed nodes, `textContent` only.
- **Stale handler across rebuilds (Med-High)**: re-subscribe on `chart:built`.
- **Single-source drift (Med)**: core imports nothing; test asserts no indicator math.
- **E2E seam coupling (Med)**: assert via `.chart-legend` DOM, no 9th key.
- **JS patch coverage (Med)**: `diff-cover` is Python-only → `node --test` + E2E.
- **Missing allowlist → blank chart (Low)**: import-graph route test derives routes.

## Rollback Plan

Per slice via `git revert`: remove the core + controller, the host method, the `main.js` line, the `theme.css` overlay, allowlist/preload entries, and tests. No data, migration, config, order surface, or CSP change — clean, isolated revert.

## Read-Only Boundary

No order execution, no owned model, no `Candle` write, no `src/` change, no new runtime dep, CSP unchanged, no new `window` global; `window.marketChart` stays 8 keys.

## Dependencies

F0 layered ESM (MERGED); Lightweight Charts v5.2.0 (pinned CDN global); Node 22 + Playwright.

## Delivery (Feature Branch Chain — 2 slices)

Base = tracker `feat/chart-legend`; each child PR targets the previous slice.
1. Core + host seam + serving — ~220 lines (node green). PR #1 → tracker.
2. Controller + overlay + E2E — ~205 lines. PR #2 → PR #1 branch.

- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: Medium/High

## Success Criteria

- [ ] `node --test` green (legend-core added); existing assertions unedited.
- [ ] E2E: `.chart-legend` shows hover readout + last values on leave; `marketChart` still 8 keys.
- [ ] New modules served same-origin JS MIME; import-graph route test green.
- [ ] No `src/` change, no new dep, CSP unchanged, no layout shift.
