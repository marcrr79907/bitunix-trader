# Proposal: chart-live-consistency

## Intent

Fix the live chart's inconsistent behaviour (issue #68): the forming candle
flickers, overlays deform, and pagination is destroyed. Root cause is an
architectural one: two writers race on the same series (`WS update()` vs a
periodic `setData()`), timestamps are invented client-side, overlays are only
refreshed via full `setData`, and pagination is overwritten by refetch.

## Scope

### In Scope
- A **pure core module** `chart-core.js` (no DOM / chart lib / network):
  `bucketTime(tsMs, interval)` with correct per-interval alignment (1w = Monday,
  1M = calendar month), `upsertCandle`, `mergeCandles`, `lastPoint`.
- Rewrite `chart.js` as a thin **adapter** (DOM + Lightweight Charts + WS + REST)
  that delegates all series math to `chart-core.js`.
- **Single write path**: `setData` only for history load + pagination (with
  merge); the live stream uses `update()` exclusively; overlays advance
  incrementally at candle close (no full `setData`).
- Monotonic `lastBucket` (never resets backwards) — kills the refetch loop.
- Same-origin core delivery via a `chart_core_js` view (mirrors `chart_js`).
- Node E2E-free unit tests (`node --test`) for the pure core; dev-only Playwright
  E2E asserting no `setData` during the stream and a monotonic series.
- A CI job running `node --test`.

### Out of Scope
- Indicator math changes (stays server-side single-source).
- New features (alerts, drawing tools). Any npm/build. Any CSP relaxation.
- Order execution (HARD invariant).

## Capabilities

### New Capabilities
- `chart-live-stream`: pure bucket/upsert/merge core + adapter single-write-path
  live chart consistency.

### Modified Capabilities
- `market-chart`: R5 (live candles) and R8 (infinite scroll) get a deltas —
  the live path MUST NOT issue periodic `setData`; timestamps MUST come from the
  exchange (normalized), not be invented client-side.

## Approach

Mirror the repo's clean-architecture philosophy: a framework-free core
(`chart-core.js`, like `src/`) and an adapter at the edge (`chart.js`, like
`web/`). The core is a UMD module (works under Node `require` and browser
`window.ChartCore`) so it is unit-testable without a DOM. The adapter owns
DOM/chart/WS/REST; it calls the core for pure decisions and never duplicates
timeline math.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/market/templates/market/chart-core.js` | New | pure core |
| `web/market/templates/market/chart.js` | Rewrite | adapter, single write path |
| `web/market/views.py` + `urls.py` | Modify | `chart_core_js` view + route |
| `web/market/templates/market/chart.html` | Modify | load core before adapter |
| `tests/js/chart-core.test.js` | New | `node --test` |
| `tests/web/test_market_e2e.py` | Modify | assert no setData during stream |
| `.github/workflows/ci.yml` | Modify | Node test job |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Regression in history/pagination | Med | keep `setData` for those paths only; E2E |
| Node not in CI | Low | ubuntu runners ship node; pin action |
| Coverage gate vs JS | Low | JS core tested by node; Python view by pytest |
| 1M calendar bucketing edge | Low | unit tests with real BitUnix timestamps |

## Rollback Plan

Revert the branch: restore `chart.js`, delete `chart-core.js` + the view/route +
the node test; restore `chart.html`. No DB, no migration, no CSP change.

## Open Questions

None blocking.

## Success Criteria

- [ ] `node --test tests/js` green (bucket 1w/1M, upsert monotonic, merge).
- [ ] E2E: no `setData` during the stream; series count monotonic across pushes.
- [ ] `pytest` green; ruff clean; scanners green; no new dep.

## Review Workload Forecast

- Estimated diff: **~350–450 lines** (core ~90, adapter rewrite ~180, view/tests ~15, node tests ~100, E2E ~40).
- Decision needed before apply: Yes
- Chained PRs recommended: No
- 400-line budget risk: Medium
