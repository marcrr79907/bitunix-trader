# Tasks: chart-architecture (issue #113, Fase F0)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

All slice PRs base on the tracker `feat/chart-architecture`; merge each slice into
the tracker before branching the next. Base boundaries: PR1 base = tracker;
PR2 base = PR1 branch; PR3 base = PR2 branch; PR4 base = PR3 branch.
Behavior-equivalent, read-only refactor: NO assertion edited. JS is outside the
Python patch gate → the net is `node --test` (45) + E2E (24), plus normal
patch-100% on the Python (`views.py`/`urls.py`) lines.

## Guard/Edge Matrix

- [ ] **ESM import resolves**: every `./x.js` specifier → existing `/market/` route → 200 + JS MIME; missing route = 404 import = blank chart caught by route-coverage UX test (R15).
- [ ] **`SmcOverlayCore` re-exported**: `main.js` sets `window.SmcOverlayCore = Smc`; E2E `test_market_e2e.py:886,929` `setupMarkers` reachable, no assertion edit (R18).
- [ ] **`BTCUSDT` + `market_kline` in entry**: `/market/chart.js` still contains both literals (`test_market_ux.py:49-50`); `CONFIG` is an ESM export, no inline/window config (R16).
- [ ] **store never holds candles**: keys are exactly `{symbol,interval,indicators,params,smc,tool}`; candle data lives only in `chart-host.js` (R14).
- [ ] **#68 single-write-path**: `setData()` only in host-build + history; candle `update()` only in stream; no periodic full-series `setData`; E2E `test_ws_stream_never_calls_setdata` spy enforces (R17).
- [ ] **race guards verbatim**: `gen` (main boot/switch), `drawGen` (drawings), `smcGen` (smc) at their current ownership; boot/switch `.then()` order + `ready` timing byte-equivalent (R17).
- [ ] **no module > ~300 lines**; no new dep (`package.json` = `{"type":"module"}` metadata only, `src/` untouched); CSP unchanged (`script-src 'self' https://unpkg.com`).
- [ ] **controllers don't import `main`**: commands travel the bus; `main.js` no cycles (R14).
- [ ] Node `--test` green unchanged glob; `pytest` + ruff + `makemigrations --check` green; patch 100% on Python lines.

## Slice 1 — ESM scaffold + cores + tests + routes (PR1)

Base tracker; branch `feat/chart-architecture-esm-scaffold`; deps none. Rollback: revert `package.json`, core `export`s, test imports, allowlist views/routes, `chart.html` tag → UMD monolith intact. ~300 lines.

- [ ] 1.1 **RED** `tests/js/*.test.js`: switch `require`→`import` (`import test from "node:test"`, `import * as core from "…/<core>.js"`); assertions untouched. Acceptance: fails pre-1.3 (no ESM/`type:module`).
- [ ] 1.2 **GREEN** root `/package.json` `{"type":"module"}` (Node metadata only). Files: `package.json`. Acceptance: `.js` treated as ESM.
- [ ] 1.3 **GREEN** `chart-core.js`/`drawing-core.js`/`smc-overlay-core.js`: drop UMD shim, add native `export` of the existing `api` members. Acceptance: 1.1 green; `node --test "tests/js/**/*.test.js"` 45 pass.
- [ ] 1.4 **RED** `tests/web/test_market_ux.py`: ADD one allowlist-iterating test — each module route GET → 200 + `text/javascript`; entry still has `BTCUSDT`+`market_kline`. Acceptance: red (routes absent).
- [ ] 1.5 **GREEN** `web/market/views.py`: 2 parameterized allowlist views (`market_chart_module_js` + `market_controller_js`) serving `market/*.js` / `market/controllers/*.js`, traversal blocked, `text/javascript`. Files: `views.py`, `urls.py`. Acceptance: 1.4 green.
- [ ] 1.6 **GREEN** `chart.html`: CDN classic stays; 3 core `<script>` tags replaced by `<script type="module" src="{% url 'market_chart_js' %}">`; `chart.js` behavior identical (still IIFE-side-effect, keeps `{{ symbols|safe }}` + `CHANNELS`). Acceptance: E2E boot green; CSP test green.
- [ ] 1.7 **REFACTOR** ruff clean; patch 100% on new `views.py`/`urls.py` lines. Acceptance: Slice 1 suite green.

## Slice 2 — store + bus + host + seam (PR2)

Base PR1 branch; deps Slice 1. Rollback: revert `chart-store/bus/host`, entry delegation, seam re-export → Slice 1 state. ~450 lines.

- [ ] 2.1 **RED** `tests/js/chart-store.test.js` + `chart-bus.test.js` (`node --test`): store `get/set/subscribe` merge+emit, keys = config only (NO candles); bus `on/off/emit`. Acceptance: fails pre-2.2.
- [ ] 2.2 **GREEN** `chart-store.js` `createStore(initial)` (UI/config only) + `chart-bus.js` `createBus()`. Acceptance: 2.1 green.
- [ ] 2.3 **GREEN** `chart-host.js` (C1/C4/C7/C8): `REGISTRY`/`PANE_ORDER` exports; `build(state)`, `remove()`, accessors `getChart/getCandleSeries/getActiveSeries/getPanes/getCandles/setCandles`, `dataKey/seriesFromPayload/rsiValues/setRsi`, `subscribeClick`, `subscribeVisibleRange`; only LightweightCharts construction surface. Acceptance: host unit green.
- [ ] 2.4 **GREEN** `chart.js`: import store/bus/host, delegate build; create `window.marketChart` (8 keys) once; `import * as Smc` + `window.SmcOverlayCore = Smc`. Acceptance: 45 node + 24 E2E green, seam shape frozen.
- [ ] 2.5 **REFACTOR** no module > ~300 lines; patch 100%. Acceptance: Slice 2 suite green.

## Slice 3 — controllers + main + thin entry (PR3)

Base PR2 branch; deps Slice 2. Rollback: revert `controllers/*` + `main.js` + entry → Slice 2. ~500 lines.

- [ ] 3.1 **GREEN** `controllers/indicators.js` (C2/C14) + `controllers/toolbar.js` (C23): DI `create({store,bus,host,config})`; layout fetch/save; emit `indicator:changed` / `config:changed`; never import `main`.
- [ ] 3.2 **GREEN** `controllers/history.js` (C10/C11) + `controllers/stream.js` (C6/C9/C12/C13): history `setData`; stream `update()` only; same `(symbol,interval,limit)` window.
- [ ] 3.3 **GREEN** `controllers/drawings.js` (C15–C18, `drawGen`) + `controllers/smc.js` (C19/C20, `smcGen`): primitive attach, CRUD, tools, markers, toggles; `host`/`store` leaf imports.
- [ ] 3.4 **GREEN** `main.js` (C5/C21/C22/C24/C25): wires store/bus/host/controllers; subscribes the bus; owns `gen`, `boot()`/`switchTo()` `.then()` order + `ready` verbatim; `chart.js` (thin) keeps `CONFIG`=Django-injected `{{ symbols|safe }}`+`CHANNELS` and calls `boot(CONFIG)`. Acceptance: 45 node + 24 E2E green, no assertion edit.
- [ ] 3.5 **REFACTOR** every module ≤ ~300 lines; no controller imports `main`; patch 100%. Acceptance: Slice 3 suite green.

## Slice 4 — cleanup + route test + docs (PR4)

Base PR3 branch; deps Slice 3. Rollback: revert cleanup/ADR edits → Slice 3. ~120 lines.

- [ ] 4.1 Remove dead globals/UMD leftovers; confirm `window.ChartCore`/`DrawingCore` aliases gone, `window.SmcOverlayCore` intentionally kept.
- [ ] 4.2 `tests/web/test_market_ux.py`: finalize the module-route coverage test (every served module 200 + JS MIME).
- [ ] 4.3 ADR + `chart.html`/module comments: document ESM layout, store boundary (#68), seam; note `legend.js`/`a11y.js` deferred to F1.
- [ ] 4.4 Final verify: `pytest` green; patch 100%; `node --test "tests/js/**/*.test.js"` 45 green; ruff clean; `makemigrations --check`; CSP + `requirements.txt` unchanged; no new dep.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | Slice1 ~300, Slice2 ~450, Slice3 ~500, Slice4 ~120 → ~1370 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (scaffold+cores+tests+routes) → PR2 (store+bus+host+seam) → PR3 (controllers+main) → PR4 (cleanup+docs) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Each slice is autonomous with its own verification and trivial rollback; slice PRs
base on the tracker `feat/chart-architecture` and each child on the previous slice
(retarget/rebase if a child diff shows prior slices).
