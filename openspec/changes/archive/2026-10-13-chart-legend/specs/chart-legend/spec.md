# chart-legend Specification

## Purpose

TradingView-style floating legend + crosshair OHLC/indicator readout for the
market chart. Read-only: the legend formats server-shaped values and recomputes
nothing. New capability — no prior spec. F1 (issue #114).

## Requirements

### Requirement: LC1 — legend-core formatter contract

`legend-core.js` MUST be a pure, framework-free ESM core exporting exactly
`DECIMALS`, `PLACEHOLDER`, `formatValue`, `formatOhlc`, `rows`, `lastValues`. It
MUST NOT import any chart library, DOM, network, or `src/` math. `DECIMALS` MUST
be a frozen static token→decimals map: price-like overlays/oscillators = 2
(`sma,ema,bollinger_*,vwap,rsi,stochastic_k,stochastic_d,atr`), MACD family = 4
(`macd,macd_signal,macd_histogram`), `volume` = 0. Output shapes MUST be plain
data (strings/numbers), never DOM nodes.

- `formatValue(token, value) → string`: number → fixed `DECIMALS[token]` string
  (2-decimal fallback for an unknown token); `null`/`undefined` → `PLACEHOLDER`.
- `formatOhlc(candle) → {open,high,low,close,dir}`, all strings; `dir` is the
  signed change direction (no `prevClose` arithmetic beyond the allowed case).
- `rows(entries, activeSeries, candle) → {ohlc, series:[{token,key,place,pane,label,value}]}`,
  where each entry carries a chart-lib-free `{token,key,place,pane,value}`
  (the controller builds `entries` from the crosshair `seriesData` Map).
- `lastValues(activeSeries, seriesData, candles) → {candle, entries:[{key,value}]}`:
  recomputes the `o:/p:` dataKey locally so the core stays chart-lib-free; used
  for the not-hovering fallback.

#### Scenario: Known and unknown tokens

- GIVEN `formatValue("macd", 1.2345)` and `formatValue("unknown", 50000.5)`
- THEN MACD uses 4 decimals, the unknown token uses the 2-decimal fallback

#### Scenario: Determinism and never-throw

- GIVEN identical inputs, WHEN `rows` runs twice, THEN output is deep-equal
- GIVEN `value` is `null`, a candle missing keys, or a token absent from `DECIMALS`
- THEN it returns the placeholder/fallback and MUST NOT throw

### Requirement: LC2 — Single-source, no recompute

The legend MUST read values only from `param.seriesData`, `host.getSeriesData()`,
and `host.getCandles()`; it MUST NOT compute any indicator, SMC, or candle value.
`changePct` is the only arithmetic allowed (change vs `prevClose`) and MUST
operate on server-shaped numbers. `legend-core.js` MUST contain no numeric
window/EMA/RSI/ATR logic.

#### Scenario: No indicator math in the core

- GIVEN `legend-core.js` source, WHEN inspected, THEN it imports nothing and defines no indicator formula

### Requirement: LC3 — Crosshair readout contract

The legend MUST update on each crosshair move from `param.seriesData`
(`get(host.getCandleSeries())` for OHLC; `get(a.series)` per `getActiveSeries()`
entry) and MUST fall back to the last value of each active series when not
hovering (`getSeriesData()[dataKey]` last element; `getCandles()` last bar).
Updates MUST be coalesced with `requestAnimationFrame` and MUST write
`textContent` only (never `innerHTML`).

#### Scenario: Hover shows the bar under the cursor

- GIVEN a crosshair move with `param.point` defined
- THEN OHLC and each active series show the values from `param.seriesData` at that time

#### Scenario: Leave shows last values

- GIVEN `param.point === undefined`
- THEN OHLC shows the last candle and each active series its last value, without recompute

#### Scenario: Off-bar gap is null-safe

- GIVEN a series absent from `param.seriesData` at the cursor
- THEN that row renders the `"–"` placeholder and no throw occurs

### Requirement: LC4 — Host crosshair seam

`chart-host.js` MUST expose `subscribeCrosshairMove(fn)`, null-guarded on
`chart`, mirroring `subscribeClick`. Because `build()` recreates the chart, the
legend MUST re-subscribe on every `chart:built` event; the stale handler dies
with the removed chart.

#### Scenario: Re-subscribe across rebuilds

- GIVEN two successive `chart:built` events
- WHEN the legend binds its handler
- THEN it subscribes on the current chart each time and no stale handler remains

### Requirement: LC5 — Overlay DOM and a11y policy

The legend MUST render as a single `<div class="chart-legend" role="status"
aria-label="Chart legend">` anchored top-left inside `#chart`
(`position:absolute; pointer-events:none`; `#chart` gains `position:relative`).
The crosshair readout MUST NOT be live-announced. `aria-live="polite"` MUST be
scoped to an idle summary only, debounced (≥300ms) and updated solely on state
changes (symbol/interval/indicator) or idle last-value refresh — NEVER per
mousemove. Change values MUST carry a signed `.num` text cue (not color alone).

#### Scenario: Hover does not spam screen readers

- GIVEN repeated crosshair moves, WHEN the region is inspected over a 1s window
- THEN no `aria-live` announcement is emitted per move

#### Scenario: State change announces once

- GIVEN an interval change or idle refresh, WHEN it settles past the debounce
- THEN exactly one polite summary update occurs

### Requirement: LC6 — Composition, lifecycle, responsive

The legend MUST be composed into the shell that remains and show ALL active
series (overlays first, then pane order). It MUST re-render the idle snapshot on
`chart:built`, `candle:closed`, and `history:loaded`. At 375px it MUST NOT
overflow the chart (`max-width:min(90%,320px)`, wrap/clip) and MUST introduce no
`window.marketChart` key.

#### Scenario: All active series shown

- GIVEN overlays and panes enabled, THEN the legend lists one row per active series

#### Scenario: 375px no overflow

- GIVEN a 375px viewport, THEN the overlay stays within `#chart` bounds with no horizontal overflow

#### Scenario: Seam frozen

- GIVEN a booted chart, THEN `window.marketChart` still has exactly its eight keys

## Edge-Case Matrix

| Case | Input | Expected |
|---|---|---|
| Empty `seriesData` | `param.seriesData` empty Map | OHLC/series → `"–"`, no throw |
| No active series | `getActiveSeries() === []` | `series:[]`, OHLC still rendered |
| Off-bar | `param.point === undefined` | last-value fallback |
| Unknown token | `key` not in `DECIMALS` | 2-decimal fallback |
| 375px | narrow viewport | overlay clipped inside `#chart`, no overflow |

## Non-Applicable Domains

- **core-domain-boundary**: N/A — served JS under `web/market/templates`, not `src/`.
- **design-system**: consumes existing tokens (`--surface`, `--text`, `--mono`, `--up/--dn`, `.num`); no token change.
