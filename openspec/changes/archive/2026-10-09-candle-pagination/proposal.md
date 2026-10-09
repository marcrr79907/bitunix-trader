# Proposal: candle-pagination

## Intent

The chart shows only the latest ~100 candles: `chart.js` fetches one page and
`/market/api/kline` always reads live BitUnix REST, ignoring the durable `Candle`
table built in #43. Users cannot scroll back, and BitUnix caps depth at ~3 years.
Issue #44 makes the endpoint paginate backward and the chart infinite-scroll,
serving history from our dataset first.

## Scope

### In Scope
- `/market/api/kline` gains optional `before` (UNIX seconds, exclusive): previous
  page, ascending, same `{candles, overlays}` shape.
- **DB-first**: read `Candle` `time < before`; **BitUnix gap-fill** only when the
  DB is short or the interval is not persisted, via `client.kline(end_time=)`.
- **Warm-up**: fetch `limit + 20`, compute `src/indicators.py` over the full
  window, slice to newest `limit` — page-edge overlays stay correct; genuine
  warm-up gaps stay omitted (no nulls).
- **Degradation**: BitUnix failure never 5xx when the DB has rows (200 with what
  we have); 502 only when both fail.
- `chart.js`: infinite scroll via `subscribeVisibleLogicalRangeChange`, fetch
  `before=oldestTime`, prepend, hold viewport by shifting the logical range.
- Tests: payload pagination/DB-first/warm-up, endpoint `before`/empty/400/auth/
  degradation, dev-only E2E scroll smoke. Patch gate 100%.

### Out of Scope
- Backfill/ingestion (`candle-store`), retention (#45), cron (#48).
- Backfilling the 6 non-persisted intervals (1m/30m/6h/8h/12h/3d) — gap-filled.
- WS protocol changes; new indicators; per-user candles.
- **Order execution — HARD invariant.** New runtime dependencies — none.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `market-chart`: R3 (kline endpoint) gains `before` pagination, DB-first read
  with BitUnix gap-fill, warm-up-correct per-page overlays. R4 restated: the
  single-source overlay rule applies per page through the warm-up slice.

## Approach

DB-first, gap-fill second: the common request is served by the indexed `Candle`
table (`WHERE symbol=? AND interval=? AND time<? ORDER BY time DESC LIMIT limit+20`);
BitUnix is touched only for history/intervals the DB lacks, reusing the existing
`client.kline(end_time=ms)` seam. One `WARMUP=20` window makes overlays correct on
every page. chart.js adds ~40 lines: an edge-triggered loader with a single
in-flight guard, a merge deduped by `time`, and a range shift to hold the viewport.
No schema, no migration, no new dependency; `src/` stays framework-free.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/market/quotes.py` | Modified | paginated DB-first payload + warm-up slice |
| `web/market/views.py` | Modified | parse/validate `before`; degradation status |
| `web/market/templates/market/chart.js` | Modified | infinite scroll + prepend + viewport restore |
| `tests/web/test_market_api.py` | Modified | pagination/DB-first/warm-up/degradation |
| `tests/web/test_market_e2e.py` | Modified | scroll-loads-more DOM smoke |
| `src/client.py`, `web/trading/**`, `urls.py`, `requirements.txt` | Unchanged | reused as-is |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Overlay wrong at page boundary | Med | `WARMUP=20` slice; test first-candle non-null |
| Viewport jump on prepend | Med | shift logical range by prepended count; E2E |
| Bucket-close refetch resets series | Med | reset pagination anchors deliberately |
| BitUnix rate/latency on gap-fill | Low | DB-first short-circuits the common case |
| Patch gate 100% vs new branches | Med | seeded `Candle` + stub client per branch |

## Rollback Plan

Revert the branch: restore `quotes.py`, `views.py`, `chart.js` and the two test
files; drop `before` handling. No schema change, no migration, no data mutation —
`Candle` and the worker are untouched. The chart returns to single-page behavior.

## Open Questions

- Empty-page signal vs explicit `has_more`/`source` field (recommend empty page).
- Refetch-on-close: replace-and-reset vs merge-preserve pagination.
- `WARMUP=20` fixed vs derived from the indicator set.

## Success Criteria

- [ ] `python -m pytest` green (Strict TDD); patch coverage 100%; ruff clean.
- [ ] Scroll back loads older pages; candles ascending, no duplicate `time`, no gaps at joins.
- [ ] Overlays correct per page (warm-up); no nulls in series arrays.
- [ ] DB-first: a full DB page never hits BitUnix; short DB gap-fills via `end_time`.
- [ ] BitUnix failure with DB rows → 200 (degraded), never 5xx; WS live path unclobbered.
- [ ] `src/` framework-free; `requirements.txt` unchanged; no order surface.

## Review Workload Forecast

- Estimated diff: **~350–450 changed lines** (`quotes.py` ~80, `views.py` ~20, `chart.js` ~50, tests ~200).
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: Medium
