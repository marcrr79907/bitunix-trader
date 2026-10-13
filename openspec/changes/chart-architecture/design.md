# Design: chart-architecture (issue #113, Fase F0)

## Technical Approach

Comportamiento-equivalent split of the 1137-line `chart.js` IIFE into layered native-ESM
modules. No rewrites: move code, keep every guard, ordering and seam byte-equivalent.
`main.js` owns ALL orchestration (`boot`/`switchTo` + `gen`/`drawGen`/`smcGen`); controllers
are leaf modules that receive `{store, bus, host, config}` factories and emit commands on the
bus; the bus breaks the `main`↔controller cycle. Cores drop UMD for `export`; `package.json
{"type":"module"}` (Node metadata only) enables `import` in `node --test`. Frozen contracts:
45 node + 24 E2E assertions unchanged.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| CONFIG location | **Entry `chart.js` owns `CONFIG`** (Django-rendered); no `config.js` | separate `market/config.js` | `test_market_ux.py:49-50` asserts BOTH `BTCUSDT` AND `market_kline` in `/market/chart.js`. A separate config module forces duplication and adds a route with no consumer benefit. One rendered module = single source. |
| Module serving | **2 parameterized allowlist views** + existing 4 routes | one view per module; bundle | 10 new modules × dedicated views = boilerplate. Allowlist blocks traversal; keeps `text/javascript`; no build step. |
| Controller deps | DI factory `create({store,bus,host,config})` | controllers `import` main/config | Never import `main` (cycle) nor `config` (not a module). Explicit deps, leaf graph. |
| REGISTRY/PANE_ORDER | live in `chart-host.js` (exports) | own `registry.js` | Single consumer boundary (build + indicators default). YAGNI a file. |
| legend.js / a11y.js | **defer (F1)** | create stubs | No behavior maps to them. |

## Module Inventory (frozen) — 25 blocks → destination

| File (served under `/market/`) | Blocks | Responsibility | Public exports |
|---|---|---|---|
| `chart.js` (entry, Django-rendered) | C0, C21(trigger), C25 | `CONFIG` + `boot(CONFIG)` | — (side-effect) |
| `main.js` | C5, C21, C22, C24 | seam, wiring, `boot`/`switchTo` | `boot(config)` |
| `chart-host.js` | C1, C4, C7, C8 | v5 encapsulation; `REGISTRY`,`PANE_ORDER` | factory → host API |
| `chart-store.js` | C3 | observable UI/config state | `createStore(initial)` |
| `chart-bus.js` | new | event emitter | `createBus()` |
| `chart-core.js` | — | pure (UMD→`export`) | named |
| `drawing-core.js` | — | pure (UMD→`export`) | named |
| `smc-overlay-core.js` | — | pure (UMD→`export`) | named |
| `controllers/indicators.js` | C2, C14 | panel DOM↔state, layout REST, rebuild emit | `create(deps)` |
| `controllers/history.js` | C10, C11 | `klineUrl`,`fetchHistory`,`loadOlder`,`applyHistory` | `create(deps)` |
| `controllers/stream.js` | C6, C9, C12, C13 | WS connect/ping/backoff, `onPush`, close refresh | `create(deps)` |
| `controllers/drawings.js` | C15–C18 | primitives, CRUD, tools, click | `create(deps)` |
| `controllers/smc.js` | C19, C20 | fetch, primitive, markers, toggles | `create(deps)` |
| `controllers/toolbar.js` | C23 | pair buttons + interval select | `create(deps)` |

## Data Flow

    chart.html ──▶ <script type=module src=market/chart.js>
    chart.js ──boot(CONFIG)──▶ main
    main ──creates──▶ store, bus, host, controllers(deps)
    toolbar/indicators ──emit config:changed|indicator:changed──▶ bus ──▶ main.switchTo/rebuild
    history ──setData──▶ host            stream ──update──▶ host  (single write path #68)
    host/drawings/smc ──write──▶ window.marketChart   (seam)

## Interfaces / Contracts

```js
// chart-store.js — UI/config STATE ONLY; candles NEVER enter (#68)
// state = { symbol, interval, indicators:[token], params:{token:{k:n}}, smc:{family:bool}, tool }
export function createStore(initial) {         // get(): state{same ref}; set(patch): merges+emits; subscribe(fn): unsub
  return { get, set, subscribe };
}

// chart-bus.js — no lib
export function createBus() { return { on(ev,fn), off(ev,fn), emit(ev,payload) }; }

// FROZEN events (commands main subscribes): config:changed {symbol,interval}; indicator:changed
// notifications: layout:loaded {indicators,params}; chart:built {chart,candleSeries,panes};
//   history:loaded {candles}; candle:closed {time}; drawings:changed {rows};
//   smc:loaded {payload}; smc:toggles {families}; ready

// chart-host.js — the ONLY LightweightCharts construction surface
// build(state) -> {chart,candleSeries,activeSeries}; remove(); getChart/getCandleSeries/
// getActiveSeries/getPanes/getCandles/setCandles; dataKey(place,pane,key);
// seriesFromPayload(desc,payload); rsiValues/setRsi; subscribeClick(fn); subscribeVisibleRange(fn)

// CONFIG shape (entry, Django-rendered before serve)
// { symbols: ["BTCUSDT",...], wsUrl: "wss://fapi.bitunix.com/public/",
//   historyLimit: 200, channels: {"1m":"market_kline_1min",...},
//   urls: {kline:"/market/api/kline", smc:"/market/api/smc", layout:"/market/api/layout", drawings:"/market/api/drawings"} }

// Seam re-exposure in main.js: window.marketChart = {8 keys};
//   main imports * as Smc → window.SmcOverlayCore = Smc  (E2E reads it; the ONE sanctioned global)
```

Entry `chart.js` keeps the literal `{{ symbols|safe }}` and the `CHANNELS` map so the UX test
passes; `views.chart_js` stays `render(...).content` + `text/javascript`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| JS unit | 3 cores | `require`→`import` (`import * as core from "..."`); **assertions untouched**; `node --test` glob unchanged |
| UX (PY) | module routes 200 + `text/javascript`; entry still has `BTCUSDT`+`market_kline` | **ADD** one test iterating the module allowlist (adding tests is allowed; editing is not) |
| E2E (PY) | seam, boot/switch order, `setData` spy, SMC parity | **unchanged, no edits** |

## Delivery (Feature Branch Chain — base = tracker `feat/chart-architecture`)

| Slice | Scope | Lines | Rollback boundary |
|---|---|---|---|
| 1 | `package.json`; cores UMD→`export`; tests `require`→`import`; entry keeps symbols+channels (behavior identical); module routes/views | ~300 | revert → UMD monolith intact |
| 2 | `chart-store`, `chart-bus`, `chart-host`; entry delegates; seam + `window.SmcOverlayCore` re-export | ~450 | revert → Slice 1 state |
| 3 | `controllers/*` + `main.js`; entry = thin CONFIG+`boot` | ~500 | revert → Slice 2 |
| 4 | dead-code removal, route-coverage test, ADR/comments | ~120 | revert → Slice 3 |

### Guard / Edge Matrix

| Edge | Handling |
|---|---|
| #68 single-write-path | `setData` only in history/build; `update()` only in stream; E2E spy enforces |
| single-source (no JS SMC math) | cores only reshape; smc controller never computes |
| seam keys (8) | `main.js` creates once; host/drawings/smc write in place; timing byte-equivalent |
| race guards | `gen` (main boot/switch), `drawGen` (drawings), `smcGen` (smc) move verbatim, same ownership |
| ESM import resolution | every `./x.js` → existing route; new modules get allowlist routes; route-coverage test |
| explicit `.js` + MIME | specifiers carry `.js`; views return `text/javascript`; CSP `script-src 'self'` unchanged |
| `SmcOverlayCore` | re-exported in `main.js` (E2E lines 886,929) |
| no new dep | `package.json` metadata only; `src/` untouched; `pip-audit` unaffected |

## Migration / Rollout

No migration, model, flag, or CSP change. Per-slice `git revert`; reverting Slice 1 restores the
UMD monolith. JS is Python-coverage-invisible → safety net = 45 node + 24 E2E.

## Open Questions

None blocking. Design refines explore Q3/Q4: config merged into the entry (frozen-token proof
above); 2 allowlist views instead of one-per-module.
