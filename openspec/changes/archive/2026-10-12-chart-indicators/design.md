# Design: chart-indicators (issue #70, Fase A1)

## Technical Approach

Extend the existing seam, change nothing structural. Pure math lands in
`src/indicators.py` (single source); `quotes.py` selects the requested set,
derives the warm-up window, serializes `{candles, overlays, panes}`; `views.py`
validates tokens/params; the adapter (`chart.js`) owns a **static pane
registry** and renders it. A toggle is a *config change* → refetch + `setData`
(same class as symbol/interval switch); the live stream keeps `update()` only.

    quote_vol ─┐
    Candles ───┼─→ quotes.get_kline_payload ─→ {candles, overlays, panes} ─→ chart.js registry
    indicators ┘        (select + warmup + slice)                              │
                                                            v5 panes: addSeries(def, opts, paneIndex)

## Indicator functions (`src/indicators.py`)

Same contract as the six existing functions: list-in/list-out, length preserved,
leading `None` warm-up, no mutation, stdlib only (`statistics`).

```python
def macd(series, fast=12, slow=26, signal=9) -> tuple[list, list, list]:
    # line = ema(series,fast) - ema(series,slow)   (None where either leg None)
    # signal = ema(line[slow-1:], signal), left-padded with slow-1 Nones
    # histogram = line[i]-signal[i] where both not None

def bollinger(series, window=20, num_std=2.0) -> tuple[list, list, list]:
    # mid = sma(series,window); sd = pstdev(per window); upper = mid+num_std*sd; lower = mid-num_std*sd

def stochastic(highs, lows, closes, k=14, d=3) -> tuple[list, list]:
    # %K = 100*(close-min(low[-k:])) / (max(high[-k:])-min(low[-k:])); range==0 -> None
    # %D = sma(valid %K suffix, d), left-padded with k-1 Nones
```

`sd == 0` needs **no branch**: `pstdev` returns `0.0`, so bands collapse to the
middle automatically (`upper == middle == lower`). Zero-range stochastic →
`None` (mirrors `zscore`).

## Server registry + payload (`web/market/quotes.py`)

`WARMUP_BASE = 20`. A token registry maps token → placement + builder + warm-up:

| Token | Placement | Output keys | warm-up |
|---|---|---|---|
| `sma20` / `ema20` | overlay | same | 19 |
| `rsi14` (legacy default) | overlay | `rsi14` | 14 |
| `rsi` | pane `rsi` | `rsi` | 14 |
| `macd` | pane `macd` | `macd,signal,histogram` | 33 |
| `bollinger` | overlay | `bollinger_upper/_middle/_lower` | 19 |
| `stochastic` | pane `stochastic` | `k,d` | 15 |
| `atr` | pane `atr` | `atr` | 14 |
| `vwap` | overlay | `vwap` | 0 |
| `volume` | pane `volume` | `volume` | 0 |

Default (`indicators` omitted) = `{sma20, ema20, rsi14}` → `overlays` keys exactly
`{sma20,ema20,rsi14}`, `panes={}` (backward compatible; only `panes` is added to
the response shape). The page always requests its explicit set.

**Warm-up**: `warmup = max(20, max(first_valid_index for token in selected))`
(MACD→33). `want = limit + warmup`; DB reads `limit+warmup`; the upstream BitUnix
`limit` is clamped to `min(want, 200)`. When `want>200` the DB supplies the older
warm-up rows; if the DB lacks them, page-edge points are **omitted** (no nulls),
documented at R3 — never an error. DB-first merge/gap-fill logic is untouched.

**Builder** computes each series over the full warm window, then slices
`[-limit:]` paired with `times[-limit:]` via `_zip` (gaps omitted — arrays never
carry null). Exact response shape:

```json
{"candles":[{"time","open","high","low","close"}],
 "overlays":{"<name>":[{"time","value"}]},
 "panes":{"<pane>":{"type":"line"|"histogram","series":{"<key>":[{"time","value"}]}}}}
```

The `type` hint is per-pane so the adapter picks `LineSeries`/`HistogramSeries`
without duplicating placement knowledge; it is presentation metadata the server
already knows from the registry.

## Volume without leaking candle keys

`quote_vol` is present on merged rows before stripping. Keep the un-stripped
`rows_full`; build `volumes = [r["quote_vol"] for r in rows_full]` (None stays
None → `_zip` omits that bar), compute `panes.volume.volume`, **then** strip
candles to exactly `CHART_KEYS`. R3 "exactly 5 candle keys" holds; volume travels
only in `panes.volume`. Volume pane = **quote_vol** (decision).

## Adapter pane registry + toggle flow (`chart.js`)

```js
var REGISTRY = {
  sma20:{place:"overlay",series:[{key:"sma20",type:"line",color:"#2962ff"}]},
  ema20:{place:"overlay",series:[{key:"ema20",type:"line",color:"#ff6d00"}]},
  bollinger:{place:"overlay",series:[
    {key:"bollinger_upper",type:"line",color:"#7e57c2"},
    {key:"bollinger_middle",type:"line",color:"#7e57c2"},
    {key:"bollinger_lower",type:"line",color:"#7e57c2"}]},
  vwap:{place:"overlay",series:[{key:"vwap",type:"line",color:"#26a69a"}]},
  rsi:{place:"pane",pane:"rsi",series:[{key:"rsi",type:"line",color:"#ab47bc"}]},
  macd:{place:"pane",pane:"macd",series:[
    {key:"macd",type:"line"},{key:"signal",type:"line"},{key:"histogram",type:"histogram"}]},
  stochastic:{place:"pane",pane:"stochastic",series:[{key:"k",type:"line"},{key:"d",type:"line"}]},
  atr:{place:"pane",pane:"atr",series:[{key:"atr",type:"line"}]},
  volume:{place:"pane",pane:"volume",series:[{key:"volume",type:"histogram"}]},
};
```

- **Pane index**: pane 0 = price (candles + overlays). Active panes get contiguous
  indices `1..n` in a fixed `PANE_ORDER = ["rsi","macd","stochastic","atr","volume"]`
  filtered by what is enabled. `chart.addSeries(def, opts, paneIndex)` creates the
  pane on demand.
- **Toggle = config change → rebuild.** On any toggle/param change: `chart.remove()`,
  `createChart(#chart)` fresh, re-add candle + the active set's series at their
  computed pane indices, then `fetchHistory()` → `setData`. This sidesteps v5 empty-
  pane surgery (v5 removes a pane when its last series leaves, and `removePane(i)`
  **shifts** later indices → incremental removal is fragile). `lastBucket` and the
  in-memory arrays survive; the WS is chart-independent.
- **Config change → `setData` is allowed** (identical class to symbol/interval).
- **Single-write-path preserved for the live stream**: WS push still `update()`s
  only the candle. At candle close, `scheduleCloseOverlay` fetches
  `limit=2&indicators=<active>` and, for **every active series**, calls
  `updateLastPoint(series, arr, point)` (generalized from `updateLastOverlay`),
  `update()` only. `rsi` text reads `panes.rsi.rsi` last value (text + pane).
- `fetchHistory`/`loadOlder` build their URL from `state.symbol`, `state.interval`,
  `state.indicators` (comma-joined) and param query string.
- Test seam: `window.marketChart.panes` exposes `{key → series}` for DOM-only E2E.

## Chart HTML (`chart.html`)

Side-panel `<fieldset>` of native `<label><input type="checkbox">` toggles (one per
registry token), keyboard-operable by default, visible focus from the global
`*:focus-visible` token rule; container classes reuse `.panel`/design tokens
(`--surface/--border/--accent`). `/impeccable` audit target. `#rsi` text kept.

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (py) | `macd`/`bollinger`/`stochastic`: exact fixtures + invariants (length, warm-up count, `hist==macd-signal`, no mutation, bounded) | `tests/test_indicators.py` |
| Integration (py) | token selection, unknown token → 400, derived warm-up (MACD→33), candles exactly 5 keys, `panes.volume` == quote_vol, MACD page-edge non-null; update the two exact-shape tests (add `panes`) | `tests/web/test_market_api.py` |
| E2E (js) | panes render, toggle adds/removes a pane, no mid-stream `setData`, close refresh `update()` only, no console errors | `tests/web/test_market_e2e.py` (dev-only) |
| Node | unchanged — `chart-core.js` adds no math | `tests/js/chart-core.test.js` |

Patch gate 100% (Python); JS covered by E2E. `ruff` clean; boundary test green
(`indicators.py` stays stdlib-only).

## ADRs

- **(a) Server-selected set vs client selection**: server selects → single math
  source (hard invariant), no over-fetch, warm-up derived per request. Rejected
  "return all" (over-fetch) and "compute in JS" (violates invariant).
- **(b) Derived warm-up vs fixed 20**: `max(20, …)` keeps page-edge values defined
  for MACD (33) without a magic per-indicator constant at the call site.
- **(c) Pane rebuild vs incremental surgery**: full rebuild on toggle —
  `removePane` shifts indices and empty-pane lifecycle is fragile; rebuild is
  deterministic and reuses the existing `setData` history path.
- **(d) Exact-5-key candles via the `panes` bucket**: volume/params ride new
  buckets, so R3's candle shape is untouched (compat + a clean seam).

## Boundary Note

`src/` unchanged/framework-free (pure functions only); `requirements.txt`, CSP,
DB, and `chart-core.js` unchanged; read-only. No npm/build.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/indicators.py` | Modify | + `macd`, `bollinger`, `stochastic` |
| `web/market/quotes.py` | Modify | token registry, selection, derived warm-up, `panes`, volume |
| `web/market/views.py` | Modify | validate `indicators` + flat param names → 400 |
| `web/market/templates/market/chart.js` | Modify | pane registry, rebuild-on-toggle, generalized close refresh |
| `web/market/templates/market/chart.html` | Modify | keyboard-operable toggle fieldset |
| `tests/test_indicators.py` | Modify | fixtures for 3 new functions |
| `tests/web/test_market_api.py` | Modify | selection/warm-up/shape |
| `tests/web/test_market_e2e.py` | Modify | pane + toggle E2E |

## Task Breakdown Hint

~550–650 lines; 400-line budget risk **High**. Chained PRs:
- **PR1** — `src/indicators.py` + `tests/test_indicators.py` (pure, autonomous).
- **PR2** — `quotes.py` registry/warm-up/panes/volume + `views.py` validation +
  `tests/web/test_market_api.py`.
- **PR3** — `chart.js` panes/toggles + `chart.html` + `tests/web/test_market_e2e.py`.
- **PR4 (optional)** — split the Python integration tests if PR2 still overruns.

Each slice: clear start/finish, autonomous, own tests, trivially revertible.
`Decision needed before apply: Yes`, `Chained PRs recommended: Yes`.

## Open Questions

None blocking. All five proposal questions are resolved: warm-up = derived
(clamp upstream to 200; DB supplies older; page-edge omission documented); volume
= quote_vol; Bollinger `sd==0` collapses to middle; default set unchanged
`{sma20,ema20,rsi14}`; RSI text and pane both kept.
