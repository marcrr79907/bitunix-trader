# Proposal: chart-indicator-settings (issue #115, Fase F2 — Ola 2)

## Intent

Indicators render with hardcoded registry colors, fixed width, and (except
`sma_len`/`ema_len`) server-default periods. F2 adds a gear per active indicator
opening an accessible dialog to edit **color, line width, period and precision**,
persisted additively and re-rendered via the existing config-change → `rebuild()`
path (#68 preserved). No new dep, CSP strict, `src/` untouched.

## Scope

**In:** pure `indicator-settings-core.js` (frozen `{color,lineWidth,precision}`
schema + `validate`/`normalize`, defaults injected via `defaultsFor(registry,
token)`); new store `styles` slot (NOT `params`) threaded into `host.build(state)`;
additive `ChartLayout.indicators[].style` persistence (JSONField, no migration);
gear + shared `<dialog>` in `controllers/indicators.js`; `quotes.
parse_layout_indicators` + `_validate_layout_style`; allowlist/preload; node +
pytest + E2E.

**Out:** live-preview (apply-on-confirm only); new controller; `src/`/model/
migration; new runtime dep; 9th `window.marketChart` key; legend `DECIMALS`
mutation; order surface.

## Capabilities

**New:** `chart-indicator-settings` — per-token-per-chart style + editable period, persisted in the layout.
**Modified:** `chart-config` (R1/R2 — `style` preserved, validated, round-trips verbatim); `market-chart` (R14 — store gains `styles`; style threaded host-side, no candle leak); `chart-legend` (LC1 — legend MAY prefer `styles[token].precision`).

## Approach

Thread style through the existing flow: dialog → `store.styles[token]` →
`readState()` → `host.build(state)` (reads `state.styles[token]`, REGISTRY
fallback) → `addSeries({color,lineWidth})` + `applyOptions({priceFormat:{precision,
minMove:10^-precision}})`. Period persists in `params` (unchanged channel).
`saveLayout` PUTs `style`; server preserves it verbatim. Style NEVER enters
`params` — `klineUrlFrom` would leak it and the server 400s.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `market/indicator-settings-core.js` | New | Pure schema + validate/normalize |
| `market/chart-host.js` | Modified | style in `addSeries`/`build` |
| `market/chart-store.js` | Modified | `styles` key (`STORE_KEYS` 6→7) |
| `market/controllers/indicators.js` | Modified | gear + dialog + read/save |
| `market/chart.html`, `theme.css` | Modified | gear, dialog, styles |
| `market/views.py` | Modified | allowlist the new core |
| `market/quotes.py` | Modified | preserve+validate `style` (**only Python change**) |
| `tests/js/*`, `tests/web/test_market_{api,e2e}.py` | New/Modified | coverage net |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Server drops `style` on save | High | Extend parser + `_validate_layout_style`; round-trip test |
| Style leaks into kline query | Med | Dedicated `styles` slot, never `params` |
| `STORE_KEYS` frozen test breaks | Med | Deliberate 1-line test edit (R14 delta) |
| Rebuild cost per style edit | Med | Apply-on-confirm → one rebuild |
| Frozen seams / JS patch gate | Med | No new global; DOM-assert E2E; node + E2E |

## Rollback Plan

Revert in reverse: (1) UI slice — drop gear/dialog markup, CSS, E2E; (2) core
slice — revert `indicator-settings-core.js`, `chart-host`/`chart-store`
threading, `quotes.py`. No migration to reverse; stray `style` keys are ignored
by the reverted parser — no data loss.

## Read-Only Boundary

No order execution; no `src/` change; no new runtime dep; CSP unchanged; no new
`window` global (`marketChart` stays 8 keys); `Candle` read-only. Only Python
change is `quotes.py`.

## Dependencies

F0 layered ESM, F1 legend (MERGED); F3 `chart-shell` decision; Lightweight Charts
v5; Node 22 + Playwright. F3 is not a code dependency (separate files).

## Delivery (Feature Branch Chain — 2 slices)

Base = tracker `feat/chart-indicator-settings`; child PRs target the tracker.
1. **Core + persistence** — core, host/store threading, `quotes.py`, allowlist/preload, node + pytest: ~330 lines. No browser change.
2. **Dialog UI + E2E** — gear/dialog/style wiring, `chart.html`, `theme.css`, E2E, `/impeccable`: ~220 lines. Depends on Slice 1.

- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High

## Success Criteria

- [ ] Each active indicator has a gear opening a labelled `<dialog>`; valid color/width/period/precision.
- [ ] Submit writes `store.styles[token]`, triggers exactly one `rebuild()`; series `options()` reflect color/width/precision.
- [ ] PUT carries `style`; `{token,params,style}` round-trips verbatim; bad style → 400, no row written.
- [ ] `node --test` + `pytest` green; `STORE_KEYS` = 7; store holds no candles; 8 keys; no `src/` change, no new dep, CSP unchanged.
