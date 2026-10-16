# Chart module architecture

The market chart is split into layered native-ESM modules served same-origin
under `/market/`. This replaces the original 1137-line `chart.js` IIFE.
Behavior is byte-equivalent: every guard, ordering and test seam is preserved.
The split exists so each concern is independently readable and testable
(pure math in Node, wiring in the browser) without a bundler or new dependency.

## Layers

| Layer | Modules | Responsibility | May import |
|---|---|---|---|
| Pure cores | `chart-core`, `chart-types-core`, `drawing-core`, `smc-overlay-core` | Timeline/series math, chart-type vocabulary + Heikin Ashi transform, drawing geometry, SMC mapping. No DOM, no chart lib, no network. | nothing |
| State | `chart-store`, `chart-bus` | UI/config state + event bus. Store holds **config only, never candles**. | cores |
| Host | `chart-host`, `chart-host-candles` | The ONLY `LightweightCharts` construction surface. `chart-host` owns the chart/panes/scale lifecycle + the seam; `chart-host-candles` owns the candle channel (series, raw array, incremental HA state). | cores |
| Controllers | `controllers/{indicators,history,stream,drawings,smc,toolbar,draw-toolbar,object-tree,legend,drawing-interaction,preference}` | DOM, REST and stream concerns. DI factories `create({store,bus,host,config})`; `preference` is a leaf `({config})` factory for the debounced preference PUT/GET. | cores, store, bus, host — **never `main`** |
| Orchestration | `main` | Wires store/bus/host/controllers; owns `boot()`/`switchTo()` and the `gen` guard. | all of the above |
| Entry | `chart` (Django-rendered) | `export const CONFIG` (injected) + `boot(CONFIG)`. The final side effect. | `main` |

Commands travel the bus (`config:changed`, `indicator:changed`); controllers
never import `main`, so `main.js` has no circular imports.

## Rules

- **ESM native**: every module uses `import`/`export`; specifiers carry the
  explicit `.js` extension. No UMD shim, no bundler, no build step.
- **Config-in-entry**: Django injects config through the rendered entry
  `chart.js` (`export const CONFIG`). No inline script, no `window` config.
- **Single write path (#68)**: history/config → `setData`; live stream →
  `update()` only; no periodic full-series `setData`. Enforced by the E2E
  `setData` spy.
- **Single source**: JS never computes indicators or SMC — those are computed
  server-side (`src/smc/`, `web/market/quotes.py`) and only reshaped in the UI.
- **Size ceiling**: no module exceeds ~300 lines.
- **Race guards verbatim**: `gen` (main boot/switch), `drawGen` (drawings),
  `smcGen` (smc) at their current ownership.

## Module inventory and serving routes

All routes are same-origin, GET-only, JS MIME (`text/javascript`). The chart
modules are **not** auth-gated (they hold no state or secrets); they are matched
against a name allowlist — never concatenated into a path — so traversal is
impossible (unknown name → 404).

| Route | Module | Notes |
|---|---|---|
| `/market/chart.js` | `chart.js` (entry) | Django-rendered; carries `CONFIG`. |
| `/market/<name>.js` | allowlisted module | `views.MODULE_ALLOWLIST` |
| `/market/controllers/<name>.js` | allowlisted controller | `views.CONTROLLER_ALLOWLIST` |

Allowlisted modules: `chart-core`, `chart-types-core`, `chart-registry-core`,
`theme-core`, `drawing-core`, `drawing-interaction-core`, `drawing-primitive`,
`tool-icons-core`, `add-indicator-core`, `smc-overlay-core`, `legend-core`,
`indicator-settings-core`, `chart-store`, `chart-bus`, `chart-host`,
`chart-host-candles`, `main`.
Controllers: `indicators`, `history`, `stream`, `drawings`,
`drawing-interaction`, `smc`, `toolbar`, `legend`, `draw-toolbar`,
`object-tree`, `preference`.

`LightweightCharts` stays a classic CDN global (`unpkg.com`); every other
script is same-origin ESM, so CSP `script-src 'self' https://unpkg.com` is
unchanged.

## Preserved invariants

| Invariant | Where enforced |
|---|---|
| #68 single-write-path | E2E `test_ws_stream_never_calls_setdata` spy |
| Single source (no JS indicator/SMC math) | cores only reshape server payloads |
| Seam `window.marketChart` (8 keys) | E2E reads the frozen keys |
| `window.SmcOverlayCore` re-export | `main.js`; E2E `setupMarkers` calls |
| Race guards + boot/switch ordering | E2E boot/switch scenarios |
| Module routes resolve | `tests/web/test_market_ux.py` import-graph test |

## Verification net

- `node --test "tests/js/**/*.test.js"` — pure cores + controller helpers.
- `pytest -m e2e` — real browser: ESM resolves, seam shape, setData spy, SMC
  parity, boot/switch ordering.
- `tests/web/test_market_ux.py` — every served module (and every relative
  import it makes) returns 200 + JS MIME; unknown name → 404.

## Deferred to F1

`legend.js` and `a11y.js` are intentionally not created — no current behavior
maps to them.
