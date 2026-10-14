# Delta for chart-legend

Issues #143/#144: **verification-evidence only**. The behavior below already holds and is unchanged; these deltas record that four probe-only scenarios are now guarded by committed regression tests. No production file, no seam key, no CSP change.

## MODIFIED Requirements

### Requirement: LC2 — Single-source, no recompute

The legend MUST read values only from `param.seriesData`, `host.getSeriesData()`, and `host.getCandles()`; it MUST NOT compute any indicator, SMC, or candle value. `changePct` is the only arithmetic allowed (change vs `prevClose`) and MUST operate on server-shaped numbers. `legend-core.js` MUST contain no numeric window/EMA/RSI/ATR logic. It MUST NOT read `styles` for formatting. The "imports nothing / no indicator formula" scenario MUST now be proven by a committed source test in `tests/js/legend-core.test.js`, which asserts no line-leading `import`/`export … from` in `legend-core.js` and scans the **comment-stripped** source for indicator tokens (so header prose mentioning EMA/RSI/ATR cannot false-positive).
(Previously: the purity scenario was proven only by a throwaway session probe; no committed test guarded it.)

#### Scenario: No indicator math in the core

- GIVEN `legend-core.js` source
- WHEN `tests/js/legend-core.test.js` reads it (`readFileSync` + `fileURLToPath`)
- THEN it asserts no line-leading `import`/`export … from` and no indicator token in the comment-stripped source

#### Scenario: No style dependency

- GIVEN `legend-core.js` source
- WHEN inspected
- THEN it does not read or import any per-indicator `style`

### Requirement: LC4 — Host crosshair seam

`chart-host.js` MUST expose `subscribeCrosshairMove(fn)`, null-guarded on `chart`, mirroring `subscribeClick`. Because `build()` recreates the chart, the legend MUST re-subscribe on every `chart:built` event; the stale handler dies with the removed chart. The re-subscribe scenario MUST now be proven by a committed E2E (`tests/web/test_market_e2e.py`) that forces a second `chart:built` via an indicator toggle, then hovers and asserts the rebuilt chart's OHLC row updates with exactly one `.chart-legend`.
(Previously: re-subscribe across rebuilds was proven only by a session probe.)

#### Scenario: Re-subscribe across rebuilds

- GIVEN two successive `chart:built` events
- WHEN the legend binds its handler
- THEN it subscribes on the current chart each time, the hover readout updates, and exactly one `.chart-legend` overlay exists

### Requirement: LC5 — Overlay DOM and a11y policy

The legend MUST render as a single `<div class="chart-legend" role="status" aria-label="Chart legend">` anchored top-left inside `#chart` (`position:absolute; pointer-events:none`; `#chart` gains `position:relative`). The crosshair readout MUST NOT be live-announced. `aria-live="polite"` MUST be scoped to an idle summary only, debounced (≥300ms) and updated solely on state changes (symbol/interval/indicator) or idle last-value refresh — NEVER per mousemove. Change values MUST carry a signed `.num` text cue (not color alone). The idle-announcement policy MUST now be proven by a committed E2E (`tests/web/test_market_e2e.py`) that drives rapid crosshair moves and asserts the region is `aria-live="off"` during hover and only one polite transition occurs after leaving past the debounce.
(Previously: the idle-vs-per-move policy was proven only by a session probe.)

#### Scenario: Hover does not spam screen readers

- GIVEN repeated crosshair moves, WHEN `tests/web/test_market_e2e.py` drives them over ~1s
- THEN the region stays `aria-live="off"` and no per-move announcement is emitted

#### Scenario: State change announces once

- GIVEN the pointer leaves and the ≥300ms debounce settles
- WHEN the idle summary updates
- THEN exactly one `aria-live="polite"` transition occurs

### Requirement: LC6 — Composition, lifecycle, responsive

The legend MUST be composed into the shell that remains and show ALL active series (overlays first, then pane order). It MUST re-render the idle snapshot on `chart:built`, `candle:closed`, and `history:loaded`. At 375px it MUST NOT overflow the chart (`max-width:min(90%,320px)`, wrap/clip) and MUST introduce no `window.marketChart` key. The "all active series shown" scenario MUST now assert **exact** counts and labels (not `>= 1`) in `tests/web/test_market_e2e.py`: with default actives, exactly three `.lg-row` and token labels `["SMA 20","EMA 20","RSI"]` (overlays first, then pane).
(Previously: the E2E asserted `.lg-row count >= 1`, which passed even if series were missing.)

#### Scenario: All active series shown

- GIVEN overlays and panes enabled (default `sma`, `ema`, `rsi`)
- WHEN the chart boots and idles
- THEN `tests/web/test_market_e2e.py` asserts exactly 3 `.lg-row` and labels `["SMA 20","EMA 20","RSI"]` in order

#### Scenario: 375px no overflow

- GIVEN a 375px viewport, THEN the overlay stays within `#chart` bounds with no horizontal overflow

#### Scenario: Seam frozen

- GIVEN a booted chart, THEN `window.marketChart` still has exactly its eight keys
