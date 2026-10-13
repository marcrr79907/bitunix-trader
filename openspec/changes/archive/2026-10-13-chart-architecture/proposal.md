# Proposal: chart-architecture (Fase F0, issue #113)

## Intent

`chart.js` is a 1137-line IIFE with UMD-global cores and no boundaries — F1–F11 pay a growing tax on it. F0 makes it the solid base: layered ESM modules, native ESM over UMD/globals. **Zero behavior change** is the contract.

## Scope

### In Scope
- Root `package.json` `{"type":"module"}` (Node metadata only — no dep, no build).
- Cores drop UMD → `export`; `tests/js/*.test.js` `require`→`import`.
- Layers: `chart-host`, `chart-store` (UI/config state only — never candles, #68), `chart-bus`, `controllers/{indicators,history,stream,drawings,smc,toolbar}`, `main` (wiring + boot/switch). `market/config.js` exports `CONFIG`; entry `<script type="module">`.
- New `/market/` routes; preserve `window.marketChart`, re-expose `window.SmcOverlayCore`.

### Out of Scope
Behavior change; new dep/npm build; `src/`; SMC math; `legend.js`/`a11y.js` (F1); toggle persistence; UI redesign.

## Capabilities

### New Capabilities
- `chart-architecture`: layered ESM contract (seams, bus events, store boundary, test-seam re-exports, serving routes, boot/switch ordering).

### Modified Capabilities
- `market-chart`: JS delivery UMD → native ESM + `market/config.js`, no behavior change.

## Approach

Mechanical move, no rewrites. `main.js` owns all orchestration (`boot()`, `switchTo()`, guards `gen`/`drawGen`/`smcGen`, boot `.then()` order verbatim). Controllers import host/store/bus directly, emit commands on the bus (breaks the `main`↔controller cycle). `chart.js` keeps `{{ symbols|safe }}` so `/market/chart.js` contains `BTCUSDT`. Locked explore Q1–Q10.

## Affected Areas

| Area | Impact |
|------|--------|
| `market/chart.js` | Modified — monolith → thin entry |
| `market/*-core.js` | Modified — UMD → `export` |
| `market/{config,chart-store,chart-bus,chart-host,main}.js`, `controllers/*.js` | New |
| `web/market/{views,urls}.py`, `market/chart.html` | Modified — routes, module tag |
| `tests/js/*.test.js` | Modified — `import`, assertions unchanged |
| `tests/web/test_market_{ux,e2e}.py` | Read-only — frozen seam, NO edits |
| `/package.json` | New |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Behavior drift (#68, race guards) | High | Orchestration only in `main.js`; E2E `test_ws_stream_never_calls_setdata` |
| E2E seam lost (`SmcOverlayCore`, `marketChart`) | High | Re-expose in `main.js`, byte-equivalent |
| `/market/chart.js` loses `BTCUSDT` | High | Keep `{{ symbols|safe }}` literal in entry |
| JS invisible to Python patch gate | Med | 45 node + 24 E2E, no assertion edits |
| Missing module route → 404 | Med | New route-coverage UX test |

## Rollback Plan

Per slice via `git revert` — no data/migration/config/CSP change. Slice 4+ reverts to the Slice 1 state; reverting Slice 1 restores the full UMD monolith.

## Read-Only Boundary

No order surface, no owned model, no `Candle` write, no `src/` change, no new runtime dependency; CSP unchanged. JS MUST NOT recompute SMC math.

## Dependencies

Lightweight Charts v5.2.0 (pinned CDN, classic global); Node 22 CI (`node --test`) + Playwright. No new runtime dep.

## Delivery (Feature Branch Chain — 4 slices)

Base = tracker `feat/chart-architecture`; each child PR targets the previous slice.
1. ESM scaffold + config + cores + tests — ~300 lines.
2. host + store + bus — ~450.
3. controllers + main — ~500.
4. cleanup + route test + docs/ADR — ~120.

- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High

## Success Criteria

- [ ] 45 node + 24 E2E green, **no assertion edited**; boot/switch order + three guards preserved.
- [ ] `/market/chart.js` contains `BTCUSDT`; `window.SmcOverlayCore.setupMarkers` reachable.
- [ ] Modules ESM `export`; UMD gone; no new runtime dep; CSP unchanged.
- [ ] Patch gate 100%; ruff clean; route-coverage test green.
