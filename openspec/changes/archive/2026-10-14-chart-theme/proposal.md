# Proposal: chart-theme (issue #148, DEBT-7 — P3)

## Intent

Fix smc-overlay W1: the LightweightCharts v5 canvas renders white inside dark
chrome, and no light mode exists. Add a user-global, persisted `theme`
(light/dark/system) driving BOTH the chart canvas and the shell CSS from one
source. Chart-only would invert the mismatch and make drawing text `#e6edf3`
(`drawing-core.js:22`) invisible on light, so the theme owns the shell.

## Scope

**In:** pure `theme-core.js` (`resolve(theme, prefersDark)` + `optionsFor(resolved)`);
one `data-theme` on `<html>` selecting dark `:root` vs authored
`[data-theme="light"]` tokens; v5 option-only live toggle via `chart.applyOptions`
(#68); `ChartPreference.theme` (`"system"` default, additive migration `0011`);
`/market/api/preference` partial PUT gains `theme` (+400 invalid); boot applies
pre-build; theme-aware drawing text + swing connector; node/pytest/E2E + a11y
contrast tests.

**Out:** light fork of series/indicator hues (kept theme-independent pending
contrast check); per-`(symbol,interval)` scope; a new controller; a 9th
`window.marketChart` key; `src/`/new dep/CSP.

## Capabilities

**New:** `chart-theme` — theme resolution, `data-theme` transport, persisted user-global.
**Modified:** `market-chart` (store gains `theme`; born-themed `build()`; option-only toggle), `chart-shell` (theme control, no new controller), `design-system` (`[data-theme="light"]` tokens).

## Approach

`theme-core.js` (imports nothing) exposes `resolve`/`optionsFor`, keeping
`chart-host.js` ≤300 (286 today). Host reads `state.theme` in `build()` → chart
born themed; a live flip is option-only `chart.applyOptions({layout, grid,
crosshair, rightPriceScale, timeScale})`, mirroring `setScaleMode`. `theme.css`
gains `[data-theme="light"]` (~15 vars); a thin applier in
`controllers/toolbar.js` sets `document.documentElement.dataset.theme`, reads
`matchMedia('(prefers-color-scheme: dark)')` + `change`, and calls the host.
`theme-core.js` joins `MODULE_ALLOWLIST` + `modulepreload`. Persistence mirrors
chart-scales: `CharField(default="system")` + `THEMES` vocabulary.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `market/theme-core.js` | New | Pure `resolve`/`optionsFor` |
| `market/chart-host.js`, `chart-store.js` | Modified | Themed build, `+theme` |
| `market/controllers/toolbar.js`, `main.js` | Modified | Control + applier + boot |
| `market/{views,quotes}.py` | Modified | Pref field, `THEMES`, 400 |
| `web/trading/models.py` + `migrations/0011_*` | Modified | Additive column |
| `web/accounts/.../theme.css` | Modified | Light token set |
| `market/chart.html` | Modified | `modulepreload` |
| `tests/{js,web}/*` | New/Modified | Coverage net |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| v5 option shape drift | Med | `{type: ColorType.Solid, color}`; symbol, not magic number |
| Light contrast failures | Med | Fork drawing text + swing connector; ≥4.5:1 test |
| Frozen 8-key seam | Low | Theme in store/data-theme, never the seam |
| Non-additive migration | Low | `AddField` + default; `makemigrations --check` green |
| Host 300-line ceiling | Med | Options built in `theme-core`; host stays thin |
| Patch 100% gate | Med | Test every branch incl. 400 + system fallback |
| WS E2E flake (DEBT-8) | Med | Decouple theme E2E from WS; `-p no:randomly` |

## Rollback Plan

Revert top-down: (3) drop `theme` field + view branches + `0011`; (2) remove
applier + control, restore hardcoded dark `theme.css`, drop `data-theme`, remove
`state.theme`/`applyOptions` + `modulepreload`; (1) delete `theme-core.js` + test
+ allowlist entry. No data loss: reverted view ignores the unknown field. Slice 1
can't revert alone (2 depends on it).

## Dependencies

`theme.css` tokens, `chart-host.js` build seam, `ChartPreference`/`quotes.py`
vocabulary precedent. Lightweight Charts v5.2.0, Node 22, Playwright. No new
runtime dep; CSP unchanged.

## Success Criteria

- [ ] `data-theme` flips both tokens and canvas; canvas/chrome match both themes.
- [ ] Live toggle option-only (`applyOptions`, no `setData`/rebuild); rebuild born themed.
- [ ] "Sistema" follows `matchMedia` + `change`.
- [ ] `theme` round-trips via partial PUT; invalid → 400 no write; boot pre-build.
- [ ] Axis text ≥4.5:1 both themes; drawing text + swing connector theme-aware.
- [ ] `0011` additive; patch 100%; seam 8 keys; host ≤300; no `src/`; no dep; CSP unchanged.

## Read-Only Boundary

No order execution; no `src/`; no new dep; CSP unchanged; no new `window` global;
`Candle` read-only. Python limited to `views.py`, `quotes.py`, model + migration, tests.

## Delivery (Feature Branch Chain — 2 slices)

Base = tracker `feat/chart-theme`; child PRs target the tracker.
1. **Theme engine + host canvas** — `theme-core.js` + node test, themed `build()` + `applyOptions`, allowlist + `modulepreload`, host option-shape test.
2. **Persistence + shell coherence + UI + a11y + E2E** — `theme` field + `0011`, preference API (+400), control + applier, light tokens + `[data-theme]`, boot restore, pytest round-trip, E2E toggle/reload/system, contrast check, `/impeccable`. Depends on 1.

- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: Medium
