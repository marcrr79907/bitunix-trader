# Design: candle-pagination (issue #44)

## Technical Approach

`/market/api/kline` becomes a DB-first cursor page: read `Candle` for
`symbol/interval/time < before` newest-first, fall back to BitUnix only when the
DB cannot fill `limit + WARMUP`, merge DB-wins, compute `src/indicators.py` over
the warm window, slice to the newest `limit`. `chart.js` detects the left logical
edge, fetches `before=<oldestTime>`, prepends older data and shifts the visible
range to hold the viewport. No schema, migration, or new dependency; `src/` untouched.

## Endpoint Design

**Validation (views.py)** — `before` optional positive UNIX-seconds int, checked
after interval/symbol/limit; same 400 shape:

```python
before = None
if raw_before:
    try:
        before = int(raw_before)
    except ValueError:
        return JsonResponse({"error": "invalid before"}, status=400)
    if before <= 0:
        return JsonResponse({"error": "invalid before"}, status=400)
```

**DB-first read (quotes.py)** — `WARMUP = 20`, `want = limit + WARMUP`:

```python
def _db_rows(symbol, interval, before, want):
    if interval not in CANDLE_INTERVALS:      # 1m/30m/6h/8h/12h/3d absent
        return []
    qs = Candle.objects.filter(symbol=symbol, interval=interval)
    if before is not None:
        qs = qs.filter(time__lt=before)
    return [{k: getattr(r, k) for k in _KEYS} for r in reversed(qs.order_by("-time")[:want])]
```

BitUnix is called **only** when `len(db) < want`. Gap-fill:
`end_ms = (before or _now()) * 1000`; `client.kline(symbol, interval, want, end_time=end_ms)`.
Merge (DB wins on duplicate `time`), keep newest `want`:

```python
merged = {c["time"]: c for c in up}
merged.update({c["time"]: c for c in db})       # durable record wins
rows = sorted(merged.values(), key=lambda c: c["time"])[-want:]
```

**Warm-up slice** — compute indicators over the full window, slice candles and
overlays to the newest `limit`:

```python
page = times[-limit:]
"candles": candles[-limit:]
"sma20": _zip(page, indicators.sma(closes, 20)[-limit:])
```

A page with ≥20 prior candles has non-null sma20/ema20 at its first candle; at
the data floor leading gaps stay omitted (no nulls).

**Degradation** — the gap-fill call swallows upstream failure only when DB rows
exist; re-raises otherwise so the view keeps its mapping:

```python
if len(db) < want:
    try:
        up = client.kline(...)
    except (BitunixError, requests.RequestException):
        if not db:
            raise                       # view -> 400 (BitunixError) / 502 (Request)
        up = []                          # degraded: serve DB rows, 200
        logger.warning("kline degraded symbol=%s interval=%s", symbol, interval)
```

Matrix: DB-full → 200 (client not called); DB-short+ok → 200 merged;
DB-short+fail → 200 degraded (logged); DB-empty+ok → 200 upstream;
DB-empty+`RequestException` → 502; DB-empty+`BitunixError` → 400 (unknown symbol).

**Empty-page signal:** `{"candles":[]}` = "no more" — no `has_more` field.

## chart.js Infinite Scroll

Module-level `allCandles/allSma/allEma` arrays enable prepend/merge. ~45 lines:

```js
var EDGE = 5, loadingOlder = false, hasMore = true, oldestTime = 0;
chart.timeScale().subscribeVisibleLogicalRangeChange(function (range) {
  if (range && range.from < EDGE) loadOlder();
});
function loadOlder() {
  if (loadingOlder || !hasMore || !oldestTime) return;
  loadingOlder = true;
  fetch("/market/api/kline?symbol=" + state.symbol + "&interval=" + state.interval +
        "&limit=200&before=" + oldestTime)
    .then(function (r) { if (!r.ok) throw 0; return r.json(); })
    .then(function (p) {
      if (!p.candles.length) { hasMore = false; return; }
      var range = chart.timeScale().getVisibleLogicalRange();
      var added = mergeOlder(p.candles);          // existing (newer) wins
      if (!added) { hasMore = false; return; }
      candleSeries.setData(allCandles);
      smaSeries.setData(mergeSeries(p.overlays.sma20, allSma));
      emaSeries.setData(mergeSeries(p.overlays.ema20, allEma));
      if (range) chart.timeScale().setVisibleLogicalRange(
        { from: range.from + added, to: range.to + added });   // hold viewport
      oldestTime = allCandles[0].time;
    })
    .catch(function () {})
    .finally(function () { loadingOlder = false; });
}
```

`mergeOlder` seeds a `{time: candle}` map from `allCandles` (existing wins),
adds unseen older rows, sorts ascending, returns added count. `applyPayload`
(latest page + bucket-close `scheduleRefetch`) **resets anchors**:
`oldestTime = allCandles[0].time; hasMore = true`. WS `onPush` still
`candleSeries.update()`s the rightmost bar, never the left edge.

## Testing Strategy

Strict TDD (`python -m pytest`), RED→GREEN→REFACTOR. Patch gate 100% — **both DB
and BitUnix branches** reachable via seeded `Candle` + a recording stub.

| Layer | What | How |
|---|---|---|
| Payload (`test_market_api.py`, `django_db`) | DB-full skips client; gap-fill passes `end_time`; merge DB-wins; warm-up first candle non-null; floor gaps omitted; empty | seed `Candle`; `StubClient` records/raises |
| Endpoint | `before` forwarded; invalid/`0`/`-1` → 400; empty → 200; degradation (raise + rows → 200); both-fail → 502; anon → 302 | `monkeypatch market.views.BitunixClient` |
| E2E (dev-only) | scroll left → `before=` observed, series grows | `live_server` + DOM `evaluate` |

Payload tests gain the `db` fixture. JS is invisible to the Python patch gate;
E2E verifies it.

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|---|---|---|---|
| a | Read source | DB-first, BitUnix gap-fill | BitUnix-only; DB-only | Uses #43's dataset; DB-only can't serve 6 unpersisted intervals; BitUnix-only ignores the table, stays 3y-capped |
| b | Overlay edges | Fetch `limit+WARMUP`, compute, slice | page-only; per-indicator widths | One constant fixes every page edge; `WARMUP=20` fixed covers sma/ema seed and rsi |
| c | "No more" | empty `candles` | `has_more` field | No schema growth; client already stops |
| d | Viewport | shift logical range by added count | anchor to a time | Official v5 pattern; index shifts exactly by prepends |
| e | Refetch-on-close | full page, reset anchors | merge-preserve | Simplest correct; deliberate reset avoids stale anchors |

## Boundary Note

`web/market` imports `trading.models`/`trading.candles` (web→web, permitted).
`src/` stays framework-free (`test_boundary.py` green). No schema/migration;
`Candle` read-only; `requirements.txt` and order scanner untouched.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/market/quotes.py` | Modify | `before`; `_db_rows`; gap-fill merge; `WARMUP` slice; degradation |
| `web/market/views.py` | Modify | parse/validate `before`; pass through |
| `web/market/templates/market/chart.js` | Modify | infinite scroll, prepend, viewport shift, anchor reset |
| `tests/web/test_market_api.py` | Modify | pagination/DB-first/warm-up/degradation matrix |
| `tests/web/test_market_e2e.py` | Modify | scroll-loads-more DOM smoke |

## Task Breakdown Hint

~350–400 lines → **chained PRs** (orchestrator confirms, ask-on-risk):

- **PR1 backend** (`quotes.py`, `views.py`, `test_market_api.py`): DB-first,
  pagination, warm-up, degradation; headless/curl-verifiable. ~280 lines.
- **PR2 frontend** (`chart.js`, `test_market_e2e.py`): infinite scroll + E2E;
  targets PR1 branch. ~120 lines.

## Open Questions

None blocking. (Exploration's refetch/`WARMUP`/empty-signal questions settled above.)
