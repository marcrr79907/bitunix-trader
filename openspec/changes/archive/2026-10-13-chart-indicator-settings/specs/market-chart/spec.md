# Delta for market-chart

Issue #115 (Fase F2). Threads the per-indicator `style` through the frozen
layered ESM boundary: the store gains a `styles` slot and the host applies style
at the sole series-construction site. R14 changes; R17 (single-write-path) and
R18 (seam) stay in force unmodified — style reuses the existing
`indicator:changed` → `rebuild()` path.

## MODIFIED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`,
`chart-store.js` (UI/config state ONLY — MUST NOT hold candle data; its vocabulary
is `symbol, interval, indicators, params, styles, smc, tool`),
`chart-bus.js`, `chart-host.js` (chart/series/panes/scales/crosshair + candle
data), `controllers/{indicators,history,stream,drawings,smc,toolbar,legend}.js`,
and `main.js` (ALL orchestration + boot/switch). No module MUST exceed ~300 lines.
Controllers MUST import host/store/bus directly but MUST NOT import `main`;
commands MUST travel the bus, so `main.js` has no circular imports. Every imported
module MUST be served same-origin under `/market/` via its Django route (core →
`MODULE_ALLOWLIST`, controller → `CONTROLLER_ALLOWLIST`).
(Previously: the store vocabulary was 6 keys with no `styles`, and the pure-core list had no `indicator-settings-core.js`.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `indicator-settings-core.js` and `controllers/legend.js`) exists, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, tool`) — no candle data

#### Scenario: Size ceiling

- GIVEN every new module, WHEN line counts are read, THEN each is ≤ ~300 lines

#### Scenario: New modules are served

- GIVEN `indicator-settings-core`, WHEN requested under `/market/` with a JS MIME type, THEN it is served 200 (missing from the allowlist → 404 → blank chart)

### Requirement: R17 — Preserved behavior invariants

The refactor MUST preserve verbatim: single-write-path (#68) — `setData()` only in
build/history, candle `update()` only in stream, no periodic full-series
`setData`; single-source — JS MUST NOT compute indicators or SMC; the
`gen`/`drawGen`/`smcGen` race guards at their ownership; and the boot/switch
`.then()` order: layout → build (reattach drawings) → drawings fetch → SMC fetch
→ history, `ready` after history, `switchTo` clearing the previous key BEFORE
reload. A style change MUST follow the config-change `rebuild()` path (build +
history `setData`); it MUST NOT introduce a second full-series `setData` writer or
mutate `DECIMALS`.
(Previously: the invariant applied to toggles/params; style is now explicitly covered.)

#### Scenario: No setData from the live path

- GIVEN the split modules, WHEN the WS live path runs, THEN no full-series `setData` is issued

#### Scenario: Guards and ordering intact

- GIVEN `switchTo(symbol, interval)`, WHEN orchestration executes, THEN `gen`/`drawGen`/`smcGen` guard their paths and the `.then()` order + `ready` timing are byte-equivalent

#### Scenario: Style change uses the rebuild path

- GIVEN a confirmed style edit
- WHEN it applies
- THEN the chart follows `indicator:changed` → `rebuild()` (build + history `setData`) and no live-path full `setData` occurs

#### Scenario: Style never leaks into the kline query

- GIVEN `styles[token]` populated
- WHEN the kline URL is serialized
- THEN no `color`/`lineWidth`/`precision` key is appended (style is not in `params`)
