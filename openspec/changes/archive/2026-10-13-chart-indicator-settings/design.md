# Design: chart-indicator-settings (issue #115, Fase F2 — Ola 2)

## Technical Approach

Thread per-indicator presentation style through the **existing** config-change path,
never a new one: gear → `<dialog>` → `store.styles[token]` → `readState()` →
`host.build(state)` → `addSeries({color,lineWidth})` + `applyOptions({priceFormat})`,
with persistence carried additively on `indicators[].style` (JSONField, no migration).
Two load-bearing facts from explore.md drive the whole design: (1) `quotes.parse_layout_indicators`
silently drops `style` (quotes.py:303) — the only Python change; (2) `history.klineUrlFrom`
flattens **every** `params[token]` key into the kline query, so `style` MUST live in a
dedicated store slot, never under `params`. Core is a pure `import`-nothing module.

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|---|---|---|---|
| D1 | Style channel | New store key `styles` (top-level) | nest under `params` | `klineUrlFrom` would leak `color` into `/api/kline`; server `_parse_params` 400s. Explore rejected B. |
| D2 | Core API names | Follow the **delta spec** (`FIELDS, TOKENS, validate, normalize, defaultsFor`), not the prompt's illustrative `normalizeStyle/validateStyle` | prompt's `e.g.` names | Spec is ratified; the prompt explicitly says "e.g.". `clamp` stays **internal** (spec: "export exactly"). |
| D3 | Style shape | `{color,lineWidth,precision}` — all optional | store period in style | Period persists in `params` (unchanged channel); keeps style presentation-only. |
| D4 | Apply point | `host.build(state)` reads `state.styles[token]`, REGISTRY fallback | `series.applyOptions` live on dialog input | build is the SOLE series-construction site + #68 config path; live-preview would need a non-sanctioned write path. |
| D5 | Precision | series `priceFormat:{precision,minMove:10**-precision}` | mutate `legend-core.DECIMALS` | Legend's frozen map (LC1) stays; axis/crosshair only. Legend preference is optional/read-only. |
| D6 | Gear/dialog home | extend `controllers/indicators.js` (135 lines) | new controller | It already owns panel DOM + `saveLayout` + `readState`; no new allowlist entry, no second save path. |
| D7 | Save trigger | apply-on-confirm → one `indicator:changed` + `saveLayout()` | per-input live | one rebuild per submit (#68/perf). |
| D8 | Server validation | `_validate_layout_style(token, style)` mirroring `_validate_layout_params`; verbatim, no defaults | reuse params validator | round-trips the user shape; unknown key/range → `ValueError` → 400 before write. |

## Frozen Core API — `indicator-settings-core.js` (pure, imports nothing)

```js
export const FIELDS  = Object.freeze({
  color:     { type: "color" },
  lineWidth: { type: "int", min: 1, max: 4 },
  precision: { type: "int", min: 0, max: 8 },
});
export const TOKENS  = Object.freeze([...]);            // = chart-host REGISTRY keys
export function defaultsFor(registry, token)            // {color:firstSeriesColor(fallback "#2962ff"), lineWidth:1, precision:2}
export function normalize(token, raw, defaults)         // -> {color,lineWidth,precision}; never throws
export function validate(token, raw)                    // -> {ok:bool, errors:[...]}; never throws
// internal (NOT exported): clamp(n,lo,hi,fallback)
```
Unknown token → `defaultsFor` neutral color, no throw. Malformed color (`red`, `#zzz`) →
default. Out-of-range → clamped. Unknown key → dropped. `TOKENS` is data, not an import.

## Frozen Style Shape

```json
{ "color": "#2962ff", "lineWidth": 1, "precision": 2 }
```
Stored per-entry as `indicators[].style`; all keys optional. **Host apply (exact v5):**
`chart.addSeries(Ctor, {color:{...style}.color ?? s.color, lineWidth: style.lineWidth ?? 1}, paneIndex)`
then `series.applyOptions({priceFormat:{precision:p, minMove: Math.pow(10,-p)}})`.

## Frozen Dialog DOM (`chart.html`)

```html
<button type="button" class="indicator-settings" data-token="sma"
        aria-haspopup="dialog" aria-label="SMA settings">⚙</button>
<dialog id="indicator-settings-dialog" aria-label="Indicator settings">
  <form method="dialog">
    <label for="is-color">Color</label><input id="is-color" type="color">
    <label for="is-width">Line width</label><input id="is-width" type="number" min="1" max="4">
    <label for="is-period">Period</label><input id="is-period" type="number" min="1">
    <label for="is-precision">Precision</label><input id="is-precision" type="number" min="0" max="8">
    <button type="submit" value="ok">Apply</button>
    <button type="submit" value="cancel">Cancel</button>
  </form>
</dialog>
```
Gear lives inside the existing `.indicators` fieldset per active toggle. Native
focus-trap + Escape; `close` handler applies on `returnValue==="ok"` (drawings precedent).
Period input hidden for tokens without a known param.

## Data Flow

    gear click ─▶ populate dialog (styles[token] + params[token])
      └─ submit "ok" ─▶ store.set({styles}) ─▶ bus "indicator:changed" ─▶ main.rebuild()
                          │                                                    ├─ host.build(state): styles[token] -> color/lineWidth/priceFormat
                          └─ indicators.saveLayout() ─▶ PUT {token,params,style} │
    loadLayout ─▶ body.indicators[].style ─▶ state.styles                 └─ history.fetchHistory() (setData; #68)

## File Changes

| File | Action | Description |
|---|---|---|
| `market/indicator-settings-core.js` | Create | Pure schema/normalize/validate/defaultsFor. |
| `market/chart-store.js` | Modify | `STORE_KEYS` +`styles` (6→7). |
| `market/chart-host.js` | Modify | `build`/`addSeries` read `state.styles[token]`; color/lineWidth/priceFormat. |
| `market/controllers/indicators.js` | Modify | gear + dialog + style read/save; `buildIndicators` 3rd `styles` arg; `loadLayout` applies style. |
| `market/chart.html` | Modify | gear buttons + dialog markup + preload core. |
| `market/views.py` | Modify | `MODULE_ALLOWLIST += "indicator-settings-core"`. |
| `market/quotes.py` | Modify | keep+validate `style` in `parse_layout_indicators`; `_validate_layout_style`. |
| `registration/theme.css` | Modify | gear + dialog styling. |
| `tests/js/indicator-settings-core.test.js` | Create | normalize/clamp/defaults exactness. |
| `tests/js/chart-store.test.js` | Modify | 7-key assertion. |
| `tests/web/test_market_api.py` | Modify | style round-trip + 400. |
| `tests/web/test_market_e2e.py` | Modify | gear/dialog/color/PUT (DOM-only, no edits to existing). |

## State shape (store)

`styles = { token: {color,lineWidth,precision} }`; `set` shallow-merges per top-level key
(unchanged store semantics). Confirmed **no leak**: `klineUrlFrom` iterates `state.params`
only, `buildIndicators` emits `style` from the separate `styles` arg.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (node) | `normalize`/`validate`/`defaultsFor` exactness; clamp/substitute/drop; never throws | `node --test tests/js/indicator-settings-core.test.js` |
| Unit (node) | STORE_KEYS=7; `buildIndicators` emits `style`; `klineUrlFrom` still has no style key | `tests/js/chart-store.test.js`, `chart-controllers.test.js` |
| Integration (pytest) | PUT `{token,params,style}` round-trips verbatim; bad style → 400 no write; A≠B | extend `test_market_api.py` (covers the only new Python lines → 100% patch gate) |
| E2E | gear opens dialog; change color → `series.options().color` updates; persists across reload; 8 seam keys; Escape closes | DOM/computed-style via Playwright (`/impeccable`) |

## Delivery — Feature Branch Chain (2 slices, all PRs base on tracker `feat/chart-indicator-settings`)

| Slice | Scope | ~Lines | Dependency / rollback |
|---|---|---|---|
| 1 | core, `chart-store` `styles`, `chart-host` threading, `quotes.py` + `_validate_layout_style`, allowlist/preload, node + pytest | ~330 | Autonomous (node+pytest green; chart still renders registry defaults). Revert → no core/threading/persistence; chart unchanged. |
| 2 | `controllers/indicators.js` gear/dialog/wiring, `chart.html`, `theme.css`, E2E, `/impeccable` | ~220 | Depends on Slice 1. Revert → no gear/dialog; Slice 1 still round-trips style. |

### Guard / Edge Matrix

| Edge | Handling |
|---|---|
| style ≠ params / no kline leak | dedicated `styles` slot; test asserts no style key in `klineUrlFrom` |
| server keeps style round-trip | `parse_layout_indicators` preserves+validates; pytest verbatim test |
| no migration | JSONField additive; `makemigrations --check` green |
| rebuild #68 | style edit → `indicator:changed` → one `rebuild()`/`setData`; E2E `setData` spy untouched |
| frozen seams | no 9th `window.marketChart` key; DOM-only asserts |
| allowlist | core added; `test_import_graph_routes_resolve` fails loudly if missed |
| a11y | native `<dialog>` focus-trap + Esc; labelled inputs; visible gear focus |
| no-new-dep / CSP | native `<input type=color>`/`<dialog>`, `theme.css`; `requirements.txt` + CSP unchanged |
| inactive token | style stored, ignored at render, no error |
| responsive | dialog + gear no horizontal overflow at 375px |

## Migration / Rollout

No migration, model, flag, or CSP change; stray `style` keys are ignored by the reverted
parser (no data loss). Per-slice `git revert`.

## Open Questions

None blocking. Locks explore Q1 (per-chart scope), Q2 (precision → priceFormat, **legend
`DECIMALS` untouched**), Q4 (period edited in dialog, persisted in `params`), Q6 (`styles`
key), Q8 (apply-on-confirm). D2 resolves the prompt-vs-spec naming in favor of the delta spec.
