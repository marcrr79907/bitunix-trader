# Archive Report: chart-live-consistency

**Archived**: 2026-10-11
**Verdict**: PASS (0 blockers, 0 criticals) — 7/7 requirements, Strict TDD
**Delivery**: single PR #69 → `develop`
**Merged commit**: PR #69 merge on `develop`

## What Shipped

A consistent live chart built on a clean-architecture split: a framework-free
pure core + a thin adapter with one write path per concern.

| Area | Delivered |
|------|-----------|
| Core | `chart-core.js` (pure, UMD, node-tested): `bucketTime` (1w=Monday, 1M=calendar month), `upsertCandle`, `mergeCandles`, `lastPoint` |
| Adapter | `chart.js` rewrite: `setData` only for history + pagination (merge, viewport preserved); live stream `update()` only; overlays via `update()` of the last point at close; monotonic `lastBucket` |
| Delivery | `chart_core_js` view (same-origin) + route; `chart.html` loads core before adapter |
| Tests | `tests/js/chart-core.test.js` (9) + E2E `test_ws_stream_never_calls_setdata` |
| CI | new `js-core` job (`node --test`) |

## Root Causes Fixed

1. Two writers raced the series (WS `update()` vs periodic `setData()`).
2. Refetch reset `lastBucket` every push → infinite refetch loop.
3. Client invented candle timestamps (1w/1M misaligned with BitUnix).
4. Overlays only refreshed via full `setData` → deformation.
5. `applyPayload` overwrote `allCandles` → pagination history lost.

## Requirement Outcomes

R1 pure core ✅ · R2 exchange-aligned bucketing ✅ · R3 in-place monotonic upsert ✅
· R4 lossless merge ✅ · R5 single write path ✅ · R6 aligned overlays ✅ · R7 invariants ✅

## Verify Findings

None blocking. Verified in a real browser (Playwright): `ChartCore` loaded, chart
mounted, 301 candles, 0 page errors. Node 9/9 + pytest 391 + patch 100%.

## Carry-forward

- Overlays advance at candle close (approved policy; server-side single source).
- `chart.js` is a template (not Python-coverage-instrumented); its behavior is
  covered by the dev-only E2E + the pure-core node tests.

## SDD Cycle Complete

Planned → implemented → verified (inline: subagents sdd-spec/sdd-tasks failed
with "Bad request"; node + Playwright evidence) → merged → archived.

Traceability: engram `sdd/chart-live-consistency/{proposal,spec,design,tasks}`.
