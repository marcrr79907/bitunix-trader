# Design: chart-theme (issue #148, DEBT-7 — P3)

## Technical Approach

One resolved theme string drives two layers that read the SAME value: a pure
`theme-core.js` owns the v5 option tables, and a `data-theme` attribute on
`<html>` selects the shell token block. The host builds born-themed from
`state.theme` (resolved) and a live flip is an option-only `chart.applyOptions`
(#68, mirroring `setScaleMode`). Persistence reuses the `ChartPreference`
partial-PUT seam from chart-scales. `theme-core` imports nothing and never
throws (CT1); the shell token layer is the single source for the two
theme-aware series colors the canvas can read from CSS.

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|---|---|---|---|
| D1 | Storage semantics | Store holds the **RESOLVED** theme (`state.theme ∈ {light,dark}`); the *preference* (`light/dark/system`) lives in the toolbar `<select>` + a `main` closure var used only to save. | store the preference and resolve in the host | `build()` must be born themed from one value; the host must never read `matchMedia`. `data-theme` and `state.theme` are then trivially equal (CT2). |
| D2 | Who resolves/applies | `toolbar.js` resolves (`resolve(pref, matchMedia.matches)`), sets `document.documentElement.dataset.theme`, and emits `theme:changed {resolved, pref}`; `main` applies to the host + persists. `matchMedia` `change` listener also lives in `toolbar` (only re-applies while the select is `system`). | new `controllers/theme.js`; applier in `main` | No new controller → `CONTROLLER_ALLOWLIST` count (==7) untouched; `toolbar` already owns the F8 selects. One resolve site → the two layers can never disagree (CT2/CT3). |
| D3 | Series-color fork transport | `theme.css` gains `--chart-text` + `--chart-connector` in both token blocks; controllers read the resolved literal via `getComputedStyle(document.documentElement).getPropertyValue(...)`. `optionsFor` holds the v5 literals (v5 cannot read CSS). | a third `theme-core` export; duplicate literals in JS | CT1 freezes the two-function API. CSS is the single shell source; a cross-check test pins the CSS dark values to `optionsFor("dark")`. |
| D4 | ColorType symbol | `optionsFor` reads `LightweightCharts.ColorType.Solid` at call time (lazy `solidColorType()`; fallback string `"solid"`), never a numeric literal | magic `0/1` | Mirrors the `PriceScaleMode`-symbol discipline; the host test stubs a non-standard value so a magic number fails. |
| D5 | Theme-aware drawing text | `defaultStyle("text")` keeps `COLORS.text` (`#e6edf3`) as the dark default; `drawings.js` overrides the *creation* color from `--chart-text`. Persisted existing rows keep their stored color. | make `drawing-core` mutable/global | `drawing-core` stays pure; the fork is one controller line at each create site. |
| D6 | Select vocabulary | `chart.html` carries three static `<option>`s (light/dark/system); the server `THEMES` validates the API. | new `THEMES` JS export | Mirrors the interval control (HTML options + server `INTERVALS`); no new core export. |

## Frozen Core API — `theme-core.js` (pure, imports nothing)

```js
export function resolve(theme, prefersDark) // -> "light" | "dark"; unknown/!bool -> system behavior; never throws
export function optionsFor(resolved)        // -> v5 option object; unknown -> dark set; never throws
```

Private frozen vocab `["light","dark","system"]`; `resolve("system", b) => b ? "dark" : "light"`; missing/falsey `prefersDark` → `"light"`.

## Frozen v5 Option Shape — `optionsFor(resolved)`

```js
{
  layout: {
    background: { type: LightweightCharts.ColorType.Solid, color },  // object, SYMBOL, never flat string
    textColor,                                                       // >=4.5:1 vs color (both themes)
  },
  grid: { vertLines: { color }, horzLines: { color } },
  crosshair: {
    vertLine: { color, labelBackgroundColor },
    horzLine: { color, labelBackgroundColor },
  },
  rightPriceScale: { borderColor },
  timeScale:       { borderColor },   // host merges timeVisible:true over this
}
```

Frozen sets (alpha channel never used; v5 `applyOptions` gets full values, never `undefined`):

| Token | dark | light |
|---|---|---|
| background.color | `#0e1117` | `#ffffff` |
| layout.textColor | `#e6edf3` | `#1f2328` |
| grid color | `#2a3240` | `#d0d7de` |
| crosshair color | `#8b949e` | `#57606a` |
| crosshair labelBackgroundColor | `#1c2230` | `#eaeef2` |
| rightPriceScale/timeScale.borderColor | `#2a3240` | `#d0d7de` |
| `--chart-text` (series) | `#e6edf3` | `#1f2328` |
| `--chart-connector` (series) | `#8b949e` | `#616161` (kept) |

Contrast method: a pure `contrastRatio(hexA, hexB)` (WCAG 2.x relative-luminance) in
`tests/js/theme-core.test.js` asserts axis text vs background ≥4.5:1 for BOTH sets
(dark ≈16.0:1, light ≈16.4:1) and grid/border/connector ≥3:1 (non-text floor).

## Data Flow

    <select id="theme"> --change--> toolbar: pref
        pref + matchMedia.matches --> resolve() --> "light"|"dark"
            ├─ document.documentElement.dataset.theme = resolved   (CSS tokens flip)
            └─ bus.emit("theme:changed", {resolved, pref})
                 ├─ main: state.theme = resolved          (store; next build born themed)
                 ├─ main: host.applyTheme(resolved)        (chart.applyOptions; option-only #68)
                 └─ main: savePreference({theme: pref})    (debounced; changed field only)
    matchMedia "change" (while pref==="system") --> re-resolve --> same emit (no save)
    boot: loadPreference() -> pref(theme) -> toolbar.setTheme(pref) [data-theme + resolve]
          -> indicators.loadLayout -> build(state) [state.theme==resolved -> born themed]

## File Changes

| File | Action | Description |
|---|---|---|
| `market/theme-core.js` | Create | Pure `resolve`/`optionsFor`; frozen tables. |
| `market/chart-host.js` | Modify | Import `optionsFor`; born-themed `createChart`; `applyTheme(resolved)`; reads `state.theme`. |
| `market/chart-store.js` | Modify | `STORE_KEYS` +`theme` (9→10). |
| `market/chart-bus.js` | Modify | `EVENTS.themeChanged = "theme:changed"`. |
| `market/main.js` | Modify | seed `theme`; `loadPreference` +`theme`; `theme:changed` subscriber; `savePreference`; boot apply pre-build. |
| `market/controllers/toolbar.js` | Modify | Theme `<select>`; applier (`data-theme` + `matchMedia` listener); `setTheme`. |
| `market/controllers/drawings.js` | Modify | `--chart-text` override at text-create sites. |
| `market/controllers/smc.js` | Modify | Swing connector from `--chart-connector`. |
| `accounts/.../theme.css` | Modify | `[data-theme="light"]` block + `--chart-text`/`--chart-connector` in both. |
| `market/chart.html` | Modify | Theme `<select>` + `theme-core` `modulepreload`. |
| `market/views.py` | Modify | `MODULE_ALLOWLIST += "theme-core"`; `theme` in bodies + PUT 400. |
| `market/quotes.py` | Modify | `THEMES` vocabulary. |
| `trading/models.py` + `migrations/0011_*` | Modify | `theme` `CharField(max_length=16, default="system")`. |
| `docs/architecture/chart-modules.md` | Modify | core inventory + allowlist rows. |
| `tests/js/theme-core.test.js` | Create | `resolve`/`optionsFor` exactness + contrast. |
| `tests/js/chart-host.test.js` | Modify | Capture `createChart` args; `applyTheme` option path; ColorType symbol. |
| `tests/js/chart-store.test.js` | Modify | 10-key assertion. |
| `tests/web/test_market_api.py` | Modify | `theme` GET default/round-trip; partial PUT; 400. |
| `tests/web/test_market_e2e.py` | Modify | Toggle/reload/system; seam 8 keys. |
| `tests/web/test_market_ux.py` | Modify | explicit `theme-core` served assertion. |

## Interfaces / Contracts

Preference API (`/market/api/preference`): GET body gains `"theme"` (default `"system"`); PUT accepts partial `{"theme": "light|dark|system"}` validated against `quotes.THEMES`, invalid → `{"error":"invalid theme"}` 400 with no write; the nothing-to-apply and GET-miss bodies also carry `"theme":"system"`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (node) | `resolve` pass-through/system/unknown/no-throw; `optionsFor` exact shape + ColorType symbol + both sets; contrast ratios | `theme-core.test.js` |
| Unit (node) | `createChart` options carry `layout.background`/`textColor`; `applyTheme` calls `applyOptions` only (no `setData`/`update`); Symbol≠number | `chart-host.test.js` stub (capture args + `ColorType:{Solid:<non-standard>}`) |
| Unit (node) | `STORE_KEYS`=10 incl. `theme` | `chart-store.test.js` |
| Integration | `theme` default/round-trip; partial PUT; `{"theme":"bogus"}`→400 no-write; A≠B default | `test_market_api.py` (covers new Python → 100% patch) |
| E2E | select → `dataset.theme` flips + `window.marketChart.chart.options().layout.background.color` changes (no `setData`); reload persists; system → `emulate_media(color_scheme=...)` | Playwright DOM/options only, no image diffs |
| A11y | axis text vs background ≥4.5:1 both sets; `/impeccable` audit of the market page | node contrast helper + skill run |

## Migration / Rollout — Feature Branch Chain (2 slices, base tracker `feat/chart-theme`)

| Slice | Scope | ~Lines | Dependency / rollback |
|---|---|---|---|
| 1 | `theme-core.js` + node test; host born-themed + `applyTheme` + host test; `MODULE_ALLOWLIST` + `modulepreload`; doc row | ~175 | Autonomous (node green; chart unchanged until wired). Revert → delete core + allowlist entry; host back to defaults. |
| 2 | model + `0011`, `quotes.THEMES`, `views.api_preference` (+400), store/bus/main, toolbar control+applier, `theme.css` light block, drawings/smc fork, boot, api/e2e/ux tests, contrast, `/impeccable` | ~230–280 | Depends on 1. Revert → no persistence/shell flip; Slice 1 inert; reverted view ignores the unknown field. |

### Guard / Edge Matrix

| Edge | Handling |
|---|---|
| Live #68 | `applyTheme` = `chart.applyOptions(optionsFor(resolved))` only; no `setData`/`update`/rebuild/refetch; test asserts the series call count is unchanged |
| Rebuild born themed | `build(state)` reads `state.theme` (resolved) inside `createChart` options; no re-apply needed |
| 8-key seam | no new `window.marketChart` key; theme in `state.theme` + `data-theme`; E2E `test_shell_keeps_seam_at_eight_keys` stays green |
| System vs OS | `resolve` + `matchMedia` `change` only while pref==="system"; explicit pref ignores the OS; `data-theme` never "system" |
| Migration additive | `AddField(default="system")` only; `makemigrations --check` green |
| Host ceiling | `chart-host.js` 286/300; additions ≤14 lines (import 1, `createChart` merge ~5, `applyTheme` ~5, accessor ~1); options live in `theme-core` |
| No-dep / CSP | pure core + native `<select>`; `getComputedStyle`/`matchMedia`/dataset are same-origin ESM; CSP + `requirements.txt` unchanged |
| Vocab | JS private `["light","dark","system"]` + Python `THEMES`; per-field 400 |
| Unknown theme | `resolve` → system behavior; `optionsFor` → dark set; never throw |
| Contrast | axis ≥4.5:1 both; grid/border/connector ≥3:1; drawing text derived from `--chart-text` |
| Patch 100% | every branch (400, system fallback, unknown → dark) covered by a committed test |

## Open Questions

- Light-preference users get a brief dark first paint until `loadPreference()` resolves (no server-side `data-theme`, no inline script under CSP). Accepted for this change; note for a future no-FOUC pass.
- `drawing-core` text color is persisted per row, so existing text drawings keep their stored color across a theme flip; only newly created text drawings adopt `--chart-text`. Accepted (user content is preserved).

No blocking questions.
