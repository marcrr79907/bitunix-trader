# Exploration: chart-indicators (issue #70, Fase A1)

## Current State

The chart pipeline is server-computed and already layer-separated:

- `src/indicators.py` — pure, index-aligned, stdlib-only. Existing: `sma`,
  `ema`, `rsi`, `atr`, `vwap`, `zscore`. Contract (spec
  `technical-indicators` R1–R8): output length == input length; leading warm-up
  positions are `None`; undefined math (÷0, zero range) is `None`; **no I/O,
  no network**; enforced by `tests/test_boundary.py::PURE_MODULES`.
  **MISSING: `macd`, `bollinger`, `stochastic`.**
- `web/market/quotes.py::get_kline_payload(client, symbol, interval, limit,
  before)` — DB-first cursor page + BitUnix gap-fill, `WARMUP = 20` fixed,
  candles stripped to `CHART_KEYS = (time, open, high, low, close)`, indicators
  computed over the warm window then sliced to the page. Response is
  `{candles:[...], overlays:{sma20, ema20, rsi14}}`; `_zip()` omits `None` gaps
  (LWC series arrays must never carry null). `quote_vol` is present on rows
  before stripping but **discarded** — no volume reaches the client today.
- `web/market/views.py::api_kline` — GET, `@login_required`, validates
  `interval ∈ INTERVALS`, clamps `limit ∈ [1,200]`; no indicator params exist.
- `web/market/templates/market/chart.js` — adapter: `addSeries(CandlestickSeries)`
  + 2 `LineSeries` at the default pane (0), RSI as text in the side panel.
  Single-write-path rule (#68): `setData` only for history reset + pagination
  merge; live stream uses `update()` only; overlays advance via
  `updateLastOverlay()` at candle close. Timeline math delegated to the pure
  core `chart-core.js` (`bucketTime`/`upsertCandle`/`mergeCandles`/`lastPoint`).
- Lightweight Charts **v5.2.0** pinned CDN. Panes render via
  `chart.addSeries(SeriesDef, options, paneIndex)` (not used yet).
- Tests: `tests/test_indicators.py` (pure fixtures),
  `tests/web/test_market_api.py` asserts the **exact** payload shape
  (`set(body["overlays"]) == {"sma20","ema20","rsi14"}` and `set(body) ==
  {"candles","overlays"}`) — these MUST be updated by this change.
  `tests/web/test_market_e2e.py` (dev-only, `page.route_web_socket`),
  `tests/js/chart-core.test.js` (`node --test`).
- CSP strict (`script-src 'self' https://unpkg.com`, no inline); `requirements.txt`
  unchanged; `read-only` (security-invariants R11); boundary R9.

## Answers to the exploration questions

### 1. Missing pure indicators — signatures, formulas, warm-up

All mirror the existing contract: `list in → list out`, same length, leading
`None`, no mutation, stdlib only (`statistics`).

**MACD (12/26/9)** — returns a **3-tuple of aligned arrays**:

```python
def macd(
    series: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """(macd_line, signal_line, histogram), each length == len(series)."""
```

- `macd_line[i] = ema(series, fast)[i] - ema(series, slow)[i]` (`None` where
  either leg is `None`). First valid index = `slow - 1` = **25**.
- `signal_line` = `ema()` over the **valid suffix** of `macd_line` (strip
  leading `None`s), then left-pad with `slow - 1` `None`s. First valid index =
  `slow - 1 + signal - 1` = **33**.
- `histogram[i] = macd_line[i] - signal_line[i]`.
- A tuple (not a dict/dataclass) preserves the index-aligned, zip-friendly
  style of the module and keeps the interface small.

**Bollinger (20, 2σ)** — 3-tuple:

```python
def bollinger(
    series: list[float],
    window: int = 20,
    num_std: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """(upper, middle, lower), each length == len(series)."""
```

- `middle = sma(series, window)`; `sd[i] = statistics.pstdev(window)`.
- `upper = middle + num_std*sd`, `lower = middle - num_std*sd`. Warm-up =
  `window - 1` = **19**.
- **Decision needed:** `sd == 0` (flat window). `zscore` returns `None` there,
  but bands are mathematically defined (collapse to the SMA). Recommendation:
  return `middle` (bands equal), not `None` — a flat market still has a valid
  band; flag for spec.

**Stochastic (14,3)** — 2-tuple:

```python
def stochastic(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    k_window: int = 14,
    d_window: int = 3,
) -> tuple[list[float | None], list[float | None]]:
    """(%K, %D), each length == len(closes)."""
```

- `%K[i] = 100 * (close[i] - min(low[i-k+1:i+1])) / (max(high[...]) - min(low[...]))`;
  zero range → `None`. Warm-up `k_window - 1` = **13**.
- `%D = sma(valid %K, d_window)` (simple SMA — the conventional "slow" line),
  left-padded; first valid = `k_window + d_window - 2` = **15**.
- Mirror `atr`'s multi-input signature exactly.

Warm-up (= first valid index, the fetch-window requirement per indicator):

| Indicator | First valid index (leading `None`s) |
|---|---|
| `macd` line | 25 |
| `macd` signal/histogram | 33 |
| `bollinger` | 19 |
| `stochastic` %K | 13 |
| `stochastic` %D | 15 |
| `rsi` / `atr` (existing) | 14 |
| `sma`/`ema` 20 (existing) | 19 |
| `vwap` | 0 |

### 2. Payload extension (`quotes.py`)

Extend the signature (keyword-only, defaults preserve today's behavior):

```python
def get_kline_payload(
    client, symbol, interval, limit, before=None,
    indicators: frozenset[str] | None = None,
    params: dict | None = None,
) -> dict:
```

- **Selection:** `indicators=None` → default set
  `{sma, ema, rsi}` (identical to today → existing payload tests stay green).
  The chart explicitly requests its set. An allowlist maps each token to its
  computation; an unknown token → `views.api_kline` returns 400 before the
  payload builds (validated in the view, like `interval`).
- **Warm-up (critical):** replace the fixed `WARMUP = 20` with a computed
  `warmup = max(20, max(first_valid_index for requested indicators))`. MACD
  forces **33**. Server fetches `limit + warmup` and slices indicators to the
  page — pane-edge MACD/Stoch values are correct on the first page candle.
- **Candle keys:** unchanged, exactly `CHART_KEYS` (spec R3 preserved).
- **Response shape** — two data buckets, client owns presentation:

```json
{
  "candles": [{"time","open","high","low","close"}],
  "overlays": {"<name>": [{"time","value"}...]},
  "panes":    {"<pane>": {"<series>": [{"time","value"}...]}}
}
```

  - `overlays` (price scale): `sma20`, `ema20`, `bollinger_upper`,
    `bollinger_middle`, `bollinger_lower`, `vwap`.
  - `panes` (sub-panes): `rsi` → `{rsi}`, `atr` → `{atr}`, `macd` →
    `{macd, signal, histogram}`, `stochastic` → `{k, d}`, `volume` →
    `{volume}`.
  - Pane identity/order/colors are **not** sent by the server (presentation
    concern; YAGNI) — the adapter holds a static registry.
- **Volume:** `quote_vol` is on merged `rows` before stripping. `vwap` needs
  `volumes`, and the volume pane needs a series — build both from the merged
  rows **without** touching `CHART_KEYS` (volume travels in `panes.volume`, so
  spec R3 "exactly 5 candle keys" holds). **Decision needed:** quote volume
  (mapped today as `quote_vol`) vs base volume (`baseVol`, not mapped).
- **Params:** flat query params (`rsi_len`, `sma_len`, `ema_len`, `bb_len`,
  `bb_std`, `macd_fast`, `macd_slow`, `macd_signal`, `stoch_k`, `stoch_d`,
  `atr_len`), validated in the view; only tokens the issue names plus the
  existing lengths are supported (no config object).

### 3. Adapter (`chart.js`) — overlays, panes, toggles

- **Price overlays** stay in pane 0 (`addSeries(LineSeries, opts)`), fed from
  `payload.overlays`. Bollinger = 3 LineSeries (upper/middle/lower, middle
  lighter); VWAP/SMA/EMA = 1 each.
- **Sub-panes** via v5 pane index: `chart.addSeries(LineSeries|HistogramSeries,
  opts, paneIndex)` where pane 1 = RSI, 2 = MACD, 3 = Stochastic, 4 = ATR,
  5 = Volume. MACD histogram → `HistogramSeries`; %K/%D, macd/signal → Line.
  Panes are declared by the adapter's static registry (key → {kind, paneIndex,
  series meta}), not by the server.
- **Toggle:** a checkbox per indicator. On change the adapter rebuilds its
  request set and calls `fetchHistory()` — this is a *config change*, so a
  full `setData` (history reset) is the correct, allowed write path, exactly
  like the symbol/interval switch. No incremental pane patching.
- **Single-write-path rule preserved:** `setData` only on history reset /
  pagination merge; the live WS stream keeps using `update()` for the candle;
  at candle close, `updateLastOverlay()`-style refresh updates each active
  pane/overlay's **last point** via `update()` (generalize the existing
  `updateLastOverlay` to iterate the active series registry). No periodic
  `setData`.
- **Timeline math** stays in the pure core; the change adds **no core math**
  (paneIndex is chart API, registry is static config) → `chart-core.js`
  unchanged. `node --test` only if we choose to add a pure helper.
- **Test seam:** extend `window.marketChart` to expose the active series map
  (e.g. `marketChart.panes.rsi`) for DOM-only E2E assertions.
- **A11y/UI:** toggle controls live in the side panel, keyboard-operable, with
  visible focus; the final pass is audited with `/impeccable`.

### 4. Warm-up per indicator (server history fetch)

`limit + warmup` where `warmup = max(20, max(first_valid_index of the requested
set))`; MACD → **33**, Bollinger → 19, Stochastic → 15, RSI/ATR → 14. This is
the only change to the fetch window; the DB-first + gap-fill merge logic is
untouched. **Risk:** BitUnix `limit` max is 200 while `limit(≤200)+warmup` can
reach 233 with MACD — see Risks (pre-existing overshoot, worsened here).

### 5. Tests

- **Pure units** (`tests/test_indicators.py`): `macd`/`bollinger`/`stochastic`
  with small-window known fixtures + structural invariants
  (`hist == macd − signal`; each output length == input; warm-up `None` count;
  no mutation). E.g. `bollinger([1,2,3,4,5], 3, 2)` → idx2 upper ≈ 3.633,
  middle 2.0, lower ≈ 0.367; `stochastic` k=3 → `%K = [None,None,50,75,50]`,
  `%D[4] ≈ 58.33`.
- **Payload selection/warm-up** (`tests/web/test_market_api.py`): selected set
  is exactly returned; unknown indicator → 400 via view; MACD request fetches
  `limit + 33`; candle keys stay exactly 5; volume pane present; `panes`/`overlays`
  shape. Update the two existing exact-shape assertions (default set unchanged
  → minimal churn).
- **E2E dev-only** (`tests/web/test_market_e2e.py`): panes render (canvas/DOM
  count grows vs. baseline), toggle adds/removes a pane, no JS console errors,
  stream still uses `update()` only.
- **`node --test`** only if `chart-core.js` changes (planned: none).
- **Patch gate 100%**: all new Python lines covered; JS is template-side (not
  measured by diff-cover) and covered by E2E.

## Affected Areas

- `src/indicators.py` — add `macd`, `bollinger`, `stochastic`.
- `tests/test_indicators.py` — pure fixtures for the three new functions.
- `web/market/quotes.py` — selectable indicators, computed warm-up, `panes`,
  volume, params.
- `web/market/views.py` — validate `indicators`/params, pass through.
- `web/market/templates/market/chart.js` — overlays + pane registry + toggles +
  generalized close-refresh.
- `web/market/templates/market/chart.html` — indicator toggle controls.
- `tests/web/test_market_api.py` — payload/endpoint selection, warm-up, shape.
- `tests/web/test_market_e2e.py` — pane/toggle E2E.
- `openspec/specs/market-chart/spec.md` — R3/R4 delta (payload) at archive time.

## Approaches

1. **Server-selected set per request (RECOMMENDED)** — query param selects the
   indicator set; warm-up computed from it; response carries `overlays` +
   `panes`. Client owns presentation. Pros: single math source (invariant),
   no over-fetch, toggle = refetch. Cons: response shape grows; tests updated.
   Effort: Medium.
2. **Return ALL indicators always** — Pros: no selection logic. Cons: over-fetch,
   larger payload, wasted compute, harder warm-up budget, ignores issue wording.
   Effort: Low. Rejected.
3. **Client computes panes in JS** — Violates the hard invariant (no indicator
   math in the browser). Rejected.

## Recommendation

Approach 1. It keeps the existing seam (server math, adapter renders), extends
it minimally, and preserves every invariant (boundary, CSP, no npm, read-only,
single write path). Backward-compatible default set limits test churn.

## Risks

- **BitUnix `limit ≤ 200` vs `limit + warmup` (→233 with MACD).** Pre-existing
  overshoot, worsened. Mitigation: clamp the upstream request to 200 and let
  the DB cover the remainder, or document the upstream clamp. Design decision.
- **LWC v5 pane lifecycle** — removing the last series in a pane may leave an
  empty pane; `removePane`/`removeSeries` semantics need doc verification.
  Mitigation: verify in design; rebuild-by-refetch sidesteps incremental
  pane surgery.
- **Response-shape change** breaks the two exact-shape payload tests.
  Mitigation: keep the default set identical; update tests deliberately.
- **Volume source ambiguity** (quote vs base). Mitigation: pick in spec.
- **Bollinger `sd == 0`** semantics. Mitigation: decide in spec.
- **MACD return type** (tuple of 3) vs a mapping. Mitigation: prefer the tuple
  to match the module's list-in/list-out style.
- **`rsi14` text in the side panel** — keep or migrate to the RSI pane? UX
  decision; not blocking.

## Open Questions (for spec/design)

1. `limit + warmup > 200`: clamp upstream and rely on DB, or cap `limit`?
2. Volume series: quote volume or base volume?
3. Bollinger flat-window (`sd == 0`): collapse bands or `None`?
4. Default indicator set when `indicators` is omitted — keep `{sma20, ema20,
   rsi14}` (recommended) or a richer default?
5. Side-panel RSI text: keep alongside the RSI pane or remove?

## Ready for Proposal

YES — all questions answered with file references; architecture is a direct
extension of the existing seam; the only pre-spec decisions are the five open
questions above.
