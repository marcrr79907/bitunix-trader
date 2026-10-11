# Tasks: chart-live-consistency (issue #68)

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a (single PR)
400-line budget risk: Medium

## Guard/Edge Matrix

- [x] core loads in Node (`require`) and browser (`window.ChartCore`)
- [x] core references no DOM/fetch/chart API
- [x] `bucketTime` 1w → Monday (`t % 604800 == 345600`)
- [x] `bucketTime` 1M → calendar month start
- [x] `bucketTime` intraday/d → `floor(sec/n)*n`
- [x] `upsertCandle` same bucket → replace in place (len unchanged)
- [x] `upsertCandle` newer → append; older → ignored (no reorder)
- [x] `mergeCandles` union, ascending, existing wins on dup
- [x] adapter: `setData` only for history/pagination; stream uses `update`
- [x] E2E: no `setData` during stream; series monotonic
- [x] overlays advance via `update` of last point (no mid-stream `setData`)
- [x] CSP unchanged; no npm/build; `requirements.txt` unchanged
- [x] `src/` boundary green; scanners green
- [x] `node --test` green; `pytest` green; ruff clean; patch 100%

## WU1 — Pure core + node tests

Branch `fix/chart-live-consistency` (base `develop`).

- [x] 1.1 **RED** `tests/js/chart-core.test.js`: bucketTime (1m/5m/1h/1d/1w/1M with real BitUnix ts), upsertCandle (3 cases), mergeCandles (overlap/existing-wins/ascending), lastPoint.
- [x] 1.2 **GREEN** `web/market/templates/market/chart-core.js` (UMD; pure; no DOM).
- [x] 1.3 `node --test tests/js` green.
- [x] 1.4 Rollback: delete core + test.

## WU2 — Adapter rewrite (single write path)

Depends: WU1.

- [x] 2.1 **GREEN** `chart.js`: history `setData` once; pagination `setData` with `mergeCandles` + viewport shift; WS `update` only (via `upsertCandle`); monotonic `lastBucket`; overlay `update` at close (small fetch limit=2, no `setData`).
- [x] 2.2 **GREEN** `chart.html`: load `chart-core.js` before `chart.js`.
- [x] 2.3 **GREEN** `web/market/views.py::chart_core_js` + `urls.py` route.
- [x] 2.4 Rollback: restore `chart.js`, remove view/route.

## WU3 — E2E + CI

Depends: WU2.

- [x] 3.1 **RED/GREEN** `tests/web/test_market_e2e.py`: spy `setData`; drive WS pushes via `route_web_socket`; assert no `setData` during stream + monotonic length.
- [x] 3.2 **GREEN** `.github/workflows/ci.yml`: Node test job (`node --test tests/js`).
- [x] 3.3 Rollback: revert E2E/CI changes.

## Phase 4 — Verification

- [x] 4.1 `node --test tests/js` green.
- [x] 4.2 `python -m pytest` green; ruff clean; `makemigrations --check`.
- [x] 4.3 Scanners green; CSP unchanged; no new dep.
- [x] 4.4 Browser check (Playwright): chart renders, no flicker/phantom candles.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | WU1 ~110, WU2 ~200, WU3 ~80 → ~350–450 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Tracker branch | `fix/chart-live-consistency` → `develop` |

```text
Decision needed before apply: No
Chained PRs recommended: No
400-line budget risk: Medium
```
