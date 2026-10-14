# Proposal: chart-host-extract (issue #146, DEBT-5)

## Intent

`chart-host.js` is **326 lines** — 26 over the R14 ceiling (~300), surviving via a tracked exemption (`ALLOWLIST = {"chart-host.js"}`) in `tests/web/test_module_size_guard.py`. DEBT-5 retires that exemption by extracting the candle channel into a host-layer module, restoring R14 compliance and unblocking host growth (F4/F6/F9).

## Scope

### In Scope
- **NEW** `chart-host-candles.js` — host-layer factory `createCandles(chart, chartType)` → `{getCandleSeries, getCandles, setCandles, updateCandle, remove}`. Owns `CANDLE_CTORS`, candle series, raw `candles` array, HA state (`prevHa`/`lastHa`/`lastBarTime`).
- `chart-host.js` delegates ctor + writes/teardown/accessors; ~289 lines.
- `views.py` `MODULE_ALLOWLIST` + `chart.html` `modulepreload` gain the module.
- Empty `ALLOWLIST` in the size guard + rewrite its exemption test.

### Out of Scope
Any functional change; new runtime dep; CSP change; a 9th seam key; core/controller/`main.js` edits; the 138 node + E2E behavior assertions.

## Capabilities

### New Capabilities
- None (pure refactor).

### Modified Capabilities
- None at spec level. `market-chart` R14 module inventory changes (delta at archive).

## Approach

Mechanical extraction. The module is **host-layer** (imports pure cores, receives the built `chart`) — not a pure core, since the HA-live path calls `candleSeries.setData`/`update` and mutates state, violating `chart-types-core.js`'s asserted import-free contract. `build()` replaces its candle-ctor lines with `createCandles(chart, chartType)` at the current position; writes delegate; the raw array returns by reference.

## Affected Areas

- New: `chart-host-candles.js` (~70 lines).
- Modified: `chart-host.js` (delegates; ~289 lines), `views.py` (allowlist), `chart.html` (preload), `test_module_size_guard.py` (empty allowlist + test rewrite), `market-chart/spec.md` + `docs/architecture/chart-modules.md` (archive).

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| C1 `prevHa` fix must move verbatim | High | Mechanical move; node C1 regression + E2E HA |
| `build()` re-attach order broken | Med | Construction after `createChart`, before `applyScale`; E2E |
| Raw-candle reference identity (history/legend) | Med | Module holds `let candles`, returns it directly |
| Missing route → 404; frozen 8-key seam; guard test rewrite | Med | Allowlist + preload same PR; same `candleSeries` handle; "allowlist empty" assertion |
| No new dep / CSP | Low | Same-origin ESM; CSP unchanged |

## Rollback Plan

`git revert` the PR: restores inline `chart-host.js`, removes the module, reverts allowlist/preload/guard. No data, migration, config, or CSP change.

## Dependencies

- `chart-host.js`, `chart-types-core.js` (pure HA math), `test_module_size_guard.py`.

## Read-Only Boundary

No order surface, no `src/` change, no `Candle` write, no new runtime dependency; CSP unchanged.

## Delivery (single PR)

~130–160 lines. Decision needed before apply: No · Chained PRs recommended: No · 400-line budget risk: Low

## Success Criteria

- [ ] 138 node + E2E green, **no behavior assertion edited**; C1 regression passes.
- [ ] `chart-host.js` ≤300 lines; new module serves without 404.
- [ ] `ALLOWLIST` empty; size guard passes with no exemption.
- [ ] 8-key seam unchanged; no new runtime dep; CSP unchanged.