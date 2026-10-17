# Proposal: f7-chart-shortcuts

Issue #120, Fase F7. Branch `develop` @ `0c2e3e8`. Read-only. Builds on archived F5
(`archive/2026-10-16-f5-chart-toolbar/`), F6 (`archive/2026-10-17-f6-measure-position/`)
and F8 scale path. Resolutions honor `explore.md` §7 forks as decided.

## Intent

F5/F6 shipped the drawing substrate; F7 adds the three TradingView interaction
instruments that substrate was built to carry:

- **Context menu** — a *transient view* over `(target-under-cursor, selection)` → an
  action list. Not state: drawing row → delete/duplicate; empty chart → reset-scale/
  add-indicator (`explore.md:18-26`). Must be JS-built DOM (CSP) and focus-trapped.
- **Undo/redo** — a *deterministic operation stack*, NOT pixels. Today the drag path
  already coalesces *rendering* to one PUT (`drawings.js:113` `if (!p.persist) return`),
  but a raw "record every `drawing:changed`" stack records every frame; the stack must
  model **operations**, so it needs a begin/commit boundary (`explore.md:27-36`).
- **Shortcuts** — ONE new binding for `Ctrl/Cmd+Z` / `Ctrl/Cmd+Shift+Z`|`Y`; the existing
  Escape/Delete are `#chart`-scoped and E2E-covered, so they stay untouched.

**Why a pure-core stack, not a store key.** The issue says "en el store", but read
literally that is a 12th `STORE_KEYS` slot. Every `store.set` notifies ALL subscribers
(`chart-store.js:47`) → `object-tree.js:295 render` re-runs on every push — an O(n) side
effect for a mutation that touches no config, violating #68 config/UI-only discipline
(`explore.md:38-47`). A pure `history-core.js` models the operation (`{op, id, before,
after}`) headlessly and keeps the store frozen at 11 keys.

**Why server-coupled undo.** All drawing mutations land as HTTP in `drawings.js`
(`createDrawing` `:139` POST / `deleteDrawing` `:162` DELETE / `persistDrawing` `:131`
PUT; `explore.md:49-63`). An undone delete must re-POST (id is gone, new id minted) and
an undone create must DELETE; a local-only stack patching `currentDrawings` would
silently diverge from the DB. The stack stores the **operation**, replayed through the
existing verbs.

## Scope

### In Scope
- Pure cores `market/history-core.js` + `market/context-menu-core.js` (node-tested).
- Controllers `controllers/undo.js` (stack owner + `Ctrl/Cmd+Z` binding) and
  `controllers/context-menu.js` (DOM `role="menu"`, hit-test, focus trap). Name is
  `undo.js` because `controllers/history.js` ALREADY EXISTS (REST pagination,
  `explore.md:152-155`).
- Undoable ops: **create / move(drag) / delete / duplicate / style**; one gesture =
  one entry via the `persist:true` boundary (`drawing-interaction.js:187,201`).
- Duplicate via thin `bus.emit("drawing:duplicate")` handled in `drawings.js`, reusing
  `createDrawing` (`drawings.js:139`).
- Reset-scale reuses F8 path (`store.scaleMode="linear"` + `scale:changed`, `main.js:204`);
  add-indicator reuses F5 `add-indicator-core` seam (`inactiveTokens` `:18`, `store.set` +
  `indicator:changed` `:79`). Neither is in the undo stack.
- `aria-keyshortcuts` on draw-toolbar buttons; firing only when focus is inside `#chart`.
- `MODULE_ALLOWLIST` +2 cores; `CONTROLLER_ALLOWLIST` 13→15 (`views.py:44,69`); bump
  `test_market_ux.py:146` `== 13` → `== 15`.

### Out of Scope
Order execution **HARD** (read-only repo); SMC internals (`find_setups`/scoring untouched);
persisted undo across reload; cross-symbol undo; new dependency or build; CSP relaxation;
`src/` changes; per-tool **global** letter shortcuts (the tree owns `v`/`l`/`s`,
`object-tree.js:137-142,201-205`).

## Capabilities

### New Capabilities
- `chart-history`: the in-session undo/redo operation stack — push/undo/redo/canUndo/
  canRedo/clear, gesture-boundary coalescing, redo-clear rule, symbol-switch `clear()`;
  server-coupled replay (re-POST undo-delete, DELETE undo-create, PUT undo-move) and the
  `Ctrl/Cmd+Z`/`Shift+Z`/`Y` router.
- `chart-context-menu`: the right-click menu — `menuModel(target,row,selection,scaleMode)`
  item list, DOM `role="menu"` with roving focus/`Escape` focus-return, and the
  delete/duplicate/reset-scale/add-indicator commands.

### Modified Capabilities
- `chart-drawings`: gains a duplicate operation (create-with-cloned-points via the
  existing POST), reusing R2 CRUD; R8 read-only boundary unchanged.
- `chart-toolbar`: R1/R6 — `aria-keyshortcuts` per tool button; deferred letter firing.
- `market-chart`: **R14** inventory gains `history-core.js`/`context-menu-core.js` +
  `controllers/undo.js`/`context-menu.js`; allowlist 13→15; **R18/R20** seam stays 8 keys
  and `STORE_KEYS` stays 11.
- `design-system`: **R6/R7** — menu is keyboard-navigable, focus returns to `#chart`,
  items carry `aria-keyshortcuts`; CSP `script-src 'self'`, menu built via JS
  (`middleware.py:28`, no inline `oncontextmenu`).

## Approach

Layered F0/F5/F6/F8 extension; logic lives in pure cores so every touched controller
stays ≤300 (`explore.md:217-251`).

- **Pure cores first** (node-tested, no DOM): `history-core.js` (`createHistory({limit})→
  {push,undo,redo,canUndo,canRedo,clear,size}` with the redo-clear rule) and
  `context-menu-core.js` (`menuModel(...)` + focus-index helpers).
- **Undo controller** (`controllers/undo.js`): owns the stack; subscribes to the
  `persist:true` `drawing:changed` (`drawing-interaction.js:201`), `drawing:delete`
  (`:227`) and `drawings:changed` (`drawings.js:51`) to cache last-committed points per id;
  replays by emitting the existing bus commands. Binds `Ctrl/Cmd+Z`/`Shift+Z`/`Y` on
  `document`, guarded by `e.metaKey||e.ctrlKey`. A symbol switch `clear()`s the stack
  (mirror `clearForSwitch` `main.js:161-167`).
- **Context-menu controller**: binds `contextmenu` ONCE on `#chart` (like
  `drawing-interaction.attach` `:270`), `e.preventDefault()`, hit-tests via the reused
  pure `grabHandle(pointerRows(rows),…,map())` (`drawing-interaction-core.js:85`), renders
  DOM `role="menu"` with roving focus + `Escape` returning focus.
- **Reuse, no new path**: duplicate/restore → `createDrawing` (POST) + `attachAllDrawings`
  (`drawings.js:37`); delete reuses `drawing:delete`; reset-scale → `scale:changed`; add-
  indicator → `add-indicator-core` seam. #68 single-write-path preserved (`explore.md:294-296`).
- **Ceiling discipline**: `object-tree.js` (299) `drawing-interaction.js` (291) `smc.js`
  (300) stay byte-untouched; `drawings.js` 281→~291 (+duplicate branch); `main.js` ~+6.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `market/history-core.js` | New | pure operation stack + redo-clear rule |
| `market/context-menu-core.js` | New | pure menu model + focus helpers |
| `controllers/undo.js` | New | stack owner + `Ctrl/Cmd+Z` router |
| `controllers/context-menu.js` | New | DOM `role="menu"`, hit-test, focus trap |
| `controllers/drawings.js` | Modified | `drawing:duplicate` branch reusing `createDrawing` (281→~291) |
| `main.js` | Modified | import + `createUndo`/`createContextMenu` (+~6) |
| `controllers/object-tree.js` (299), `drawing-interaction.js` (291), `smc.js` (300) | Untouched | MUST stay ≤300 |
| `market/chart-store.js` (11), `chart-host.js` (267) | Untouched | no 12th key; reset routes via main |
| `controllers/draw-toolbar.js` | Modified | `aria-keyshortcuts` per button |
| `web/market/views.py` | Modified | allowlists +2 modules, +2 controllers |
| `web/middleware.py` (CSP), `theme.css` | Unchanged/Modified | CSP untouched; menu tokens |
| `tests/js/*`, `tests/web/*` | Modified | cores, controller helpers, e2e, allowlist 15 |

## Rollback Plan

- **No migration, no schema/data change** → nothing to unwind server-side.
- **Feature-branch chain** → drop the tracker branch and all child slices; no merge to
  `develop` until green.
- **Stack is in-session only** → revert `history-core.js`/`undo.js`/`context-menu-core.js`/
  `context-menu.js` + their JS/CSS/markup; no persisted state to recover.
- Each slice independently revertible; no CSP, dependency, `src/`, or destructive change.

## Risks

| Risk | L | Mitigation |
|------|---|------------|
| 300-line ceiling (guard empty, `smc.js`=300, `object-tree.js`=299) | High | both plus `drawing-interaction.js` byte-untouched; `drawings.js` ~291; duplicate fallback in undo controller |
| Seam freeze 8 keys (`main.js:57-66`) | High | F7 adds NO seam key; assert via DOM/bus |
| `STORE_KEYS` frozen 11 (#68/R14) | High | Fork 1: no 12th key; pure core (`chart-store.js:13-27`) |
| #68 single-write-path | High | menu/undo replay the existing bus commands; `setData` spy green |
| Drag coalescing correctness | High | record ONLY on `persist:true` (`drawing-interaction.js:201`); one gesture = one entry |
| Undo/server consistency / id re-mint | High | store the OPERATION; re-POST undo-delete, DELETE undo-create, PUT undo-move; symbol-switch `clear()` |
| R14 cross-user isolation | High | replay only `for_user` CRUD; stack cleared on switch |
| Shortcut conflicts | Med | only Ctrl/Cmd+Z/Shift+Z/Y added; `v`/`l`/`s` stay tree-owned; letters deferred |
| Patch coverage 100% | High | `diff-cover`; node tests for both cores + controller pure-helper tests |
| E2E class-C flake (#149) | Med | readiness-gated `_wait_ready` (`e2e:563`); assert DOM + network, never pixels |

## Read-Only Boundary

MUST NOT place/modify/cancel orders or relax any read-only invariant. `src/` framework-free
and unchanged; no new dependency; no build; ESM `.js`; CSP unchanged (menu is JS-built DOM,
no inline `oncontextmenu`). Strict TDD (`openspec/config.yaml`): tests precede implementation.

## Delivery (Feature Branch Chain)

Over the 400-line budget → chained PRs. S1 pure cores + node tests; S2 undo controller +
`drawing:duplicate` + `Ctrl/Cmd+Z` + e2e; S3 context-menu core/controller + toolbar
`aria-keyshortcuts` + allowlist bump + e2e. Base: tracker branch `feat/f7-chart-shortcuts`.

- Chained PRs recommended: **Yes**
- 400-line budget risk: **High**

## Success Criteria

- [ ] Context menu is DOM (`role="menu"`), keyboard-navigable, `Escape` returns focus to `#chart`.
- [ ] Undo/redo consistent across create/move/delete/duplicate; one drag = one entry.
- [ ] `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z`, `Ctrl/Cmd+Y` work and are documented.
- [ ] Reset-scale and add-indicator work from the menu via the F8/F5 seams (not in the stack).
- [ ] `window.marketChart` stays 8 keys; `STORE_KEYS` stays 11; size guard passes with empty allowlist.
- [ ] `CONTROLLER_ALLOWLIST` 15 / `MODULE_ALLOWLIST` +2; served same-origin; patch coverage 100%.
- [ ] `node --test` + `pytest` green; undo-delete re-POSTs (new id), undo-create DELETEs.
