# Exploration: f5-chart-toolbar

Issue #118, Fase F5. Branch `develop` @ `96bd2f6`. Read-only exploration — no code changed.

## 1. Problem framing

Today the chart sidebar carries **two unrelated, separated lists** that both do
"list things on the chart, act on them":

- **Drawings tool + list** — `chart.html:80-89`: an `<h2>Drawings</h2>`, a
  `<fieldset class="drawings">` of five flat text buttons (`H-line`, `Trend`,
  `Fib`, `Box`, `Text`), a `.draw-cancel` button, and `<ul id="drawing-list">`.
  The list rows are rendered by `controllers/drawings.js:32-46`
  (`renderDrawingList`): one `<li><button class="drawing-del">× <kind> #<id></button></li>`
  per drawing — **delete-only**, no visibility, no lock, no selection.
- **Indicators** — `chart.html:46-68`: an `<h2>Indicators</h2>` +
  `<fieldset class="indicators">` of nine `.indicator-row` checkboxes (each with a
  period input and a ⚙ gear). The checkbox IS both "present on chart" and
  "visible" — unchecking removes it from the layout
  (`readIndicators()` at `controllers/indicators.js:49-56` filters `.indicator-toggle`).

What a **unified Object Tree** buys (TradingView parity):

1. **One place to see everything on the chart.** TradingView's "Object Tree"
   lists drawings *and* indicators together, grouped, with per-row
   eye/lock/delete/select. Today a user has to look in two different idioms.
2. **Separates "on the chart" from "visible".** The owner decision (B) makes
   hide/lock **persistent**. Today "off" can only mean "removed" (indicator) or
   "deleted" (drawing). Persistent hide lets a user park an object without losing
   it — and lock protects a finished drawing from accidental drag.
3. **Drawings get real per-row actions.** The current list only deletes. The tree
   gives visibility + lock + select, matching the already-built interaction layer
   (F4: selection, drag, delete — `controllers/drawing-interaction.js`).

## 2. Codebase map (exact files/functions, with refs)

### Markup — where the DOM lives
- `web/market/templates/market/chart.html`
  - Indicators list: `46-68` (`#indicators-heading`, `fieldset.indicators`,
    `.indicator-row` × 9, `.indicator-toggle`, `.indicator-param`,
    `.indicator-settings`).
  - Drawings tool + list: `80-89` (`fieldset.drawings` with `.draw-tool`
    `data-kind` ∈ {hline,trendline,fib,rect,text}, `.draw-cancel`, `#drawing-list`).
  - Dialogs: `text-dialog` `93-100`, `indicator-settings-dialog` `102-115`,
    `drawing-settings-dialog` `117-126`.
  - `modulepreload` block `131-152` — every served module listed; a NEW module
    must be added here (mirrors the allowlist).
- `web/market/templates/market/chart.js:28-34` — `CONFIG.urls` (kline/smc/layout/
  preference/drawings). New endpoints would be added here only if any.

### Toolbar controller — where the existing toolbar is built
- `web/market/templates/market/controllers/toolbar.js` (187): pair buttons
  (`30-34`), interval chips (`37-83`, incl. arrow-key nav `63-71`), scale/type
  selects (`97-116`), theme control (`123-152`), sidebar toggle (`155-162`).
  Returns `{setInterval,setScaleMode,setChartType,setTheme}` (`186`).
  **The draw-tool buttons are NOT here** — they belong to `drawings.js`.

### Drawings list + CRUD + tools
- `controllers/drawings.js` (261):
  - `renderDrawingList()` `32-46` — the list to replace.
  - `attachAllDrawings()` `51-67` — attaches primitives, writes
    `window.marketChart.drawings` seam (`64`), calls `renderDrawingList` (`65`),
    emits `drawings:changed` (`66`).
  - `loadDrawings()` `73-92`, `createDrawing` `144-162`, `deleteDrawing` `164-174`.
  - `syncToolButtons()` `176-183` — toggles `.draw-tool` active + `#chart.drawing`.
  - tool click wiring `218-232`; `onChartClick` `187-216`; `clearForSwitch` `251-258`.
  - `bus.on("drawing:selected")` `105-108`, `bus.on("drawing:changed")` `113-127`
    (already persists partial field PUTs: `body.points`/`body.style` `123-126`),
    `bus.on("drawing:delete")` `130-132`.

### Drawing interaction (selection/drag/lock target)
- `controllers/drawing-interaction.js` (217): `onPointerDown` `83-98` (calls
  `grabHandle(rows,...)` `87`; a miss clears selection), `onPointerMove` `100-114`,
  `endDrag` `116-131`, `onKeyDown` Delete/Escape `139-157`, `onDblClick` `161-173`,
  `attach()` `196-207`, `clearForSwitch()` `211-214`.
- `drawing-interaction-core.js` (230): `grabHandle`, `applyDrag`, `handlesFor`,
  `HANDLE_RADIUS`, `BODY_RADIUS`. **Lock enforcement seam**: filter `rows` by
  `locked` before `grabHandle` (interaction controller) and/or inside the core.

### Render layer (visible=false)
- `drawing-primitive.js` (126): `renderShape(ctx,size,row,map,selected)` `32-74`
  (per-kind draws), `makeDrawingPrimitive(row,selection)` `92-124`
  (`paneViews`/`autoscaleInfo`/`requestUpdate`). **visible=false → early-return in
  `renderShape` (or in the paneView `draw`) keeps the primitive attached but blank;
  `autoscaleInfo` should return null when hidden.**
- `drawing-core.js` (158): `fromApi(row)` `35-43` (**strips unknown fields** —
  must be extended to carry `visible`/`locked`), `DRAWING_KINDS` `13`,
  `defaultStyle` `25-30`.

### Indicator toggles + layout REST
- `controllers/indicators.js` (261): `DEFAULT_INDICATORS` `11`,
  `settingsFromFields` `22-34`, `readParams` `37-46`, **`readIndicators()` `49-56`
  (DOM checkbox source — the on/off truth today)**, `buildIndicators` `61-68`,
  `createIndicators({store,bus,config})` `75-260`:
  - `applyLayout(indicators)` `95-110` — syncs checkboxes from a saved layout.
  - `loadLayout(symbol,interval)` `114-142` — GET layout, sets `state.indicators`,
    `state.params`, `state.styles`, emits `layout:loaded` `135`.
  - `saveLayout()` `147-164` — debounced PUT
    `buildIndicators(state.indicators,state.params,state.styles)`.
  - `openDialog`/`applyDialog` `191-238` (gear/style dialog).
- `chart-host.js` (297): `REGISTRY` `16-56`, `PANE_ORDER` `59`.
  `build(state)` `156-199` — `enabled = state.indicators` (`175`),
  `isOn` (`177`), overlays `179-183`, panes `184-186`. `addSeries` `121-152`.
  `setTheme` `230-233` and `applyScale` `237-243` are the **option-only** precedent
  for a new `setSeriesVisible`. `activeSeries` `144-150` carries `{token,key,place,pane,series}`.

### Orchestration / store / bus
- `main.js` (283): boot state `33-44` (incl. `tool: null`), seam `51-60`,
  controllers `63-84`, `buildChart` `92-108`, `rebuild` `113-126`,
  `switchTo` `128-159`, bus handlers `164-182`, `savePreference` `195-208`.
- `chart-store.js` (58): `STORE_KEYS` **frozen 10-key** `13-24`
  (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType,
  theme, tool`) — adding a key requires an R14 spec delta.
- `chart-bus.js` (50): `EVENTS` `8-20`.

### Server — model / API / layout / validation
- `web/trading/models.py`: `ChartLayout` `210-230` (`indicators` JSONField `221`),
  **`Drawing` `233-263`** (`kind` choices `244-249`, `points` `253`, `style` `254`,
  index `(user,symbol)` `258-263`), `ChartPreference` `296-317`.
- `web/market/views.py`: allowlists `44-73` (**`MODULE_ALLOWLIST` `44-61`,
  `CONTROLLER_ALLOWLIST` `62-73` at 8 controllers** — a NEW module 404s without an
  entry). `api_layout` `216-292` (+`_put_layout` `260-292`), `api_drawings` `389-416`
  (+`_post_drawing` `419-455`), **`api_drawing_detail` `458-476` + `_put_drawing`
  `479-512`** (partial body `{points?,style?}`, kind-immutable `489-490`, persist
  `503-504` — the injection point for `visible`/`locked`).
- `web/market/quotes.py`: `DEFAULT_LAYOUT` `90`, **`parse_layout_indicators` `300-328`
  (only preserves `token`/`params`/`style` `322-327` — must add `visible`)**,
  `_validate_layout_style` `363-386`, **`parse_drawing(kind,points,style)` `415-445`**
  (validates shape, not the new flags).
- `web/trading/migrations/`: latest is **`0013_chartpreference_smc.py`** → the new
  migration is **`0014`** (task said 0014 — correct). `0013` is the additive
  AddField precedent (`AddField` JSONField `default=dict`, 17-21). `0012` is the
  destructive-order precedent (`RemoveIndex`→`AlterField`→`RemoveField`→`AddIndex`).
  **F5's 0014 is purely additive** (`visible` bool default True, `locked` bool
  default False) — SQLite-safe, no destructive order needed.

### CSS
- `web/accounts/templates/registration/theme.css` (220): `.indicators` `120-123`,
  `.indicator-row` `125-130`, `.drawings`/`.draw-tool` `155-159`, `.draw-cancel`
  `160`, `.drawing-list`/`.drawing-del` `161-164`, `.interval-chip` `85-89`,
  `.panel-toggle` `98`, dialogs `131-144`, `#chart:focus-visible` `147`.

### Module line counts (ceiling 300, empty allowlist)
`controllers/smc.js=300` (AT ceiling), `chart-host.js=297`, `main.js=283`,
`controllers/indicators.js=261`, `controllers/drawings.js=261`,
`drawing-interaction-core.js=230`, `controllers/drawing-interaction.js=217`,
`controllers/toolbar.js=187`.

### Tests that constrain F5
- `tests/web/test_market_ux.py`: `128` asserts `len(CONTROLLER_ALLOWLIST) == 8`
  (a new controller bumps this); `102-169` module/import-graph route coverage.
- `tests/web/test_market_e2e.py`: `579-746` indicator-toggle assertions,
  `.draw-tool[data-kind="hline"]` click `842`, `#drawing-list .drawing-del` `879`,
  interaction suite `887+` (uses `window.marketChart.drawings`, captured PUT/DELETE).
- `tests/web/test_market_api.py`, `tests/web/test_isolation.py`: drawings CRUD,
  layout round-trip.
- `tests/web/test_migration_0012.py`: the migration round-trip **pattern** to copy
  for a `0014` test (walks the real graph down/up).
- `tests/web/test_module_size_guard.py`: `CEILING=300`, empty allowlist, `rglob`.

## 3. Persistence design for hide/lock

### 3a. Drawing `visible` / `locked` — RECOMMENDED
Add two model fields to `Drawing` (`models.py:233-263`):

```
visible = models.BooleanField(default=True)
locked  = models.BooleanField(default=False)
```

- **Migration `0014`** = two additive `AddField` ops (mirrors `0013`, `17-21`).
  Non-destructive, SQLite-safe, reversible with zero data loss.
- **API**: `parse_drawing` (`quotes.py:415-445`) gains flag validation (accept &
  coerce booleans; reject non-bool → 400). `_post_drawing` (`views.py:419-455`)
  and `_put_drawing` (`479-512`) persist them; the partial-body PUT already accepts
  per-field updates — extend the partial set from `{points?,style?}` to
  `{points?,style?,visible?,locked?}` and add them to `update_fields` (`504`).
  GET (`407-416`) and POST/PUT responses must include `visible`/`locked`.
- **JS**: `drawing-core.fromApi` (`35-43`) must carry the flags (currently strips
  unknown keys). `drawing-primitive.renderShape` early-returns when `!visible`.
  `drawing-interaction` filters `locked` rows out of `grabHandle` (both
  `onPointerDown` `87` and `onDblClick` `164`) so a locked shape is not selectable
  /draggable — **but stay selectable from the tree** (select is a bus emit, not a
  pointer hit).
- **Persistence channel**: reuse the existing `drawing:changed` bus event with a
  new `visible`/`locked` field + `persist:true` — `drawings.js:113-127` already
  builds a partial PUT body from provided fields (`123-126`). **No new bus event.**

### 3b. Indicator visibility — the real fork
Today "indicator on/off" IS layout membership: `readIndicators()`
(`indicators.js:49-56`) reads the checked checkboxes; `saveLayout`
(`147-164`) PUTs exactly that token set; `parse_layout_indicators`
(`quotes.py:300-328`) stores `{token, params?, style?}` per entry.
A **hidden** indicator is a *different* state from a *removed* one, and nothing
in the layout today represents it.

Options:

| Option | Shape | Pros | Cons |
|---|---|---|---|
| **A. Flag in layout entry** (recommend) | each entry gains `visible?: bool` (absent = true); `parse_layout_indicators` validates it; `ChartLayout.indicators` JSON already open-ended → **no migration** | faithful to B; one persisted source; reuses the layout PUT | needs a store slot + host visibility method (see below) |
| B. Reuse the checkbox as "present" | keep membership = visible; "hide" = remove from layout | zero new state | NOT persistent-hide — contradicts the owner's B decision |
| C. Separate preference field | `ChartPreference` boolean map | global, not per-chart | wrong scope; indicators are per `(user,symbol,interval)` |

**Recommend A.** Because hide ≠ remove, and the layout JSON column is already
open-ended (the model docstring `217-221` says a JSON column "avoids a migration
per indicator token"), **no migration is needed for indicator visibility**.

Open forks the proposal/design must settle (see §7): where the flag lives in the
store, and how hidden series render.

### 3c. Rendering a hidden indicator — RECOMMENDED option-only
The host builds a series only for `state.indicators` (`chart-host.js:175-186`).
Two ways to hide:
- **Option-only (recommend)**: build ALL layout indicators, then
  `series.applyOptions({visible:false})`. Eye toggle = option-only (no rebuild,
  no setData — mirrors `setScaleMode` `247-250` / `setTheme` `230-233`). **#68-clean.**
- Rebuild route: exclude hidden from `state.indicators` and rebuild via
  `indicator:changed` (setData path). Simpler, but re-fetches/recomputes on every
  eye toggle — wasteful and TradingView-unfaithful.

Option-only requires `chart-host.js` (297) to gain a `setSeriesVisible(token,bool)`
method (~+8 lines) → **303 > 300. Forces an extraction first** (see §4).

## 4. Module-size strategy (CRITICAL)

Every touched module must stay ≤300. `smc.js` is AT 300 and `chart-host.js` is at
297 — F5 must not grow either. Recommended new modules + precondition extractions:

### New pure cores (node-tested, no DOM)
| Module | Responsibility | ~Lines |
|---|---|---|
| `market/tool-icons-core.js` | `TOOL_GROUPS` (grouped vocab: lines→hline/trendline, fib→fib, shapes→rect, text→text), `iconFor(kind)` → inline-SVG string (no handlers), `TREE_GROUPS`. Pure, imports nothing. | ~110 |
| `market/chart-registry-core.js` | Move `REGISTRY` + `PANE_ORDER` + `SCALE_MODES` out of `chart-host.js` (`16-67`). Pure data; importers (`indicators.js:9`, `chart-host.js`) update. | ~60 (moved) |

### New controllers (thin, DI factory per R14)
| Module | Responsibility | ~Lines |
|---|---|---|
| `controllers/draw-toolbar.js` | Vertical grouped icon toolbar: renders from `tool-icons-core`, sets `store.tool`, reflects active state via `store.subscribe`, Up/Down arrow nav. Replaces `.draw-tool` buttons in `chart.html:82-86`. | ~160 |
| `controllers/object-tree.js` | Unified tree: subscribes `drawings:changed` + indicator source; renders grouped `role="tree"`; per-row eye/lock/delete/select emits existing bus events (`drawing:changed` w/ visible|locked, `drawing:delete`, `drawing:selected`) and the indicator path. Replaces `renderDrawingList` + the indicators fieldset. | ~230 |

`CONTROLLER_ALLOWLIST` 8 → 10 (`views.py:62-73`); `test_market_ux.py:128` bumps to 10;
`chart.html` `modulepreload` +2 (`131-152`).

### Precondition extractions (to keep ceilings)
| File | Now | Change | Result |
|---|---|---|---|
| `chart-host.js` | 297 | −`REGISTRY`/`PANE_ORDER`/`SCALE_MODES` to `chart-registry-core.js` (−~50) then +`setSeriesVisible` (+~10) | ~257 |
| `controllers/drawings.js` | 261 | −`renderDrawingList` (−15, moves to object-tree); add visible/locked render+persist handling | ≤ ~270 |
| `controllers/indicators.js` | 261 | −checkbox-list DOM ownership (moves to object-tree); `readIndicators` re-sourced | shrink |
| `main.js` | 283 | +2 controller creations + wiring; **must be watched** — at risk of >300; if so extract the `savePreference`/`saveLayout` persistence helpers to a small module | ≤300 (verify) |

**S1 extraction (`chart-host.js` + `drawings.js`) is a hard precondition**, exactly
as F4 did (`archive/2026-10-14-drawing-interaction/tasks.md:31`). Without it the
first added line breaks the guard.

## 5. a11y + CSP plan

### Icon toolbar (CSP-safe)
- `<div class="draw-tools" role="toolbar" aria-label="Drawing tools"
  aria-orientation="vertical">`, with `role="group" aria-label="Lines|Fib|Shapes|Text"`
  sub-groups.
- Each button: native `<button type="button" aria-pressed="true|false"
  aria-label="…">`, icon = **inline SVG injected by JS** from `tool-icons-core`
  (no `onclick`, no inline `<script>` — SVG markup without event attributes is CSP-clean
  under the existing `script-src`). Active tool: `aria-pressed="true"` + `.active`
  class (state MUST NOT be color-only — weight/border per `design-system` R6/R9).
- Keyboard: Up/Down (and Home/End) move focus across the group — mirror the interval
  chip pattern (`toolbar.js:63-71`). Enter/Space activate natively.

### Object Tree
- `<ul class="object-tree" role="tree" aria-label="Chart objects">`.
- Group parents: `<li role="treeitem" aria-expanded="true" aria-label="Drawings">`
  wrapping a `<ul role="group">`; same for `Indicators`. Rows:
  `<li role="treeitem" aria-selected="true|false">`.
- Per-row action buttons (native `<button>`): eye = visibility toggle
  (`aria-pressed`), lock = `aria-pressed` (drawings only), delete
  (`aria-label="Delete …"`), select (row focus/Enter). No color-only state.
- Keyboard on the tree: Up/Down between visible treeitems, Left/Right collapse/expand
  a group parent, Enter = select, Delete = delete the focused row. Roving tabindex
  (single `tabindex="0"`, rest `-1`) mirroring the chip group.
- Every icon from `tool-icons-core`; every control has an accessible name.

### CSP
- **No inline handlers, no inline `<script>`.** Icons via JS `innerHTML`/`createElementNS`
  from a core map. Existing market CSP (`market-chart` R6, `chart-shell` R25,
  `design-system` R7) unchanged; `requirements.txt` unchanged; no new dependency.
  E2E/template scans must not find `onclick`/`<script>` inline.

## 6. Risk list

| # | Risk | Severity | Evidence / mitigation |
|---|---|---|---|
| R1 | **300-line ceiling** — `smc.js` AT 300, `chart-host.js` 297, `main.js` 283, `drawings.js`/`indicators.js` 261 | **High** | `test_module_size_guard.py`; S1 extraction precondition (§4) |
| R2 | **`window.marketChart` 8-key freeze** — no 9th key | High | `market-chart` R18/R20; object tree asserts via DOM/bus + captured PUT; drawings rows already ride `marketChart.drawings` (`drawings.js:64`) and can carry `visible`/`locked` via `fromApi` without a new key |
| R3 | **`STORE_KEYS` frozen 10-key** (R14) — indicator visibility needs a reactive source | High | `chart-store.js:13-24`, `market-chart` R14; adding a key = spec delta (see §7) |
| R4 | **#68 single-write-path** — visibility must not add a setData writer | Med | prefer option-only `applyOptions({visible})`; #68 spies in `chart-host.test.js` |
| R5 | **R14 for_user** — new persisted fields must route through `Drawing.for_user`/`ChartLayout.for_user` | Med | `api_drawing_detail:470`, `_put_layout:279` already scoped |
| R6 | **Patch coverage 100%** on new Python (0014 + `parse_drawing` flags + PUT/POST) | High | `diff-cover`; full branch matrix (valid/bad bool, absent, A≠B) |
| R7 | **E2E class-C flake (#149)** — SQLite threaded `live_server` | Med | existing readiness-gate `_wait_ready`; assert DOM + captured network, never pixels |
| R8 | **Migration 0014 additive but schema-touching** | Low | `0013` AddField precedent; add a `0014` round-trip test mirroring `test_migration_0012.py` (`makemigrations --check` green) |
| R9 | **Indicator "hide" semantics** — hidden ≠ removed; risk of double-source truth | Med | settle store slot + host method (§3c/§7) before apply |
| R10 | **`readIndicators()` DOM source** breaks when the checkbox list moves to the tree | Med | re-source from the tree/store, keep `buildIndicators` shape stable |
| R11 | **CSP regression** if an icon string or handler leaks inline | Low | core emits markup without event attrs; template/DOM scans |

## 7. Open questions (for proposal/design — only real forks)

1. **Indicator visibility store home.** Add an 11th `STORE_KEYS` slot (e.g.
   `indicatorVisible: {token: bool}`) with an explicit `market-chart` R14 delta —
   OR keep it in `indicators.js` closure and publish via a bus event? (Recommend
   the store slot: the object tree needs a reactive source; the store is the
   documented home for UI/config state.) This is the single biggest fork.
2. **Hidden-indicator render path.** Option-only `applyOptions({visible})` (recommend,
   #68-clean, forces the `chart-host.js` extraction) vs rebuild via `indicator:changed`.
3. **New bus event for indicator visibility?** Reuse a light path (or the store)
   vs a new `indicator:visibility` event that main routes to
   `host.setSeriesVisible` (mirrors `scale:changed:179-182`). Drawing hide/lock can
   reuse `drawing:changed` (no new event); the indicator path needs a decision.
4. **Object tree scope.** List only active indicators (layout membership — recommend,
   TradingView-faithful) vs all 9 registry tokens (would need a "+" add affordance).
5. **Icon set.** Confirm the grouped taxonomy (lines / fib / shapes / text) and
   whether the existing 5 `DRAWING_KINDS` map 1:1 (today: exactly 5 kinds →
   groups of 1/1/1/1/1 is thin; may want ≥2 shapes or accept singleton groups).
6. **Capability shape.** New `chart-toolbar` + `chart-object-tree` capabilities,
   or extend `chart-shell` (R25-R27) + `chart-drawings` + `chart-indicator-settings`?

## Prioritized brief for the next phase (sdd-propose)

- **Intent**: TradingView-style vertical grouped icon toolbar (replaces
  `chart.html:80-89` text buttons) + a unified Object Tree (replaces
  `#drawing-list` and the indicators fieldset), with **persistent** hide/lock.
- **In scope**: `tool-icons-core.js`, `draw-toolbar.js`, `object-tree.js`;
  `chart-registry-core.js` extraction; `Drawing.visible/locked` + migration `0014`;
  layout-entry `visible`; `parse_drawing`/`parse_layout_indicators` flag validation;
  `maxPaper`-style wiring in `main.js`; allowlists 8→10; CSS tokens; specs
  `market-chart`(R14/R11/R18/R20), `chart-drawings`(R1/R2/R6/R9),
  `chart-indicator-settings`, `chart-shell`(R25-R27), `design-system`(R9).
- **Out of scope**: order execution (HARD, read-only), SMC internals, undo/versioning,
  shared drawings, new npm/build, CSP relaxation, new runtime dependency, `src/` changes.
- **Delivery**: likely a **feature-branch chain** (≥3 slices: (1) extractions +
  `Drawing` fields/migration/API/parse; (2) icon toolbar; (3) object tree + wiring)
  — well over the 400-line budget; `sdd-tasks` must forecast
  `Chained PRs recommended: Yes`, `400-line budget risk: High`.

### Ready for Proposal
**Yes.** The codebase is fully mapped, the owner's persistence decision (B) is
honored, the extraction preconditions are identified, and the only blocking
design forks are enumerated in §7 (chiefly the indicator-visibility store home).
