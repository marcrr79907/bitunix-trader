# Design: f7-chart-shortcuts (issue #120, Fase F7)

## Technical Approach

Layered F0/F5/F6/F8 extension (`docs/architecture/chart-modules.md:9-21`). Three
instruments = three seams, all reusing shipped paths:

- **Undo/redo** — pure `market/history-core.js` (opaque operation stack) owned by
  a new `controllers/undo.js` that records ONLY at the `persist:true` gesture
  boundary (`drawing-interaction.js:201`) and replays through the existing bus
  commands (`drawing:delete`/`drawing:changed`) plus two thin new commands
  (`drawing:duplicate`, `drawing:restore`) handled in `drawings.js`. Server stays
  the single writer: replay re-runs the SAME `createDrawing`/`persistDrawing`/
  `deleteDrawing` HTTP (`drawings.js:131,139,162`).
- **Context menu** — pure `market/context-menu-core.js` (`menuModel`) + new
  `controllers/context-menu.js` binding `contextmenu` ONCE on `#chart` (mirrors
  `drawing-interaction.attach` `:270`), hit-testing via the reused pure
  `grabHandle(pointerRows(rows),…)` (`drawing-interaction-core.js:85`) and
  rendering a CSP-clean `role="menu"`.
- **Shortcuts** — one new `document`-level binding in `undo.js` for
  `Ctrl/Cmd+Z` / `Shift+Z` / `Y`. Existing `#chart` Escape/Delete
  (`drawing-interaction.js:213-231`) and tree `v`/`l`/`s`
  (`object-tree.js:137-142,201-205`) stay byte-untouched.

#68 held: neither new path calls `setData`/`update`; menu commands emit bus
commands, replay reuses `drawings.js`. R14 held: replay only `for_user` CRUD;
`clearForSwitch` drops the stack on symbol change.

## Architecture Decisions

| # | Decision | Choice | Alternatives rejected | Rationale |
|---|---|---|---|---|
| D1 | Undo home | Pure `history-core.js` + `controllers/undo.js` owner; `STORE_KEYS` stays **11** | 12th store key | Every `store.set` notifies all subscribers (`chart-store.js:47`) → `object-tree.render` (`:295`) re-runs per push; the store is config/UI-only (#68). Fixed by brief; `explore.md:134-150` |
| D2 | Undo scope | create / move / delete / duplicate / style | +reset-scale, +add-indicator | Brief decides OUT: they are own commands (F8/F5 seams), not drawing ops (`explore.md:157-162`) |
| D3 | Gesture boundary | Record only on `drawing:changed persist:true` | record every `drawing:changed` frame | Per-frame recording = N entries per drag; the `:201` emit is the one-per-gesture seam (`explore.md:164-170`) |
| D4 | Server coupling | Store the OPERATION; replay HTTP verbs | local-only point patch | Un-undone delete's id is gone; a local patch diverges from the DB (`explore.md:49-63`) |
| D5 | Rename | `controllers/undo.js` (not `history.js`) | `history.js` | `controllers/history.js` exists = REST pagination (`history.js:1`) |
| D6 | Duplicate/restore | `drawing:duplicate`/`drawing:restore` bus commands handled in `drawings.js`, reusing `createDrawing` | new POST path in undo | Single write path (#68); delete/duplicate reuse `createDrawing` (`drawings.js:139`) |
| D7 | Menu | pure `context-menu-core.js` + `controllers/context-menu.js` ; JS-built DOM | inline `oncontextmenu` / static markup | CSP `script-src 'self'` (`middleware.py:28`); brief fixed |
| D8 | Keys | new binding only for Ctrl/Cmd+Z/Shift+Z/Y; per-tool letters deferred to `aria-keyshortcuts` | global letter router | Tree owns `v`/`l`/`s`; existing Escape/Delete are E2E-covered (`explore.md:189-205`) |
| D9 | Bus vocabulary | `drawing:duplicate`/`restore`/`created` are string literals (like `drawing:changed`/`delete`) | add to `EVENTS` | `chart-bus.js` stays byte-untouched; the drawing events were never in `EVENTS` (`explore.md:85-89`) |
| D10 | Add-indicator from menu | reuse `add-indicator-core.inactiveTokens` (`:18`) + the same `store.set`+`indicator:changed` write | re-implement registry math | Single source (`explore.md:207-213`) |

## Module Decomposition & Line Budget

New files (all ≤300):

| File | Kind | Lines | Exports / role |
|---|---|---|---|
| `market/history-core.js` | pure module | ~85 | `createHistory({limit})` |
| `market/context-menu-core.js` | pure module | ~80 | `menuModel`, `nextIndex`, `clampIndex` |
| `controllers/undo.js` | controller | ~150 | `createUndo({store,bus,host,config})` → `{clearForSwitch}` |
| `controllers/context-menu.js` | controller | ~170 | `createContextMenu({store,bus,host,config})` → `{attach,clearForSwitch}` |

Before → after on every touched module (baseline `wc -l`, verified):

| File | Now | Δ | After | What changes |
|---|---|---|---|---|
| `controllers/drawings.js` | 281 | +10 | **291** | `bus.on("drawing:duplicate")` (find row + `createDrawing(kind, clone(points), style)`, ~5); `bus.on("drawing:restore")` (~1); `createDrawing` `.then` emits `drawing:created {id,kind,points,style}` (~1); comment lines (~3) |
| `main.js` | 260 | +8 | **268** | imports +2, `createUndo`/`createContextMenu` +2, `contextMenu.attach()` in `buildChart`, `undo.clearForSwitch()`+`contextMenu.clearForSwitch()` in `switchTo` (`:161`) |
| `controllers/draw-toolbar.js` | 101 | +5 | **106** | `TOOL_KEYS` map (~2) + `btn.setAttribute("aria-keyshortcuts", …)` (~2) + comment (~1). No firing (D8) |
| `web/market/templates/market/chart.html` | 142 | +4 | **146** | 4 `modulepreload` links (2 cores + 2 controllers) |
| `web/market/views.py` | 584 | +4 | **588** | `MODULE_ALLOWLIST` +2 names, `CONTROLLER_ALLOWLIST` +2 names (`:44,69`) |
| `tests/web/test_market_ux.py` | 320 | +2 | 322 | `:146` `== 13` → `== 15`; served-test +2 names |
| `controllers/chart-bus.js` | 54 | **0** | 54 | **UNTOUCHED** — D9 string literals |
| `chart-store.js` | 61 | **0** | 61 | **UNTOUCHED** — no 12th key (D1) |
| `chart-host.js` | 267 | **0** | 267 | **UNTOUCHED** — reset routes via `scale:changed`→main (`main.js:204`) |
| `controllers/object-tree.js` | 299 | **0** | 299 | **UNTOUCHED** — menu is a sibling controller; delete/duplicate reuse bus events, tree re-renders from `drawings:changed` as today (`object-tree.js:285`) |
| `controllers/drawing-interaction.js` | 291 | **0** | 291 | **UNTOUCHED** — `context-menu.js` imports the exported pure `localPoint` (`:17`) / `pointerRows` (`:27`) and `grabHandle` from the core, building its own local `map()` (~10 lines inside the new file) |
| `controllers/smc.js` | 300 | **0** | 300 | **UNTOUCHED** — not on any F7 path |

**Ceiling proof (the three tight modules).** `object-tree.js` (299), `drawing-interaction.js` (291), `smc.js` (300) stay **byte-untouched**: the menu binds its OWN `contextmenu` listener on `#chart` (never edits `drawing-interaction.js`), duplicate/delete reuse the bus events the tree already consumes, and undo replays bus commands. Their byte-identity is proven by `git diff --stat` = empty for those paths in every slice, and by `test_module_size_guard.py` (`CEILING=300`, allowlist EMPTY, `:20,23`). The largest touched module is `drawings.js` at ~291 (9 under). **Fallback if `drawings.js` threatens 300**: move the `drawing:duplicate`/`drawing:restore` handling into `undo.js` (emit the exact `createDrawing` bus sequence) — a zero-line-in-`drawings.js` extraction, but it duplicates the POST body assembly, so it is deferred unless the budget moves.

## Layer Compliance

| New module | Layer | Allowed imports | DI |
|---|---|---|---|
| `history-core.js` | Pure core | nothing | — |
| `context-menu-core.js` | Pure core | nothing | — |
| `controllers/undo.js` | Controller | bus, store (`core→store/bus`, **never `main`**) | `create({store,bus,host,config})` |
| `controllers/context-menu.js` | Controller | `drawing-interaction.js` (pure exports), `drawing-interaction-core.js`, `add-indicator-core.js`, store, bus, host — **never `main`** | `create({store,bus,host,config})` |

`context-menu.js` is the only new controller→controller edge (it imports
`localPoint`/`pointerRows`, which are pure exports, `drawing-interaction.js:17,27`);
`drawings.js`/`main.js` keep their existing layers. No controller imports `main`
(`docs/architecture/chart-modules.md:16,20-21`). `main` imports both new
controllers (`main.js:73-105` pattern).

## Data Flow

**(a) one drag gesture → one history entry** (the persist boundary + before-snapshot):

    undo.js  bus.on("drawings:changed", {rows})      ← load/create/delete/restore
      └─▶ committed[row.id] = {kind, points, style}   (cache; NEVER removed)
    #chart pointermove (drawing-interaction.js:187)
      └─▶ drawing:changed {points, persist:false}      → drawings.js requestUpdate (NO PUT, NO record)
    #chart pointerup   (drawing-interaction.js:201)
      └─▶ drawing:changed {points, persist:true}
            ├─▶ drawings.js (first subscriber) → persistDrawing PUT  (drawings.js:113-119)
            └─▶ undo.js    (later subscriber) → push({op:"update", id,
                                   before:{points:committed[id].points}, after:{points}})
                                   committed[id].points = points

**(b) undo/redo of each op → HTTP verb + id re-mint**:

    op:"update"  undo → PUT {points|style: before}      (drawings:changed persist:true)
                 redo → PUT {points|style: after}        id stable
    op:"create"  undo → DELETE entry.id                 (drawing:delete)
                 redo → drawing:restore after → POST     → NEW id → entry.id patched
    op:"delete"  undo → drawing:restore before → POST   → NEW id → entry.id patched
                 redo → DELETE entry.id
    op:"create"(duplicate) ≡ create: undo DELETEs the cloned row, redo re-POSTs

**(c) right-click → hit-test → menu model → DOM → command**:

    document.body ⨝ #chart "contextmenu" (bound once, e.preventDefault)
      └─▶ p = localPoint(rect, e.clientX, e.clientY)
          hit = grabHandle(pointerRows(rows), p.x, p.y, map())      (drawing-interaction-core.js:85)
          row = rows.find(id===hit.id) | null
          bus.emit("drawing:selected", {id: hit ? hit.id : null})
          items = menuModel({hit, row, scaleMode: store.get().scaleMode})
          render <div role="menu" style="position:fixed;left/top=clientX/Y">
            <button role="menuitem" tabindex=-1 aria-keyshortcuts="…">…</button>
          focus first item (roving); ArrowUp/Down/Home/End via nextIndex()
          click/Enter → ACTION[item.id](row) → close + return focus to #chart

**(d) Ctrl/Cmd+Z → undo() → replay**:

    document "keydown" (undo.js, bound once)
      guard: (e.metaKey||e.ctrlKey) && target not INPUT/TEXTAREA/SELECT/contenteditable
      "z" & !shift  → undo()      : entry=history.undo(); replay(entry,"undo")
      "z" & shift | "y" → redo()  : entry=history.redo(); replay(entry,"redo")

**(e) symbol switch → clear()**:

    main.switchTo (main.js:161, symbolChanged) →
      drawings.clearForSwitch() (existing lines)
      undo.clearForSwitch()          → history.clear(); committed = {}
      contextMenu.clearForSwitch()   → close any open menu

## Interfaces / Contracts

```js
// market/history-core.js — pure, opaque ops, bounded, redo-clear rule.
export function createHistory({ limit } = {}) {
  // op = {op, id, before, after, ...}; the core NEVER inspects op fields.
  // push(op): undoStack.push(op); redoStack.length = 0        (redo-clear rule)
  //           while (undoStack.length > limit) undoStack.shift()   (default limit 50)
  // undo() -> entry|null : null if empty; else redoStack.push(entry = undoStack.pop()); return entry
  // redo() -> entry|null : null if empty; else undoStack.push(entry = redoStack.pop()); return entry
  // canUndo()/canRedo() -> bool
  // clear() : both stacks empty
  // size()  -> int (undo depth)
  // Stacks hold REFERENCES: the controller may mutate a returned entry's `id`
  // in place after an async re-mint; no core `patch()` API is needed.
}
```

```js
// market/context-menu-core.js — pure; item = {id,label,keyshortcut}.
export function menuModel({ hit, row, scaleMode }) {
  // row (a drawing under the cursor):
  //   [{id:"delete",label:"Delete",keyshortcut:"Delete"},
  //    {id:"duplicate",label:"Duplicate",keyshortcut:""}]
  //   + [{id:"reset-scale",label:"Reset scale",keyshortcut:""}] when scaleMode!=="linear"
  // empty chart:
  //   [({reset-scale} when scaleMode!=="linear"), {id:"add-indicator",label:"Add indicator"}]
  // Never throws; unknown hit → the empty-chart list.
}
export function nextIndex(count, index, delta)  // wrap; 0 when count<=0
export function clampIndex(count, index)        // 0..count-1
```

`replay(entry, dir)` lives in `undo.js`; `ACTION[id]` in `context-menu.js`.

## Undo/Server Consistency Contract (the hard part)

- **Op payloads**. `update`: `{op:"update", id, before:{points?|style?}, after:{points?|style?}}`
  (only the changed field). `create` (incl. duplicate): `{op:"create", id, after:{kind,points,style}}`.
  `delete`: `{op:"delete", id, before:{kind,points,style}}`. `after`/`before` are plain
  `points`/`style` copies (`JSON.parse(JSON.stringify)`).
- **Before-points cache**. `undo.js` keeps `committed[id] = {kind,points,style}`, updated on
  every `drawings:changed` (`drawings.js:51`). It is **add/update only, never removed**, so a
  deleted row's last-committed shape survives for `op:"delete".before`. Reset to `{}` only in
  `clearForSwitch`.
- **id re-mint**. A re-POST mints a new id. `replay` sets `replaying = entry` before emitting
  `drawing:restore`/`drawing:duplicate`; the async `drawing:created {id}` handler, while
  `replaying` is set, writes `replaying.id = id` (same reference already on the target stack)
  and clears `replaying`. No id is ever assumed stable across restore.
- **Restored row visibility**. `createDrawing`'s `.then` → `attachAllDrawings` publishes
  `drawings:changed` (`drawings.js:50-51`); `object-tree.js:285` and `drawing-interaction.js:67`
  react unchanged, so the restored row appears in the tree with its NEW id — no tree edit.
- **Re-entrancy guard**. `replaying !== null` makes the recorder skip `drawing:changed(persist)`,
  `drawing:delete`, and `drawing:created`, so a replay never pushes a new op. Emission is
  synchronous for `drawing:changed`/`drawing:delete`; `drawing:created` is async and is the
  restore/redo-create completion signal.
- **Cross-symbol safety**. `clearForSwitch` clears the stack AND `committed`, so no op keyed to
  a gone id can replay after a symbol switch (R14).

**State machine** (`undo()` / `redo()` return the entry; `replay` acts):

| top op | undo action | id after undo | redo action | id after redo |
|---|---|---|---|---|
| `update` | PUT `before` | stable | PUT `after` | stable |
| `create` | DELETE `id` | stable (row gone) | POST `after` | **new** |
| `delete` | POST `before` | **new** | DELETE `id` | stable (row gone) |
| `create`·duplicate | DELETE `id` | stable | POST `after` | **new** |

Optimistic note: the delete op is pushed on `drawing:delete` (before the DELETE resolves).
A failed DELETE already keeps the row silently (`drawings.js:171`); undo would then re-POST a
duplicate. Mitigation (deferred): emit `drawing:deleted` on fetch success and record there.

## Keyboard Router

Bound once at `createUndo` time on `document`:

```js
function onDocKey(e) {
  if (!(e.metaKey || e.ctrlKey)) return;
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA"
      || t.tagName === "SELECT" || t.isContentEditable)) return;
  const k = (e.key || "").toLowerCase();
  if (k === "z" && !e.shiftKey) { undo(); e.preventDefault(); }
  else if ((k === "z" && e.shiftKey) || k === "y") { redo(); e.preventDefault(); }
}
```

`metaKey||ctrlKey` covers Mac+Windows; redo accepts `Shift+Z` (Mac) or `Y` (Windows).

**Explicitly NOT touched** (no re-handle, no steal): `Escape`/`Delete`/`Backspace` on `#chart`
(`drawing-interaction.js:213-231`), `Escape` position draft (`drawings.js:244`), `Escape`
measure (`measure.js:183`), tree row `v`/`l`/`s`/`Delete` (`object-tree.js:137-142,201-205`),
draw-toolbar arrows/Home/End (`draw-toolbar.js:84`), chip arrows (`toolbar.js:63`).

## Context Menu Render + a11y

- **Markup** (JS-built, appended to `document.body`, `position:fixed`): `<div class="chart-context-menu" role="menu" aria-label="Chart actions">` with native `<button type="button" role="menuitem" tabindex="-1" aria-keyshortcuts="…">` per item. No inline `on*` (CSP `script-src 'self'`).
- **Roving focus**: first item `tabindex="0"` and focused on open; ArrowUp/Down/Home/End via `nextIndex`/`clampIndex`; Enter/Space native activation.
- **Focus trap**: `Tab`/`Shift+Tab` are handled to wrap within the item list (`preventDefault`); `Escape` closes and **returns focus to `#chart`** (`el.focus()`, the container already has `tabindex="0"`).
- **Close**: item activation, `Escape`, outside `pointerdown`, `clearForSwitch`.
- **Placement**: fixed at `clientX`/`clientY`; a right/bottom overflow clamp keeps it on-screen.
- **CSS tokens** (`theme.css`): `.chart-context-menu` uses existing `--surface`, `--border`, `--fs-3`, `--radius`; sits above the chart via `z-index`. No new color literals (design-system).

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (node) | `history-core`: push/undo/redo/canUndo/canRedo/clear/size, redo-clear on push, bound-50 drop, empty→null, LIFO order, reference-patch survives redo; `context-menu-core`: `menuModel` row vs empty vs non-linear-scale lists, never-throws; `nextIndex`/`clampIndex` wrap+clamp | `node --test "tests/js/**/*.test.js"` (new `history-core.test.js`, `context-menu-core.test.js`) |
| Controller pure helpers | `draw-toolbar` `aria-keyshortcuts` map is exported/assertable; replay/op builder as a pure function if extracted | `tests/js/*.test.js` (mirror `drawing-interaction-controller.test.js`) |
| Integration (pytest) | allowlists `== 15`; both cores served JS; `+2` controllers served; `STORE_KEYS == 11`; seam 8 keys; import-graph resolves new edges | `test_market_ux.py:146`, `chart-store.test.js` |
| E2E | drag → exactly ONE PUT then `Ctrl+Z` → a second PUT with prior points; menu `contextmenu` on a row shows Delete/Duplicate; menu Duplicate → captured POST then Undo → captured DELETE; menu Delete → DELETE then Undo → captured re-POST (new id); reset-scale emits `scale:changed` (no PUT); `setData` spy green; readiness-gated `_wait_ready` (`e2e:563`), DOM+network only, never pixels (#149) | `test_market_e2e.py` (mirrors `:1286-1365`) |
| Guard | no module >300 (esp. `smc.js`=300, `object-tree.js`=299, `drawing-interaction.js`=291) | `test_module_size_guard.py` |

## Risks & Mitigations

Explore §6 carried: **R1** 300-ceiling — three tight modules byte-untouched, largest touched `drawings.js` ~291; **R2** 8-key seam (`main.js:57-66`) — F7 adds NO seam key, asserted via DOM/bus; **R3** `STORE_KEYS` 11 — no key; **R4** #68 — menu/undo replay existing bus commands, `setData` spy; **R5** drag coalescing — record ONLY on `persist:true` (`drawing-interaction.js:201`); **R6** undo/server id re-mint — operation stack + `replaying` guard + `drawing:created` patch; **R7** R14 — `for_user` CRUD only, `clear()` on switch; **R8** shortcut conflicts — only Ctrl/Cmd+Z/Shift+Z/Y, tree keys untouched; **R9** patch 100% — node tests for both cores + controller helpers + E2E; **R10** E2E flake — readiness gate, DOM+network. **New**: **R11** optimistic delete record (failed DELETE → duplicate on undo) — accepted, mitigation `drawing:deleted` deferred; **R12** two `#chart` listeners (`contextmenu` vs `drawing-interaction` pointer) — different event types, no conflict.

## Migration / Rollout (Feature Branch Chain)

Over the 400-line budget (`chained-pr`), tracker branch `feat/f7-chart-shortcuts`:

- **S1** — `history-core.js` + `context-menu-core.js` + node tests (revert = delete 2 files; no app impact, no allowlist yet since unimported).
- **S2** — `controllers/undo.js` + `drawing:duplicate`/`drawing:restore`/`drawing:created` in `drawings.js` + `Ctrl/Cmd+Z` + main wiring + allowlist 13→14 + E2E (revert = revert slice; stack is in-session only).
- **S3** — `controllers/context-menu.js` + `draw-toolbar` `aria-keyshortcuts` + allowlist 14→15 + `chart.html` preloads + menu CSS + `test_market_ux` count + E2E (revert = revert slice).

No migration, no `src/`, no dependency, no CSP change; each slice independently revertible.

## Open Questions

None blocking. Explore §7 forks resolved by the brief: Q1→D1 (store stays 11), Q2→D2
(OUT), Q3→D8 (deferred letters), Q4→duplicate copies verbatim (clone; offset not required),
Q5→`limit` 50 (bounded), Q6→empty menu = reset-scale + add-indicator only.
