# Proposal: f5-chart-toolbar

Issue #118, Fase F5. Branch `develop` @ `96bd2f6`. Read-only.

## Intent

The chart sidebar carries two unrelated "list things on the chart, act on them"
idioms: a flat text drawing tool + delete-only list (`chart.html:80-89`,
`controllers/drawings.js:32-46`), and a nine-checkbox indicators fieldset
(`chart.html:46-68`) where the checkbox is both "present" and "visible". F5
gives TradingView parity: a **vertical grouped icon toolbar** and one **Object
Tree** listing drawings *and* indicators, each with per-row visible / lock /
delete / select. Hide and lock are **persistent** (owner decision B): a hidden
object stays on the chart, parked, not deleted.

## Scope

### In Scope
- Pure `tool-icons-core.js` (grouped vocab + inline-SVG strings) and
  `chart-registry-core.js` (REGISTRY/PANE_ORDER/SCALE_MODES moved out of
  `chart-host.js:16-67`).
- Controllers `draw-toolbar.js` (vertical icon toolbar, replaces
  `chart.html:82-86`) and `object-tree.js` (unified tree, replaces
  `#drawing-list` and the indicators fieldset).
- `Drawing.visible` (bool, default True) + `Drawing.locked` (bool, default
  False) + additive migration **`0014`** (latest `0013`); `parse_drawing`
  (`quotes.py:415-445`), `_post_drawing`/`_put_drawing` (`views.py:419-455`,
  `479-512`) carry them; partial-PUT set extends `{points,style}` →
  `{points,style,visible,locked}`.
- Layout entry `visible?: bool` (absent = true) in `parse_layout_indicators`
  (`quotes.py:300-328`) — **no migration** (JSON column open-ended,
  `models.py:217-221`).
- Option-only render: new `host.setSeriesVisible(token,bool)` via
  `series.applyOptions({visible})`; drawings hidden in
  `drawing-primitive.renderShape` (`drawing-primitive.js:32-74`).
- Allowlists 8→10 (`views.py:62-73`), `test_market_ux.py:128` → 10,
  `chart.html` modulepreload +2, CSS tokens.

### Out of Scope
Order execution (HARD); SMC internals; undo/versioning; shared drawings;
npm/build; CSP relaxation; new runtime dependency; `src/` changes.

## Capabilities

### New Capabilities
- `chart-toolbar`: vertical grouped icon toolbar — role="toolbar", grouped
  `aria-label`s, `aria-pressed` active state, Up/Down/Home/End roving focus.
- `chart-object-tree`: unified tree — `role="tree"`, grouped parents, per-row
  eye/lock/delete/select, keyboard tree navigation, active-only membership.

### Modified Capabilities
- `chart-drawings`: **R1** model gains `visible`/`locked`; **R2** CRUD
  accepts/returns both, PUT partial body gains them; **R6** hidden renders
  blank (autoscale null), locked row not pointer-selectable/draggable; **R9**
  lock enforcement (tree-select still allowed).
- `market-chart`: **R14** store vocabulary gains the 11th key
  `indicatorVisible`; inventory gains 2 cores + 2 controllers; allowlist/count;
  **R11** drawings flags; **R20** permits exactly one new bus event
  `indicator:visibility`; **R18** seam stays 8 keys.
- `chart-indicator-settings`: **F2.4** `visible` in the store slot; **F2.5**
  add `setSeriesVisible` option-only host contract.
- `design-system`: **R6/R7** a11y + CSP for toolbar/tree icons and controls;
  toolbar/tree token requirements.
- `chart-shell`: **R25** a11y/CSP for the vertical toolbar and tree; **R23/R24**
  sidebar layout preserved.

## Approach

Layered F0 extension. Pure cores first: `tool-icons-core.js` (no imports) and
`chart-registry-core.js` (data moved from `chart-host.js`, freeing the ceiling
for `setSeriesVisible`). Two thin DI controllers (`draw-toolbar.js`,
`object-tree.js`) render from the cores and emit **existing** bus events.

- **Persistence channel** — drawings: reuse `drawing:changed` with
  `visible`/`locked` + `persist:true` (`drawings.js:113-127` already builds a
  partial PUT). Indicators: new `indicator:visibility` event → `main` routes to
  `host.setSeriesVisible` (mirrors `scale:changed`, `main.js:179-182`).
- **Fork 1 (store home) — 11th slot `indicatorVisible: {token: bool}`** with an
  explicit `market-chart` R14 delta. Chosen over a closure+bus: the tree needs a
  *reactive* source and the store is the documented home for UI/config state
  (`chart-store.js:13-24`); a closure would force a bespoke subscription.
- **Fork 2 (command path) — new `indicator:visibility` event.** `indicator:changed`
  is the rebuild/setData path; a visibility toggle must NOT re-fetch or
  setData (#68), so it cannot ride it. Option-only mirrors `scale:changed`.
- **Fork 3 (tree scope) — active-only** (layout membership), TradingView-faithful;
  all-9 registry would need a "+ add" affordance out of scope.
- **Fork 4 (capability shape)** — the set above: 2 new + 5 modified.
- **Fork 5 (icons) — grouped vocab lines/fib/shapes/text** from the pure core;
  accept singleton groups (5 kinds → 2/1/1/1). Inventing a second shape to pad a
  group is dishonest; TradingView ships thin groups too.

Precondition extractions (ceiling `test_module_size_guard.py`, empty allowlist):
`chart-host.js` 297 − registry (~50) + setter (~10) ≈ 257; `drawings.js` 261
loses `renderDrawingList`; `indicators.js` 261 loses checkbox-list DOM;
`main.js` 283 watched (extract persistence helpers if it crosses 300).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `market/tool-icons-core.js` | New | grouped vocab + inline-SVG icons (pure) |
| `market/chart-registry-core.js` | New | REGISTRY/PANE_ORDER/SCALE_MODES moved |
| `controllers/draw-toolbar.js` | New | vertical grouped icon toolbar |
| `controllers/object-tree.js` | New | unified drawings+indicators tree |
| `chart-host.js` | Modified | −registry, +`setSeriesVisible` option-only |
| `controllers/drawings.js` | Modified | −list render, +visible/locked persist |
| `controllers/indicators.js` | Modified | re-source `readIndicators` from tree/store |
| `main.js` | Modified | wiring + `indicator:visibility` route |
| `drawing-core.js`, `drawing-primitive.js` | Modified | carry flags; hidden draw blank |
| `chart-store.js` | Modified | 11th key `indicatorVisible` |
| `chart.html`, `theme.css` | Modified | markup, preload, tokens |
| `web/market/{views,quotes}.py` | Modified | allowlists, flag validation/persist |
| `web/trading/{models.py,migrations/0014}` | Modified/New | `visible`/`locked` additive |
| `tests/js/*`, `tests/web/*` | Modified | cores, allowlist count, api/e2e |

## Rollback Plan

- **Migration `0014`** is purely additive (two `AddField`, mirrors `0013:17-21`)
  → revert with `python manage.py migrate trading 0013`; zero data loss.
- **Feature-branch chain** → drop the tracker branch and all child slices; no
  merge to `develop` until green.
- Layout-entry `visible` needs no migration → just unset the flag (absent = true).
- No CSP, dependency, `src/`, or destructive-schema change; each slice is
  independently revertible.

## Risks

| Risk | L | Mitigation |
|------|---|------------|
| 300-line ceiling (`smc.js` AT 300, host 297, main 283) | High | S1 extraction is a hard precondition |
| `window.marketChart` 8-key freeze (no 9th) | High | assert via DOM/bus + captured PUT (`market-chart` R18/R20) |
| `STORE_KEYS` frozen 10 → 11 | High | explicit R14 delta; tree is the reactive consumer |
| #68 single-write-path on visibility | Med | option-only `applyOptions`; host spies green |
| R14 `for_user` on new fields | Med | route through `Drawing.for_user` (already scoped) |
| Patch coverage 100% (0014 + flags + PUT/POST) | High | `diff-cover`; full valid/bad/absent bool matrix |
| E2E class-C flake (#149) | Med | readiness gate; assert DOM + network, never pixels |

## Read-Only Boundary

MUST NOT place/modify/cancel orders, expose order endpoints, or relax any
read-only invariant. `src/` framework-free and unchanged; `requirements.txt`
unchanged; CSP unchanged (icons via JS-built inline SVG, no handlers).

## Delivery (Feature Branch Chain, 3 slices)

S1 extractions + `Drawing` fields/migration/API/parse (~300) | S2 icon toolbar
+ cores + wiring (~300) | S3 object tree + indicator visibility + wiring (~350).
Base: tracker `feat/f5-chart-toolbar`. Total ≈ 950.

- Chained PRs recommended: **Yes**
- 400-line budget risk: **High**

## Success Criteria

- [ ] Toolbar renders grouped vertical icons; `aria-pressed` active tool; Up/Down/Home/End nav.
- [ ] Tree lists drawings + active indicators with eye/lock/delete/select; keyboard-operable.
- [ ] Hide/lock persist across reload (drawings via `visible`/`locked`; indicators via layout `visible`).
- [ ] Hidden indicator toggles via option-only `applyOptions` — no setData/rebuild (#68 spies green).
- [ ] `window.marketChart` stays exactly 8 keys; size guard passes with empty allowlist.
- [ ] PUT/POST validate booleans (bad → 400); miss/A≠B → 404; patch coverage 100%.
- [ ] `node --test` + `pytest` green; migration `0014` round-trips (`makemigrations --check`).
