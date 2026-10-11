# Design: chart-live-consistency (issue #68)

## Technical Approach

Two layers, mirroring the repo's clean-architecture philosophy:
- **Core** `web/market/templates/market/chart-core.js` — framework-free pure math
  (like `src/`): timeline bucketing + series normalization. UMD so it runs in
  Node (`require`) and browser (`window.ChartCore`) from one source.
- **Adapter** `web/market/templates/market/chart.js` — the edge (like `web/`):
  DOM, Lightweight Charts, WS, REST. Delegates every series decision to the core.

The core is the testable interface; the adapter is thin and has one write path per
concern.

## Core (`chart-core.js`)

```js
function intervalSeconds(interval){ /* 1m..12h,1d,1w,1M */ }

function bucketTime(tsMs, interval){
  if (interval === "1M") {                    // calendar month (UTC)
    var d = new Date(tsMs);
    return Math.floor(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)/1000);
  }
  var sec = intervalSeconds(interval);
  if (interval === "1w") sec = 604800;        // weeks align to Monday
  var s = Math.floor(tsMs/1000);
  var b = Math.floor(s/sec)*sec;
  if (interval === "1w") b += 345600;         // shift to Monday 00:00 UTC
  return b;
}

function upsertCandle(candles, bar){          // in-place, monotonic, deduped
  var n = candles.length;
  if (n === 0 || bar.time > candles[n-1].time){ candles.push(bar); }
  else if (bar.time === candles[n-1].time){ candles[n-1] = bar; }
  // else: older -> ignore
  return candles;
}

function mergeCandles(older, existing){       // pagination: union, existing wins
  var by = {};
  older.forEach(function(c){ by[c.time] = c; });
  existing.forEach(function(c){ by[c.time] = c; });
  return Object.keys(by).map(function(t){ return by[t]; })
    .sort(function(a,b){ return a.time - b.time; });
}

function lastPoint(series){ return series.length ? series[series.length-1] : undefined; }

// UMD export shim
if (typeof module !== "undefined" && module.exports) module.exports = {...};
else if (typeof window !== "undefined") window.ChartCore = {...};
```

**Why a pure core**: the timeline/ordering bugs (1w/1M alignment, flicker,
monotonicity) are *logic*, not DOM. Testing them in Node is deterministic and
fast; testing them in a browser is flaky. This is the same "pure core at the
center, adapters at the edges" rule the project already uses for `src/` vs `web/`.

## Adapter (`chart.js`) — one write path per concern

| Concern | Write path |
|---------|-----------|
| Initial history | `setData` (once) |
| Pagination (older) | `setData` with `mergeCandles` + viewport shift |
| Live stream (WS push) | `update()` only — `upsertCandle` on the array |
| Candle close | small `fetch(limit=2)` → `update()` the candle's last overlay point; **no** `setData` |

- `lastBucket` is derived from the WS bar time via `bucketTime`, **monotonic**
  (a fetch never moves it backwards) → the refetch loop cannot fire.
- Overlays: keep `sma/ema/rsi` arrays; on close, update their **last point** via
  `series.update(point)`. Never `setData` the overlays mid-stream.
- `switchTo` (symbol/interval) is the only full reset: `setData` fresh history,
  reset the WS subscription and `lastBucket`.

## Serving

`web/market/views.py::chart_core_js` renders `market/chart-core.js` as
`text/javascript` (mirror of `chart_js`); `market/urls.py` adds `market/chart-core.js`;
`chart.html` loads core **before** the adapter. Same-origin → CSP `script-src 'self'`
covers it; no relaxation.

## Testing Strategy

- **Node unit** `tests/js/chart-core.test.js` (`node --test`): `bucketTime` for
  every interval incl. **1w → Monday** and **1M → calendar month** using real
  BitUnix timestamps (`1790553600`, `1788220800`); `upsertCandle` (append/update/
  ignore-older, no dup); `mergeCandles` (union, existing wins, ascending).
- **E2E dev-only** (`tests/web/test_market_e2e.py`): load the page, drive pushes
  via `route_web_socket`, spy `LightweightCharts` series `setData`, assert it is
  **not** called during the stream and the series count is monotonic.
- **CI**: new job runs `node --test tests/js` (ubuntu runners ship Node).
- Python coverage unchanged (no new Python except the 4-line view → pytest covers).

## ADRs

- **(a) Pure core + adapter** vs everything in one file: the timeline bugs are logic; a pure core is deterministically testable in Node and keeps the adapter thin (matches the repo's `src/`/`web/` split).
- **(b) UMD shim** vs bundler: zero npm/build; one file loads in both Node and browser.
- **(c) Exchange-aligned bucketing** vs client `floor`: BitUnix aligns 1w to Monday and 1M to calendar months; inventing a timeline produced phantom candles.
- **(d) Overlays via `update()` at close** vs periodic `setData`: keeps indicator points aligned without shifting them; preserves server-side single-source math.
- **(e) `setData` only for history/pagination**: the professional Lightweight Charts streaming pattern.

## Boundary Note

`src/` unchanged/framework-free; `requirements.txt` unchanged; no npm/build; CSP
unchanged; read-only. The JS core is verified by `node --test`; the adapter's
integration by the dev-only E2E.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/market/templates/market/chart-core.js` | New | pure core (UMD) |
| `web/market/templates/market/chart.js` | Rewrite | adapter, single write path |
| `web/market/views.py` | Modify | `chart_core_js` view |
| `web/market/urls.py` | Modify | `market/chart-core.js` route |
| `web/market/templates/market/chart.html` | Modify | load core before adapter |
| `tests/js/chart-core.test.js` | New | `node --test` |
| `tests/web/test_market_e2e.py` | Modify | no-setData-during-stream assertion |
| `.github/workflows/ci.yml` | Modify | Node test job |

## Task Breakdown Hint

~350–450 lines; single PR (one cohesive fix); budget risk Medium. No chaining.

## Open Questions

None blocking. Overlay policy = update-last-point at close (per approved plan).
