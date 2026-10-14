# Delta for chart-indicator-settings

Issues #144: **verification-evidence only**. F2 behavior already holds; these deltas record that its probe-only scenarios are now guarded by committed regression tests, and add one committed module-size guard. No production file, no 9th `window.marketChart` seam key, no CSP change.

## MODIFIED Requirements

### Requirement: F2.5 — Host apply contract

`host.build(state)` MUST read `state.styles[token]` per series, falling back to the registry default when absent, and MUST apply `color`/`lineWidth` at series construction and `precision` as the series `priceFormat` (`{precision, minMove: 10^-precision}`). A style change MUST travel `indicator:changed` → `rebuild()` (the `setData` path); the live WS `update()` path MUST remain the sole writer for candles (#68). Precision MUST NOT mutate the legend `DECIMALS` map. The one-rebuild invariant MUST now be proven by a committed E2E (`tests/web/test_market_e2e.py`) that wraps the CDN global `LightweightCharts.createChart` in-page as a counter (NOT a `window.marketChart` key) and asserts `=== 1` builds after one confirmed style change; the legend style-independence MUST be proven by committed source assertions in `tests/js/legend-core.test.js` that `legend-core.js` and `controllers/legend.js` contain no `styles`/`priceFormat` token.
(Previously: the one-rebuild and legend-style-independence scenarios were proven only by session probes.)

#### Scenario: Series reflects style

- GIVEN `styles.sma = {color:"#ff0000", lineWidth:3, precision:5}`
- WHEN the chart builds
- THEN the `sma` series `options()` have that color/lineWidth and priceFormat precision 5

#### Scenario: Missing style uses registry default

- GIVEN no `styles` entry for `ema`
- WHEN the chart builds
- THEN the `ema` series uses the registry color, width 1

#### Scenario: One rebuild per style change (#68 intact)

- GIVEN an active chart with the `createChart` counter installed
- WHEN a style is confirmed
- THEN exactly one `rebuild()` runs on the `setData` path, `createChart` is called exactly once, and no live-path full `setData` occurs

#### Scenario: Legend output ignores style precision

- GIVEN `legend-core.js` and `controllers/legend.js` sources
- WHEN `tests/js/legend-core.test.js` scans them
- THEN neither contains a `styles`/`priceFormat` read — the legend cannot be affected by a per-indicator style precision

### Requirement: F2.9 — Scope and isolation

Style MUST be scoped per chart, i.e. per `(user, symbol, interval)` — NOT global-per-token, NOT cross-chart. User B MUST NOT read or write A's style (inherited from the layout isolation contract). The A≠B scenario MUST now be proven by committed assertions in `tests/web/test_isolation.py`: A's `ChartLayout` carrying an indicator `style` yields `ChartLayout.for_user(B).count() == 0` and `for_user(B).get(...)` raises `DoesNotExist`, so B can never read the row that carries the style.
(Previously: style isolation was proven only by a session probe.)

#### Scenario: A ≠ B

- GIVEN A saved a layout with a styled indicator for `BTCUSDT,1m`
- WHEN `tests/web/test_isolation.py` evaluates `for_user(B)`
- THEN B's queryset is empty and `get` raises `DoesNotExist` — B never sees A's style

## ADDED Requirements

### Requirement: F2.10 — Module-size ceiling guard (R14)

A committed guard `tests/web/test_module_size_guard.py` MUST enforce the R14 layer rule that no module exceeds ~300 lines. It MUST define `CEILING = 300` and scan every `web/market/templates/market/**/*.js` file (including `controllers/`) via `Path.rglob("*.js")` with `len(path.read_text().splitlines())`. It MUST carry an **explicit allowlist** exempting `chart-host.js` (326 lines), annotated with a comment referencing R14 "~300" and DEBT-5 (#146) as the tracked refactor. The guard MUST FAIL for any **other** module exceeding `CEILING`, naming the offending file and its line count. It is pure filesystem (no Django client, no network) and adds no dependency.

#### Scenario: Current tree passes with the documented exception

- GIVEN the current modules, WHEN the guard runs
- THEN it passes and `chart-host.js` is exempted by the annotated allowlist (DEBT-5 / #146)

#### Scenario: A synthetic over-ceiling module fails the guard (negative control)

- GIVEN any module other than `chart-host.js` with more than `CEILING` lines
- WHEN the guard runs
- THEN it fails and the failure names that file and its line count
