# Delta for market-chart

Issue #114 (Fase F1): adds the `chart-legend` module to the frozen inventory and
the host crosshair-subscription seam the legend binds to. R1–R13, R15–R17 stay in
force and unmodified; R18 is unchanged (no new `window.marketChart` key).

## ADDED Requirements

### Requirement: R19 — Host crosshair subscription seam

`chart-host.js` MUST expose `subscribeCrosshairMove(fn)` (crosshair is host-owned
per R14), null-guarded on `chart`, mirroring `subscribeClick`. Because `build()`
calls `chart.remove()` and creates a new chart, any crosshair handler registered
on a prior chart MUST be considered dead; consumers MUST re-subscribe after each
`chart:built`. No new bus event is introduced.

#### Scenario: Method mirrors subscribeClick

- GIVEN a built chart, WHEN `subscribeCrosshairMove(fn)` is called, THEN it delegates to `chart.subscribeCrosshairMove(fn)` and is a no-op when `chart` is null

#### Scenario: Handler re-binds after rebuild

- GIVEN `chart:built` fires again after `build()`, WHEN the legend subscribes, THEN the handler is bound to the current chart object

## MODIFIED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`, `chart-store.js` (UI/config state ONLY —
MUST NOT hold candle data), `chart-bus.js`, `chart-host.js` (chart/series/panes/
scales/crosshair + candle data), `controllers/{indicators,history,stream,
drawings,smc,toolbar,legend}.js`, and `main.js` (ALL orchestration + boot/switch).
No module MUST exceed ~300 lines. Controllers MUST import host/store/bus directly
but MUST NOT import `main`; commands MUST travel the bus, so `main.js` has no
circular imports. Every imported module MUST be served same-origin under
`/market/` via its Django route (core → `MODULE_ALLOWLIST`, controller →
`CONTROLLER_ALLOWLIST`).
(Previously: inventory lacked `legend-core.js` and `controllers/legend.js`; serving allowlists were implied by R15.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `legend-core.js` and `controllers/legend.js`) exists, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, smc, tool`) — no candle data

#### Scenario: Size ceiling

- GIVEN every new module, WHEN line counts are read, THEN each is ≤ ~300 lines

#### Scenario: New modules are served

- GIVEN `legend-core` and `legend`, WHEN requested under `/market/` with a JS MIME type, THEN they are served 200 (missing from the allowlist → 404 → blank chart)
