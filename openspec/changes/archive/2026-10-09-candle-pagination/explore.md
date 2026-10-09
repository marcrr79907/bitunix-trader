# Exploration: candle-pagination (issue #44)

**Change**: `candle-pagination`
**Date**: 2026-10-09
**Mode**: investigation only. No code written.
**Issue**: gh#44 — candle-pagination: historial completo en la API y el chart.
**Depends on**: `candle-store` (issue #43) — implemented and verified (PASS WITH WARNINGS), `Candle` table live.

## Executive Summary

The chart is capped at one 100-candle page. `chart.js` calls `/market/api/kline?symbol=&interval=`
once and never asks for older data; the endpoint always reads live BitUnix REST (200-row max,
~3y depth max) even though we now own a durable `Candle` table. This change adds `before`-cursor
pagination to the endpoint (DB-first, BitUnix gap-fill) and infinite-scroll prepend to `chart.js`,
keeping the response shape, overlays server-side, and the WS live path untouched.

## Current State (read, not guessed)

| Area | Fact | Source |
|---|---|---|
| Endpoint | `api_kline` parses `symbol/interval/limit`, clamps limit `[1,200]`, calls `get_kline_payload(BitunixClient(), symbol, interval, limit)`. GET-only, `@login_required`. No `before`/`end_time`. | `web/market/views.py:33-58` |
| Payload seam | `get_kline_payload` calls `client.kline(symbol, interval, limit)` (live REST), dedupes by time (last wins), sorts ascending, projects candles to exactly `CHART_KEYS = (time,open,high,low,close)`, computes sma20/ema20/rsi14 via `src/indicators.py`, `_zip` omits `None` gaps. | `web/market/quotes.py:30-59` |
| Client | `kline(symbol, interval="1m", limit=100, start_time=None, end_time=None)` — epoch-ms `startTime`/`endTime`, unsigned public GET. `endTime` paginates BACKWARD (verified by candle-store probe I); `startTime` is IGNORED by BitUnix. | `src/client.py:126-150`, candle-store verify-report probe I |
| Candle table | Global `trading.Candle`: `symbol, interval, time(BigInt seconds), open/high/low/close, quote_vol(null)`; `UniqueConstraint(symbol,interval,time)` + composite index `(symbol,interval,time)`. Persisted per interval **5m,15m,1h,2h,4h,1d,1w,1M** (NO 1m,30m,6h,8h,12h,3d). | `web/trading/models.py:57-87`, `web/trading/candles.py:19-30` |
| Chart intervals | UI supports 14 intervals incl. 1m/30m/6h/8h/12h/3d; **6 of these are never persisted** → DB cannot serve them. | `web/market/templates/market/chart.html:17-32`, `candles.py:19-28` |
| chart.js | `fetchHistory()` GETs `/market/api/kline?symbol=&interval=` (no limit → default 100) → `applyPayload` does `setData` on candle+sma+ema, reads last rsi, sets `lastBucket`. WS `onPush` calls `candleSeries.update()` for the forming candle; on bucket advance `scheduleRefetch()` re-fetches the whole latest page. NO pagination. | `web/market/templates/market/chart.js:70-104` |
| Overlay math | `src/indicators.py` index-aligned, warm-up `None`: sma20/ema20 need 19 prior + current; rsi14 needs 14 deltas → first valid index 14. Computing on a page-only window yields `None` for the page's leading points → those overlay points are silently omitted. | `src/indicators.py:12-78`, `tests/web/test_market_api.py:84-105` |
| Tests | Payload layer stub-client into `get_kline_payload`; endpoint layer monkeypatches `market.views.BitunixClient`. E2E dev-only DOM smoke (`@pytest.mark.e2e`, deselected). Patch gate 100%, web ≥85%. | `tests/web/test_market_api.py`, `tests/web/test_market_e2e.py`, `pyproject.toml` |
| Lightweight Charts v5 | Official infinite-history pattern: `timeScale().subscribeVisibleLogicalRangeChange`, detect left-edge via `getVisibleLogicalRange()`, load older, `setData` merged, then `setVisibleLogicalRange` to preserve viewport. `series.update()` exists for the live candle. | Context7 `/tradingview/lightweight-charts` infinite-history tutorial |

## Key Findings (answers to the exploration questions)

### 1. API pagination contract

- **Param**: add optional `before` (UNIX **seconds**, exclusive upper bound = oldest candle currently
  loaded). Omitted → latest page (today's behavior, backward compatible). Keep `limit` `[1,200]`.
  Rationale: the client already speaks unix seconds (`time` everywhere), and DB queries are on
  `time` seconds; the ms conversion stays inside the client seam.
- **Response shape**: unchanged `{"candles":[{time,open,high,low,close}], "overlays":{sma20,ema20,rsi14}}`.
  Previous page returned = the `limit` candles immediately older than `before`, ascending.
- **Empty page**: 200 with `{"candles":[],"overlays":{...empty}}` — the client treats it as "no more history".
- **Validation**: `before` non-int / non-positive → 400 `{"error":"invalid before"}` (mirrors limit handling).

### 2. DB-first vs BitUnix — CONFIRMED DB-FIRST

Reading from `Candle` is the whole point of #43; the endpoint MUST use it.
- **Read `Candle` first** for `symbol, interval, time < before`, ordered `time DESC`, limit `limit + WARMUP`.
- **Gap-fill from BitUnix only when the DB cannot satisfy the page**:
  - interval not persisted at all (1m/30m/6h/8h/12h/3d), OR
  - DB has fewer rows than needed AND BitUnix may hold older data (page requests `before` < `Min(time)`).
  - Fallback call: `client.kline(symbol, interval, limit + WARMUP, end_time=(before or now)*1000)`.
- **When to stop asking BitUnix**: if neither source returns rows older than the cursor → empty page
  (client stops). A per-request `has_more` flag is NOT needed; the empty page is the signal.
- **Degradation (acceptance criterion)**: BitUnix unreachable (`BitunixError`/`RequestException`) MUST
  NOT 5xx when the DB has data — serve the DB rows; only return 502 when BOTH sources fail/empty-by-error.
  Concretely: try DB; if DB yields a full page, never touch BitUnix. If DB is short, attempt BitUnix;
  on upstream failure, return what the DB gave (200) rather than 502.
- **Merge**: DB rows win on duplicate `time` (they are the durable record); union by `time`, drop dups,
  sort ascending, keep the newest `limit + WARMUP`.

This "DB-first, BitUnix gap-fill" resolves the interval-coverage gap (persisted vs chartable) without a
second data path for the common case.

### 3. Overlay correctness across pages (the subtle part) — WARM-UP SLICE

SMA20/EMA20 need 19 prior candles; RSI14 needs 14 deltas. A page computed alone would omit overlays for
its first ~20 points — visibly wrong when scrolling back (overlays vanish at every page boundary).

**Approach: fetch `limit + WARMUP` candidates, compute indicators on the full window, then slice.**

- `WARMUP = 20` (covers sma20/ema20 seed at index 19; rsi14 valid from index 14). One constant, no
  per-indicator bookkeeping.
- Fetch window = `limit + WARMUP` candles ending at the page (all `< before`).
- Compute overlays over the whole window via `src/indicators.py`; **slice candles AND overlays to the
  newest `limit` candles** before returning.
- Result: the page's first candle sits at window index 20 → SMA20/EMA20/RSI14 all defined, EXCEPT at the
  true oldest edge of data (DB floor / BitUnix depth) where warm-up genuinely does not exist; there the
  existing gap-omission rule applies (no nulls, points omitted). This is correct, not a bug.
- Cost: one extra `limit`-normalized fetch of ≤20 rows per request — negligible; DB query is index-backed.

### 4. chart.js infinite scroll

- **State**: add `oldestTime` (min loaded candle time), `loadingOlder` (debounce/in-flight guard),
  `hasMore` (false after an empty page / no-history symbol).
- **Detect left edge**: `chart.timeScale().subscribeVisibleLogicalRangeChange(fn)`; when
  `range.from < EDGE_THRESHOLD` (e.g. 5 logical bars) and `!loadingOlder && hasMore` → `loadOlder()`.
  `subscribeVisibleLogicalRangeChange` is the v5-sanctioned primitive.
- **Debounce**: `loadingOlder` flag set before fetch, cleared in `.finally`; the flag alone prevents
  re-entry (the handler fires on every pan). No timer needed.
- **Load older**: `GET /market/api/kline?symbol=&interval=&limit=200&before=<oldestTime>`.
- **Prepend + preserve viewport**:
  ```
  var range = chart.timeScale().getVisibleLogicalRange();   // capture BEFORE setData
  ... merge newCandles+existing (dedupe by time, keep newest), setData(candles+overlays)
  if (range) chart.timeScale().setVisibleLogicalRange({from: range.from + newCount, to: range.to + newCount});
  ```
  The logical index shifts by `newCount` because data was prepended; shifting the range keeps the same
  bars on screen. This is the official v5 pattern.
- **Merge order**: prepend older; dedupe by `time` keeping the existing (newer) entry to avoid a stale
  duplicate overwriting a fresher row.
- **WS interplay**: `onPush` only calls `candleSeries.update()` on the FORMING (rightmost) candle — far
  from the left prepend, no clobber. The one hazard is `scheduleRefetch()` (bucket-close) which does a
  full `setData` of the latest page: it MUST reset pagination state (`oldestTime` = new page's oldest,
  keep `hasMore`) so a subsequent scroll re-fetches correctly. Design may instead merge the refetch into
  the existing series; simplest correct behavior = refetch replaces series and resets pagination anchors.
- **Overlay prepend**: the older page carries its own sma20/ema20/rsi14; prepend+dedupe them too. RSI
  display text uses the newest rsi point (unchanged).

### 5. Tests

- **Unit — payload pagination (`tests/web/test_market_api.py`)**: `get_kline_payload(..., before=...)`
  returns only candles `< before`; DB-first reads `Candle` not the client when DB is full; gap-fill calls
  the client with `end_time` when the DB is short; merge dedupes by time (DB wins); empty → empty payload;
  WARMUP slicing yields non-None overlays at the page's first candle; DB floor leaves leading gaps omitted.
- **Integration — endpoint**: `before` accepted and forwarded; invalid `before` → 400; empty page → 200
  empty; anonymous → 302; BitUnix failure with DB data → 200 (degradation), both fail → 502.
- **E2E (dev-only DOM)**: after load, scroll the time scale left; assert `/market/api/kline...before=`
  was requested and the candle series grew (DOM/evaluate, no image diffs).
- **Patch gate 100%**: every new branch (DB-full / DB-short / upstream-fail) reachable via stub client +
  seeded `Candle` rows.

### 6. Scope boundaries

**In**: `before` param on `/market/api/kline`; DB-first + BitUnix gap-fill; WARMUP overlay slicing;
chart.js infinite-scroll prepend with viewport preservation + loading guard; tests + E2E smoke.
**Out**: backfill/ingestion (candle-store); retention/prune (#45); cron (#48); new chart indicators;
WS protocol changes; per-user candles; order execution (hard invariant); new runtime deps.

## Affected Areas

- `web/market/quotes.py` — paginated payload builder (DB-first + gap-fill + warm-up slice) (modify)
- `web/market/views.py` — parse/validate `before`, pass through; degradation status handling (modify)
- `web/market/templates/market/chart.js` — infinite scroll, prepend, viewport restore (modify)
- `tests/web/test_market_api.py`, `tests/web/test_market_e2e.py` — pagination matrix + scroll smoke (modify)
- `web/trading/models.py`, `web/trading/candles.py`, `src/client.py`, `urls.py` — **unchanged**
- `requirements.txt`, `web/scheduler.py`, `web/worker.py` — **unchanged**

## Approaches

1. **DB-first + BitUnix gap-fill, WARMUP slice (RECOMMENDED)** — durable dataset serves history; BitUnix
   covers non-persisted intervals and the pre-backfill frontier; overlays correct at page edges.
   Pros: uses #43's dataset (the point); one code path per source; degrades cleanly. Cons: merge logic +
   warm-up slicing is the main new correctness surface. Effort: Medium.
2. **BitUnix-only pagination** — add `before`→`endTime`, skip the DB. Pros: smallest diff. Cons: ignores
   the durable dataset; still capped at ~3y; no degradation benefit. Rejected (contradicts issue #44).
3. **DB-only, no fallback** — Pros: simplest, no merge. Cons: 6 chart intervals unservable; history stops
   at backfill frontier; no gap-fill. Rejected.

## Risks

- **Overlay seam at page boundary** — wrong/missing warm-up → broken overlays on scroll. Mitigation: WARMUP
  constant + a test asserting the page's first candle has non-None sma20/ema20 (and rsi where defined).
- **Viewport jump on prepend** — must shift logical range by prepended count. Mitigation: capture range
  before `setData`, restore after; E2E scroll assertion.
- **Refetch vs pagination state** — bucket-close `setData` can reset the series under the user. Mitigation:
  reset pagination anchors deliberately; document behavior.
- **BitUnix latency/rate limit on gap-fill** — shared 10 req/s. Mitigation: gap-fill only when the DB is
  short; DB-first short-circuits the common case.
- **Patch gate 100% vs DB/BitUnix branches** — Mitigation: inject stub client + seed `Candle` rows; each
  branch is a test.
- **`before` type/units confusion (s vs ms)** — Mitigation: `before` is seconds at the HTTP seam; ms
  conversion only inside `client.kline` call.

## Open Questions (for spec/design)

- Should the endpoint expose an explicit `has_more`/`source` field, or rely on the empty page signal?
  (Recommend empty-page signal — no schema growth.)
- On bucket-close refetch, replace-and-reset vs merge-preserve pagination?
- `WARMUP = 20` fixed vs `max(window)+1` derived from the indicator set?
- Should non-persisted intervals be backfilled (candle-store extension) or permanently BitUnix-served?

## Ready for Proposal

**Yes** — DB-first confirmed, contract and overlay strategy concrete, chart.js pattern validated against
the v5 docs. Open questions are design-level and non-blocking.
