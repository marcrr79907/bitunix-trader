# Delta for chart-legend

Issue #115 (Fase F2). Locks the precision boundary: the per-indicator `style`
precision feeds the **series `priceFormat` only** (axis + crosshair, applied by
`chart-host`). The legend keeps its own frozen `DECIMALS` map and MUST NOT read
`styles[token].precision`. LC1/LC2 are modified to state this explicitly; LC3–LC6
are unchanged and remain in force.

## MODIFIED Requirements

### Requirement: LC1 — legend-core formatter contract

`legend-core.js` MUST be a pure, framework-free ESM core exporting exactly
`DECIMALS`, `PLACEHOLDER`, `formatValue`, `formatOhlc`, `rows`, `lastValues`. It
MUST NOT import any chart library, DOM, network, or `src/` math. `DECIMALS` MUST
be a frozen static token→decimals map: price-like overlays/oscillators = 2
(`sma,ema,bollinger_*,vwap,rsi,stochastic_k,stochastic_d,atr`), MACD family = 4
(`macd,macd_signal,macd_histogram`), `volume` = 0. `DECIMALS` MUST remain a
static, frozen map and MUST NOT be derived from the store's `styles`, the layout,
or the series `priceFormat`; a per-indicator style `precision` MUST NOT change
legend output. Output shapes MUST be plain data (strings/numbers), never DOM
nodes.
(Previously: silent on the style-precision interaction.)

#### Scenario: Known and unknown tokens

- GIVEN `formatValue("macd", 1.2345)` and `formatValue("unknown", 50000.5)`
- THEN MACD uses 4 decimals, the unknown token uses the 2-decimal fallback

#### Scenario: Determinism and never-throw

- GIVEN identical inputs, WHEN `rows` runs twice, THEN output is deep-equal
- GIVEN `value` is `null`, a candle missing keys, or a token absent from `DECIMALS`
- THEN it returns the placeholder/fallback and MUST NOT throw

#### Scenario: Style precision does not change the legend

- GIVEN `styles.sma.precision = 6`
- WHEN the legend formats the `sma` value
- THEN it still uses `DECIMALS.sma` (2), unaffected by the style

#### Scenario: DECIMALS is static and frozen

- GIVEN `legend-core.js`
- WHEN inspected
- THEN `DECIMALS` is a frozen literal with no reference to `styles` or `priceFormat`

### Requirement: LC2 — Single-source, no recompute

The legend MUST read values only from `param.seriesData`, `host.getSeriesData()`,
and `host.getCandles()`; it MUST NOT compute any indicator, SMC, or candle value.
`changePct` is the only arithmetic allowed (change vs `prevClose`) and MUST
operate on server-shaped numbers. `legend-core.js` MUST contain no numeric
window/EMA/RSI/ATR logic. It MUST NOT read `styles` for formatting.
(Previously: silent on the style-precision interaction.)

#### Scenario: No indicator math in the core

- GIVEN `legend-core.js` source, WHEN inspected, THEN it imports nothing and defines no indicator formula

#### Scenario: No style dependency

- GIVEN `legend-core.js` source
- WHEN inspected
- THEN it does not read or import any per-indicator `style`
