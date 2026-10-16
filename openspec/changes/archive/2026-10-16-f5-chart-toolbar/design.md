# Design: f5-chart-toolbar (issue #118, Fase F5)

## Technical Approach

Layered F0 extension (docs/architecture/chart-modules.md). Two pure cores are
extracted/created first, then two thin DI controllers render from them. Every
new module ≤300 (`test_module_size_guard.py`, empty allowlist). Persistence reuses
existing channels: drawings ride `drawing:changed` (partial PUT already built at
`drawings.js:123-126`); indicators add exactly ONE new bus event
`indicator:visibility` routed by `main` to an option-only `host.setSeriesVisible`
(mirrors `scale:changed`, `main.js:179-182`). #68 held: visibility is
`applyOptions`, never `setData`.

Confirmed baseline line counts (`wc -l`): `smc.js=300` (untouched), `chart-host=297`,
`main=283`, `drawings=261`, `indicators=261`.

## Architecture Decisions

| # | Decision | Choice | Alternatives rejected | Rationale |
|---|---|---|---|---|
| D1 | Registry home | New pure `chart-registry-core.js` holds `REGISTRY`/`PANE_ORDER`/`SCALE_MODES`, moved verbatim from `chart-host.js:16-67` | leave in host; new "host-registry" module | Host is AT 297 with no room for `setSeriesVisible`; two importers already exist (`indicators.js:9`, `chart-host.js`) |
| D2 | Toolbar/tree as controllers | `controllers/draw-toolbar.js` + `controllers/object-tree.js`, DI `create({store,bus,config,...})` | fold into `toolbar.js`/`drawings.js` | `toolbar.js` is a top-bar controller; drawings/indicators are at 261. Capability shape (proposal §Fork 4) |
| D3 | Tool command path | `draw-toolbar` writes `store.tool`; `drawings` reacts via `store.subscribe` | new `tool:changed` bus event | `EVENTS` gains exactly one entry total (R20); store is the documented UI-state home (`chart-store.js:13-24`) |
| D4 | Indicator visibility home | 11th `STORE_KEYS` slot `indicatorVisible:{token:bool}` | closure + bespoke publish | Tree needs a reactive source; store is the frozen vocabulary's home (R14 delta) |
| D5 | Indicator visibility command | New `indicator:visibility` bus event → `main` → `host.setSeriesVisible` | ride `indicator:changed` | `indicator:changed` is the rebuild/setData path; visibility must NOT re-fetch (#68) |
| D6 | Indicator render | Option-only `series.applyOptions({visible})` | excludes hidden from `state.indicators` + rebuild | TradingView-faithful, no recompute; forces D1 extraction |
| D7 | Drawings persistence | Reuse `drawing:changed` with `visible`/`locked` + `persist:true` | new event | `drawings.js:113-127` already builds the partial PUT |
| D8 | Tree scope | Active-only indicators (layout membership) | all-9 registry | TradingView-faithful; all-9 needs a "+add" affordance out of scope |
| D9 | Icons | JS-built inline SVG string from the pure core, `innerHTML` on a button | `<img>` sprite; inline handler | CSP-safe (local constant, no event attrs); no new asset route |
| D10 | Tree→gear | `createObjectTree({...,onIndicatorSettings})` callback → `indicators.openSettings` | new bus event | `toolbar.js` `onTheme` callback precedent; keeps R20 at one new event |
| D11 | Preference helpers | Stay in `main.js` (projected ≈293) | extract now | 293 < 300; extraction is the documented contingency if apply reveals >300 |

## Module Decomposition & Line Budget

| File | Action | From → To | What moves / changes |
|---|---|---|---|
| `market/chart-registry-core.js` | **New** | — → ~60 | `REGISTRY` (`chart-host.js:16-56`), `PANE_ORDER` (`59`), `SCALE_MODES` (`63-67`) + header |
| `market/tool-icons-core.js` | **New** | — → ~110 | `TOOL_GROUPS` (lines→{hline,trendline}, fib, shapes→{rect}, text), `TREE_GROUPS`, `iconFor(kind)`→SVG string, `groupLabel` |
| `controllers/draw-toolbar.js` | **New** | — → ~150 | vertical `role=toolbar`, renders groups from core, sets `store.tool`, `store.subscribe` active state, pan/cancel, Up/Down/Home/End roving focus |
| `controllers/object-tree.js` | **New** | — → ~230 | `role=tree`, subscribes `drawings:changed`+`layout:loaded`+`store.subscribe`, per-row eye/lock/delete/select, keyboard tree nav |
| `chart-host.js` | Modify | 297 → ≈259 | −52 (registry block 16-67) + import core + `setSeriesVisible` (~8) + build() applies initial visibility (~5) |
| `controllers/drawings.js` | Modify | 261 → ≈241 | −`renderDrawingList` (32-46) −tool/cancel DOM wiring (19, 218-232) +`store.subscribe` tool reset (~7) +visible/locked apply+PUT (~6) |
| `controllers/indicators.js` | Modify | 261 → ≈233 | −`readIndicators` DOM (49-56) −`readParams` DOM (37-46) −`applyLayout` DOM (95-110) −gear/toggle DOM wiring (77-85, 241-246) +`openSettings` (~12) +`buildIndicators` visible arg (~4) +`loadLayout` visible→store (~5) |
| `main.js` | Modify | 283 → ≈293 | +2 imports, +2 creates, +1 store key, +`indicator:visibility` route (~5) |
| `drawing-core.js` | Modify | 158 → ≈160 | `fromApi` carries `visible`/`locked` (`35-43`) |
| `drawing-primitive.js` | Modify | 126 → ≈130 | `renderShape` early-return when `visible===false`; `autoscaleInfo` null when hidden |
| `controllers/drawing-interaction.js` | Modify | 217 → ≈219 | filter `locked` rows from `grabHandle` (`87`, `164`) |
| `chart-store.js` | Modify | 58 → ≈59 | 11th `STORE_KEYS` `indicatorVisible` |
| `chart-bus.js` | Modify | 50 → ≈51 | `indicatorVisibility:"indicator:visibility"` |
| `chart.html` | Modify | 154 → ~140 | replace indicators fieldset (46-68) + drawings fieldset/list (80-89) with `#draw-tools` + `#object-tree`; +2 controllers and +2 modulepreload |
| `views.py` | Modify | 552 → ~572 | allowlists `MODULE +2`, `CONTROLLER +2`; flag parse/persist in POST/PUT/GET |
| `quotes.py` | Modify | 739 → ~758 | `parse_drawing` flag validation; `parse_layout_indicators` `visible` |
| `models.py` + `migrations/0014` | Modify/New | +2 fields / ~24 | `visible`/`locked` additive `AddField` |

`smc.js` is untouched (AT 300). `main.js` projected 293 — WATCHED; contingency D11
(`controllers/preference.js`, ~50 lines: `csrfToken` 184-187, `savePreference`
189-208, `loadPreference` 210-237) is pre-specified if apply crosses 300.

## Layer Compliance

| New module | F0 layer | Allowed imports |
|---|---|---|
| `chart-registry-core.js` | Pure core | nothing |
| `tool-icons-core.js` | Pure core | nothing |
| `controllers/draw-toolbar.js` | Controller | cores, store, bus — **never `main`** |
| `controllers/object-tree.js` | Controller | cores, store, bus — **never `main`** |

`draw-toolbar` DI: `create({store,bus,config})`. `object-tree` DI:
`create({store,bus,config,onIndicatorSettings})`. `chart-host` continues to import
cores only; `indicators.js:9` switches its `REGISTRY` import from `chart-host` to
`chart-registry-core`.

## Data Flow

**(a) Drawing eye/lock toggle → persist** (reuses `drawing:changed`, no new event):

    object-tree row eye/lock click
      └─▶ bus.emit("drawing:changed", {id, visible|locked, persist:true})
            └─▶ drawings.js handler: row.visible/locked = …; requestUpdate()
                  ├─▶ drawing-primitive: renderShape early-return if !visible
                  │     autoscaleInfo → null when hidden
                  └─▶ body {visible|locked}; PUT /market/api/drawings/<id>
                        └─▶ _put_drawing: parse flags (bool | 400) → save
        tree re-renders on drawings:changed (rows carry flags via fromApi)

**(b) Indicator eye toggle → option-only** (#68):

    object-tree indicator eye
      └─▶ store.set({indicatorVisible:{[token]:v}})
      └─▶ bus.emit("indicator:visibility", {token, visible})
            └─▶ main: host.setSeriesVisible(token, visible)
                  └─▶ activeSeries[token].series.applyOptions({visible})   (no setData)
            └─▶ indicators.saveLayout()  → layout entry carries visible:false

**(c) Object tree re-render sources**:

    drawings:changed ─┐
    layout:loaded    ─┼─▶ object-tree.render()
    store.subscribe  ─┘    (grouped role=tree; drawings rows + active-only indicators)

**(d) `readIndicators()` re-sourcing**: the DOM checkbox list moves to the tree, so
`readIndicators`/`readParams` DOM readers are deleted. Membership = `store.indicators`;
params = `store.params`. `main.js:36` seeds `indicators: DEFAULT_INDICATORS.slice(),
params:{}`; `loadLayout` writes `state.indicators`/`state.params` directly (already
does, `indicators.js:124`); `readState` returns store values. Indicator presence
change emits `indicator:changed` (rebuild); gear opens the dialog via
`onIndicatorSettings` → `indicators.openSettings(token)`.

## Store & Bus Contract Changes

- `STORE_KEYS` 10→11 (`chart-store.js:13-24`): add `"indicatorVisible"`; remains
  config-only (#68). No current subscriber reads it excepts the new tree.
- `EVENTS` gains exactly ONE key: `indicatorVisibility:"indicator:visibility"`
  (`chart-bus.js:8-20`). Drawings reuse `drawing:changed`; tool uses `store.tool`.
- Existing subscribers unaffected: `drawing:changed`/`drawings:changed`,
  `layout:loaded`, `scale:changed`, `indicator:changed` semantics unchanged;
  `drawings.js`'s handler only gains two optional fields.
- `window.marketChart` stays exactly 8 keys (`main.js:51-60`, R18): the tree
  asserts via DOM + bus + captured PUT, never a new seam key.

## Interfaces / Contracts

```js
// chart-registry-core.js
export const REGISTRY;      // token -> {place, series|pane}
export const PANE_ORDER;
export const SCALE_MODES;   // {linear:"Normal", log:"Logarithmic", percentage:"Percentage"}

// tool-icons-core.js
export const TOOL_GROUPS;   // [{label, kinds:[...]}] e.g. Lines:[hline,trendline]
export function iconFor(kind);      // -> inline-SVG string (no event attrs)
export function groupLabel(group);

// chart-host.js  (option-only; no rebuild, no setData)
function setSeriesVisible(token, visible) {          // ~8 lines
  activeSeries.forEach(function (a) {
    if (a.token === token && a.series.applyOptions)
      a.series.applyOptions({ visible: !!visible });
  });
}

// drawing-core.js
function fromApi(row) {
  if (!row || DRAWING_KINDS.indexOf(row.kind) === -1) return null;
  return { id: row.id, kind: row.kind, points: row.points || {},
           style: row.style || {},
           visible: row.visible !== false, locked: row.locked === true };
}

// indicators.js (buildIndicators gains a 4th arg)
function buildIndicators(indicators, params, styles, visible) {
  return indicators.map(function (t) {
    const e = { token: t };
    if (params && params[t]) e.params = params[t];
    if (styles && styles[t]) e.style = styles[t];
    if (visible && visible[t] === false) e.visible = false;  // absent = true, minimal payload
    return e;
  });
}
```

```python
# quotes.py — flags validated as REAL bools (reject int/str -> 400)
def parse_drawing(kind, points, style, visible=True, locked=False):
    ...  # existing kind/points/style validation unchanged
    if not isinstance(visible, bool): raise ValueError("visible must be a boolean")
    if not isinstance(locked, bool):  raise ValueError("locked must be a boolean")
    return points, style, visible, locked

# parse_layout_indicators: preserve-verbatim (no default injected)
if "visible" in item:
    if not isinstance(item["visible"], bool): raise ValueError("visible must be a boolean")
    entry["visible"] = item["visible"]
```

```python
# views.py
# GET api_drawings rows: add "visible": d.visible, "locked": d.locked
# _post_drawing: parse_drawing(kind, points, style,
#     body.get("visible", True), body.get("locked", False)) -> create(..., visible, locked)
# _put_drawing: parse_drawing(drawing.kind, body.get("points", drawing.points),
#     body.get("style", drawing.style), body.get("visible", drawing.visible),
#     body.get("locked", drawing.locked)); save(update_fields=["points","style","visible","locked"])
# POST/PUT responses include "visible"/"locked".
```

Model (`models.py:233-263`), additive:

```python
visible = models.BooleanField(default=True)
locked  = models.BooleanField(default=False)
```

Every query inside POST/PUT/GET already routes through `Drawing.for_user`
(`views.py:407,440,470`) — R14 preserved. Layout PUT stays `ChartLayout.for_user`
(`views.py:279`). No new `for_user` call sites.

## a11y + CSP

- **Toolbar**: `<div class="draw-tools" role="toolbar" aria-label="Drawing tools"
  aria-orientation="vertical">`; sub-`<div role="group" aria-label="Lines|Fib|Shapes|Text">`.
  Buttons are native `<button type="button" aria-pressed="true|false">`; SVG via
  `innerHTML` from a local constant (`iconFor`). Roving tabindex: active tool
  `tabindex="0"`, rest `-1`; Up/Down/Home/End move focus (structure mirrors the
  interval-chip keydown, `toolbar.js:63-71`).
- **Tree**: `<ul class="object-tree" role="tree" aria-label="Chart objects">`;
  group parents `<li role="treeitem" aria-expanded>` wrapping `<ul role="group">`;
  rows `<li role="treeitem" aria-selected>`. Per-row native buttons: eye
  (`aria-pressed`), lock (`aria-pressed`, drawings only), delete
  (`aria-label="Delete …"`). Keyboard: Up/Down between treeitems, Left/Right
  collapse/expand a parent, Enter select, Delete delete; roving tabindex.
- **Not color-only** (design-system R6/R9): eye/lock swap a filled↔outline icon
  plus `aria-pressed`; active tool uses `aria-pressed` + border/weight, never hue alone.
- **Focus**: existing `button:focus-visible` rule (`theme.css:43-45`) covers new
  controls; tree rows get `:focus-visible` via the same token.
- **CSP (R7/R25)**: no inline handler, no inline `<script>`; icons are strings with
  no event attributes. `requirements.txt`, `script-src` unchanged.

## CSS

Token-only additions in `theme.css` (reuse `--surface/--border/--accent/--muted/--sp-*`):

- `.draw-tools` (vertical flex column, gap `--sp-1`), `.draw-tool` button
  (`min-height`/`min-width:36px`), `.draw-tool[aria-pressed="true"]` (border/weight,
  not hue-only).
- `.object-tree` (`role=tree` list, no bullets), `.tree-group`/`.tree-group-label`,
  `.tree-row` (flex: name grows, actions at end), `.row-action` (≥32px hit target),
  `.tree-row[aria-selected="true"]` (non-color cue).
- Light/dark/system parity: all colors from tokens; `[data-theme="light"]` block
  already redefines every name, so no per-theme rule is required.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (node) | `chart-registry-core` data shape; `tool-icons-core` groups/`iconFor` (no `on*` attr, valid SVG); `object-tree`/`draw-toolbar` pure helpers (roving index, group build) | `node --test "tests/js/**/*.test.js"` |
| Unit (node) | `drawing-core.fromApi` carries flags; host applyOptions spy on `setSeriesVisible` (no setData) | extend `drawing-core.test.js`, `chart-host.test.js` |
| Integration | POST/PUT/GET flags round-trip; non-bool → 400 (no write); absent keeps stored; `kind` immutable; A≠B → 404; `parse_layout_indicators` visible valid/bad/absent | `test_market_api.py` (patch 100%) |
| Migration | `0014` down/up round-trip + `makemigrations --check` | new `test_migration_0014.py` (copy `test_migration_0012.py`) |
| Contract | `CONTROLLER_ALLOWLIST == 10`, +2 modules/controllers served JS; `STORE_KEYS==11`; `window.marketChart` 8 keys | `test_market_ux.py:128`, `chart-store.test.js`, e2e seam |
| E2E | toolbar groups render + `aria-pressed`; tree eye/lock/delete/select; hide persists via captured PUT; indicator eye → option-only (setData spy green); readiness-gated, DOM + network assertions, never pixels (#149) | `test_market_e2e.py` |
| Guard | no module >300 | `test_module_size_guard.py` |

## Migration / Rollout

Migration `0014` is purely additive (two `AddField`, mirrors `0013:17-21`);
revertible with `migrate trading 0013`, zero data loss. Layout-entry `visible`
needs no migration (absent = true). Delivery is a 3-slice feature-branch chain
(proposal §Delivery): **S1** extractions (`chart-registry-core`, preference
helpers if needed) + `Drawing.visible/locked` + migration `0014` + API/parse flags;
**S2** `tool-icons-core` + `draw-toolbar` + `setSeriesVisible` + wiring;
**S3** `object-tree` + indicator visibility (store key, event, layout `visible`)
+ wiring. Each slice is independently revertible (`git revert`); no CSP,
dependency, `src/`, or destructive-schema change.

## Risks & Mitigations

Carried from explore §6: R1 300-line ceiling (S1 extraction precondition; 293
contingency D11); R2 8-key seam freeze (assert via DOM/bus/PUT); R3 `STORE_KEYS`
10→11 (explicit R14 delta); R4 #68 (option-only `applyOptions`, setData spy); R5
R14 `for_user` (existing scoped queries); R6 patch 100% (`diff-cover`, full bool
matrix); R7 E2E flake (#149, readiness gate); R8 additive migration (round-trip
test); R9 hide≠remove (store slot + option-only host method); R10 `readIndicators`
re-source (store-backed); R11 CSP (no event attrs). NEW: R12 gear wiring — the
`openSettings` callback must be passed to the tree before first render (created
in `main` before `object-tree`, same boot order).

## Open Questions

None blocking. Explore §7 forks resolved: Q1→D4, Q2→D6, Q3→D5, Q4→D8, Q5→D9
(accept singleton groups), Q6→capability set in proposal.
