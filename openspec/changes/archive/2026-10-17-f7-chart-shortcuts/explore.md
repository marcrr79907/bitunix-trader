# Exploration: f7-chart-shortcuts

Issue #120, Fase F7. Branch `develop` @ `0c2e3e8`. Read-only — no code changed,
no branch created. Builds on the archived F5 chain
(`openspec/changes/archive/2026-10-16-f5-chart-toolbar/`) and F6
(`openspec/changes/archive/2026-10-17-f6-measure-position/`). F0 + F4 done.

Goal: professional interaction — a right-click **context menu** on the chart, an
**undo/redo history** of drawing operations, and **keyboard shortcuts** (`Del`,
`Esc`, `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z` or `Y`, plus per-tool shortcuts).

---

## 1. Problem framing

Three distinct TradingView instruments, three different models:

- **Context menu** — a *transient view* over the current target. It is not state;
  it is a function of `(target-under-cursor, selection)` → a list of actions.
  TradingView shows different items for a drawing ("Delete", "Duplicate",
  "Bring forward") than for empty chart ("Reset scale", "Add indicator"). The
  menu must be DOM (CSP), focus-trapped, and keyboard-navigable.
- **Undo/redo** — a *deterministic operation stack*, NOT pixels. TradingView's
  undo reverses the last user **operation** (create / move / delete / style
  change); a drag that emitted 200 `pointermove` frames is ONE operation, not
  200. This is the crux: today the drag path already coalesces *rendering* to one
  PUT (`drawings.js:113` `if (!p.persist) return`), but a raw "record every
  `drawing:changed`" undo stack would record every frame. The stack must model
  **operations**, so it needs a begin/commit boundary around a gesture.
- **Shortcuts** — a *router* over keys → commands. Today keys are scattered:
  `drawing-interaction.js:213` (Escape/Delete/Backspace on `#chart`),
  `drawings.js:244` (Escape for a position draft on `#chart`), `measure.js:183`
  (Escape on `#chart`), `object-tree.js:259` (roving nav + `v`/`l`/`s`/Delete on
  a tree row), `draw-toolbar.js:84` (arrows/Home/End), `toolbar.js:63` (chip
  arrows). F7 must add a layer WITHOUT re-handling an existing key or stealing a
  key the tree already owns.

**What "deterministic stack in the store" must mean here.** The issue says the
stack lives "en el store". Read literally that is a 12th `STORE_KEYS` slot — but
the store is **config/UI state only** (#68, `chart-store.js:1-12`) and every
`store.set` notifies ALL subscribers (`chart-store.js:47`), which today include
`object-tree.js:295 render`, `converters`/consumers in `draw-toolbar.js:98`,
`measure.js:192`, `draw-toolbar` sync, and `drawings.js:231`. Pushing an undo
frame would re-render the whole object tree on every drawing edit — an O(n) side
effect for a stack mutation that touches no config. The right reading of
"deterministic stack" is a **pure, node-testable stack core owned by a
controller**, not a store key (§3 Fork 1).

**Server consistency (the real hard problem).** All drawing mutations already
funnel through the bus and land as HTTP in `drawings.js`:

| Operation | Entry | HTTP | Undo needs |
|---|---|---|---|
| create | `drawings.createDrawing` `drawings.js:139` | `POST` → new id | re-POST on redo, DELETE on undo |
| move / style | `bus.on("drawing:changed")` `drawings.js:98` → `persistDrawing` `drawings.js:131` | `PUT` | PUT the prior points/style |
| delete | `bus.on("drawing:delete")` `drawings.js:125` → `deleteDrawing` `drawings.js:162` | `DELETE` | re-POST (id is gone; a new id is minted) |

So undo/redo is NOT a local-only revert: **undone deletes must re-create rows
server-side (new id), and undone creates must DELETE rows**. The stack must store
the *operation* (kind + points + style) not just a row snapshot, so it can replay
it through the existing `drawings.js` paths. A local-only stack that just patches
`currentDrawings` would silently diverge from the DB. This is the top design
constraint.

---

## 2. Codebase map (exact files/functions, cited)

### The gesture layer (where the context menu attaches)
- `controllers/drawing-interaction.js` — DI factory, `#chart` pointer + keydown.
  `attach()` binds ONCE on the persistent `#chart` (`drawing-interaction.js:270-281`).
  Pure exports reused by tests/other modules: `localPoint` `:17`, `pointerRows`
  `:27`, `mergeStyle` `:36`. Selection state is a closure, published on
  `drawing:selected` `:145`. **291 lines — the tightest touched target (9 free).**
- `drawing-interaction-core.js` — `handlesFor` `:31`, `grabHandle` `:85`,
  `bodyHit` `:107`, `applyDrag` `:162`. Pure, 271 lines. A context-menu hit-test
  reuses `grabHandle(pointerRows(rows), x, y, map())` exactly like
  `onPointerDown` `drawing-interaction.js:158`.
- `controllers/drawings.js` — `createDrawing` `:139`, `deleteDrawing` `:162`,
  `persistDrawing` `:131`, `onChartClick` `:176`, `attachAllDrawings` `:37` +
  `bus.emit("drawings:changed")` `:51`. Owns the ONLY HTTP for drawings. 281 lines.

### The store / bus (undo candidate)
- `chart-store.js` — `STORE_KEYS` = **11** (`:13-27`), `set` notifies all
  subscribers (`:47`), `subscribe` `:52`.
- `chart-bus.js` — `EVENTS` frozen `:9-24`; drawing events used today are string
  literals, not in `EVENTS` (`drawing:changed`, `drawing:delete`,
  `drawing:selected`). A new `drawing:restored`/`history:changed` would follow
  that literal convention (or join `EVENTS`).

### Persistence (already CRUD-complete; NO server change needed)
- `views.py` — `api_drawings` GET/POST `:403`, `_post_drawing` `:438`,
  `api_drawing_detail` PUT/DELETE `:487`, `_put_drawing` `:506`. All
  `Drawing.for_user`-scoped (R14). Undo replays these three verbs unchanged.
- `views.py` — reset scale: F8 is a store key + `scale:changed` bus → `main`
  `host.setScaleMode` (`main.js:204-207`) + `savePreference({scale_mode})`. There
  is **no server "reset scale" endpoint**: scale is persisted per-user in
  `api_preference` (`views.py:328-334`, `_PREFERENCE_DEFAULTS.scale_mode`). So
  "reset scale" = set `store.scaleMode="linear"` + emit `scale:changed` (reuses
  the existing F8 path verbatim — single seam, no new code path).
- `views.py` — `MODULE_ALLOWLIST` = 21 names `:44-68`; `CONTROLLER_ALLOWLIST` =
  **13** `:69-85`. A new pure core MUST be added to `MODULE_ALLOWLIST` and a new
  controller to `CONTROLLER_ALLOWLIST`, or its import 404s and the chart blanks
  (`test_market_ux.py:127,146` asserts `len(...) == 13`, so that test MUST be
  bumped to the new count).

### Host
- `chart-host.js` — `getChart` `:171`, `getCandleSeries` `:172`, `setScaleMode`
  `:216`, seam written at `:152-154`. **267 lines; do NOT touch** (scale reset
  routes through main, not the host).

### Existing key handling to avoid double-handling (grep `keydown`)
`draw-toolbar.js:84`, `object-tree.js:259`, `measure.js:206`,
`drawing-interaction.js:278`, `toolbar.js:63`, `drawings.js:244`. **All are
`#chart`- or row-scoped.** Nothing binds `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z`, or
`contextmenu` anywhere. The `v`/`l`/`s` letter keys are ALREADY owned by the
object tree rows (`object-tree.js:137-142,201-205`).

### Tests to mirror
- Pure: `tests/js/drawing-interaction-controller.test.js` (imports the pure
  helpers from the controller), `drawing-interaction-core.test.js`,
  `object-tree.test.js`, `draw-toolbar.test.js`, `chart-store.test.js`.
- E2E: `tests/web/test_market_e2e.py` — `_wait_ready` `:563`, delete `:1069`,
  keyboard delete `:1549`, escape `:1580`, drag single-PUT `:1309`, click-empty
  noop `:1270` (DOM + network interception, never pixels). `test_market_ux.py`
  `:146` allowlist count.
- Ceiling: `test_module_size_guard.py:20` `CEILING=300`, `:23` allowlist EMPTY.

---

## 3. Design options (real forks, with recommendations)

### Fork 1 — Undo/redo home
- **(a) 12th `STORE_KEYS` slot `history`** — literal issue reading. REJECT:
  `store.set` notifies every subscriber (`chart-store.js:47`) → object-tree
  re-renders (`object-tree.js:295`) on every stack push; the store is documented
  config/UI-only (#68); an operation stack is neither. It would also violate the
  frozen-vocabulary discipline that every prior F-use respected (F6 D3 added NO
  key, `design.md` F6 table).
- **(b) Closure in a new controller** — stack array + methods live only in the
  controller. Works, but the stack logic (bounded, coalescing, redo-clearing) is
  then untestable without a browser.
- **(c) Pure `history-core.js` + `controllers/undo.js` owner** — the stack is a
  pure factory (`createHistory({limit}) → {push, undo, redo, canUndo, canRedo,
  clear, size}`), node-tested; the controller owns it, subscribes to the mutation
  events, and replays through `drawings.js`'s existing bus commands.

**RECOMMEND (c).** "Deterministic stack" is exactly a pure core: model the
operation (`{op:"create"|"update"|"delete", id, before, after}`), test the
coalescing and redo-clear rules headlessly, and keep the store frozen at 11 keys.

### Fork 2 — Naming collision (HARD)
`controllers/history.js` ALREADY EXISTS = REST kline history + left-edge
pagination (`history.js:1`). The new controller MUST NOT be `history.js`. Use
`controllers/undo.js` (core `history-core.js` is a NEW pure module, no clash).

### Fork 3 — Undo scope + drag coalescing
- Undoable operations: **create, move/drag, delete, duplicate, style change**
  (the issue's create/move/delete plus duplicate from the menu). Reset-scale and
  add-indicator are NOT drawing ops — leave them out of the stack (they are own
  commands; keeping the stack drawing-scoped matches the issue wording
  "operaciones de dibujo").
- **Coalescing a drag into ONE op.** The drag emits `drawing:changed` per frame
  with `persist:false`, and exactly ONE with `persist:true` at gesture end
  (`drawing-interaction.js:187,201`). The undo controller records on the
  **`persist:true`** event only, capturing the row's pre-drag points. Pre-drag
  points are not in the event → the controller must cache the last *committed*
  points per id (snapshot on `drawings:changed`, compare on `persist:true`). One
  frame boundary → one stack entry. This is the single most important rule and
  the reason the stack belongs in a core with an explicit `commit()`.

### Fork 4 — Context menu structure
- Pure `context-menu-core.js`: `menuModel({target, row, selection, isPosition})`
  → `[{id:"delete",label,shortcut},{id:"duplicate",...},{id:"reset-scale",...},
  {id:"add-indicator",...}]`. Which items for which target: a drawing row →
  delete/duplicate (+reset-scale when scale is non-linear); empty chart →
  reset-scale/add-indicator. Node-testable.
- `controllers/context-menu.js`: binds `contextmenu` on `#chart` (binds once, like
  `drawing-interaction.attach`), hit-tests via `grabHandle(pointerRows(rows),…,
  map())`, emits `drawing:selected` when a row is hit, renders a DOM
  `role="menu"` at the cursor, manages roving focus + `Escape`/`Enter`/arrows,
  returns focus on close. **No inline `oncontextmenu`** (CSP `script-src 'self'`,
  `web/config/middleware.py:28` — no `unsafe-inline`).
- Duplicate = `createDrawing(row.kind, clone(row.points), row.style)` via a new
  small `bus.emit("drawing:duplicate", {id})` handled in `drawings.js` (or call
  the existing `createDrawing` through a thin bus command). Deletion reuses
  `drawing:delete` (`drawings.js:125`) — no new delete path.

### Fork 5 — Shortcut registry: one router vs scattered
- Existing keys are already scattered and scoped (`#chart` for Escape/Delete,
  row-scoped for the tree). A big-bang router would risk double-handling.
- **RECOMMEND a single new `controllers/undo.js` keyboard binding for
  `Ctrl/Cmd+Z` and `Ctrl/Cmd+Shift+Z` (or `Y`) only** — nothing binds those today
  (verified §2), so no conflict. Bind on `document` so undo works regardless of
  focus (TradingView parity), guarded by `if (e.metaKey||e.ctrlKey)`. Keep the
  EXISTING Escape/Delete on `#chart` untouched (they already work and are E2E-
  covered at `:1549,:1580`). Do NOT route them through the new controller — that
  would be churn over working, tested behavior.
- **Per-tool letter shortcuts: DEFER or scope to `#chart` focus only.** The
  object tree already owns `v`/`l`/`s` (`object-tree.js:137-142,201-205`); a
  global letter router would collide. Recommend documenting per-tool shortcuts as
  `aria-keyshortcuts` on the draw-toolbar buttons and firing them only when
  `document.activeElement` is inside `#chart`. Flag as an open question (§7).
- Mac vs non-Mac: use `e.metaKey || e.ctrlKey` (covers both), and for redo accept
  `Ctrl/Cmd+Shift+Z` OR `Ctrl/Cmd+Y` (Windows convention, per the issue).

### Fork 6 — Add-indicator from the menu (reuse, no duplication)
F5 already ships `chart-indicator-add` via `add-indicator-core.createAddIndicator`
(`add-indicator-core.js:30`) which sets `store.indicators` and emits
`indicator:changed` (`:78-79`). The menu's "Add indicator" item MUST reuse that
seam: open the SAME affordance (or emit the same store+event). Do NOT re-implement
the REGISTRY-minus-membership logic. `inactiveTokens` is exported `:18` and can
feed a small submenu list without touching `object-tree.js`.

---

## 4. Pure-core split (CRITICAL for the 300-line ceiling)

New files (all ≤300; allowlist empty `test_module_size_guard.py:23`):

| File | Kind | Est. lines | Role |
|---|---|---|---|
| `market/history-core.js` | pure **module** | ~80 | `createHistory({limit})` → push/undo/redo/canUndo/canRedo/clear; operation model + redo-clear rule |
| `market/context-menu-core.js` | pure **module** | ~90 | `menuModel(target,row,selection,scaleMode)` → item list; focus-index helpers |
| `controllers/undo.js` | **controller** | ~150 | owns the stack; subscribes `drawing:changed`(persist)/`drawing:delete`/`drawings:changed`; binds Ctrl/Cmd+Z; replays via bus |
| `controllers/context-menu.js` | **controller** | ~180 | DOM `role="menu"`, hit-test, focus trap, invokes the replayed commands |

Both new modules MUST join `MODULE_ALLOWLIST` (`views.py:44`) and both new
controllers `CONTROLLER_ALLOWLIST` (`views.py:69`), and `test_market_ux.py:146`
(`== 13`) MUST become `== 15`, plus the F6-style served test (`:159`).

Touched existing modules — before → after:

| File | Now | Δ | After | What changes |
|---|---|---|---|---|
| `controllers/object-tree.js` | 299 | **0** | 299 | **UNTOUCHED** — menu/undo never edit it (duplicate/delete reuse the existing bus events `object-tree.js:123,148`) |
| `controllers/drawing-interaction.js` | 291 | **0** | 291 | **UNTOUCHED** — the context menu is its OWN controller binding `contextmenu` on `#chart`; it imports the pure `pointerRows`/`localPoint` (`:17,:27`) rather than growing this file |
| `controllers/drawings.js` | 281 | +~10 | ~291 | one `bus.on("drawing:duplicate")` branch reusing `createDrawing`; a restored-delete re-POST reuses `createDrawing` — no new HTTP |
| `main.js` | 260 | +~6 | ~266 | import + `createUndo`/`createContextMenu`; pass `drawings` handles if needed; no buildChart change |
| `chart-store.js` | 61 | **0** | 61 | **UNTOUCHED** — no 12th key (Fork 1) |
| `chart-bus.js` | 54 | +~2 | ~56 | optional: add `drawingDuplicate` to `EVENTS` (or use a string literal as today) |
| `chart-host.js` | 267 | **0** | 267 | **UNTOUCHED** — reset scale routes through the existing `scale:changed` → main |

**Ceiling proof.** The three tightest modules are the three that must stay small:
`object-tree.js` (299) is byte-untouched; `drawing-interaction.js` (291) is
byte-untouched because the menu is a sibling controller reusing its exported pure
helpers; `drawings.js` (281) grows by ~10 for the duplicate/restore bus branch and
lands at ~291 ≤ 300. `smc.js` (300) is untouched. No extraction is required, but
if `drawings.js` threatens the ceiling, the duplicate branch can live in the undo
controller (emit the exact bus sequence `createDrawing` would) — a zero-line
fallback.

---

## 5. a11y + CSP

- CSP (`web/config/middleware.py:28`, `script-src 'self'` — no `unsafe-inline`):
  the menu is DOM built by JS; the `contextmenu` listener calls `e.preventDefault()`
  and is added with `addEventListener`, never an inline `oncontextmenu`.
- Menu: `role="menu"` container, each item a native `<button role="menuitem">`
  (or `role="menuitem"` on focusable elements), `aria-label` per item, roving
  focus with ArrowUp/Down/Home/End, `Enter`/`Space` to activate, `Escape` to
  close and **return focus** to `#chart` (mirrors the F5 object-tree roving
  pattern `object-tree.js:243-281` and the settings dialog focus return
  `e2e:2560`).
- `aria-keyshortcuts` on menu items (`Delete`, `Ctrl+Z`, …) advertises bindings —
  same idiom as `object-tree.js:58`.
- Shortcuts documented in a help affordance / the specs `keyboard` requirement.
  Undo/redo state changes announce via the existing `aria-live` region style
  (`#rsi` / `#measure-readout`, `design-system/spec.md`) — optional, low priority.

---

## 6. Risk list

1. **300-line ceiling** (`test_module_size_guard.py:20,23`): mitigated by keeping
   the two new pure cores + two new controllers and touching `drawings.js`/`main.js`
   only; `object-tree.js` and `drawing-interaction.js` stay byte-untouched (§4).
2. **Seam freeze** — 8 keys (`main.js:57-66`). F7 adds NO seam key (undo/menu are
   DOM+store-command driven); a menu/stack test seam is not needed.
3. **STORE_KEYS 11→12?** — Fork 1 resolves NO (stays 11). If reviewers insist on
   the literal "en el store", the alternative is a 12th key, which forces
   `chart-store.test.js` and the R14 delta spec to change and re-renders the tree
   on every push — flag as open question.
4. **Undo/server consistency** — undone delete re-mints an id (re-POST), undone
   create issues DELETE, undone move PUTs prior points. The stack must store the
   OPERATION, and a symbol switch must `clear()` the stack (a stack entry for a
   gone id is invalid) — mirror `clearForSwitch` (`main.js:161-167`).
5. **Shortcut conflicts** — `v`/`l`/`s` owned by object-tree rows
   (`object-tree.js:137-142,201-205`); Escape/Delete owned by `#chart`
   (`drawing-interaction.js:278`, `drawings.js:244`, `measure.js:206`). New
   bindings limited to Ctrl/Cmd+Z / Shift+Z / Y → no overlap. Per-tool letter
   shortcuts deferred to avoid collision (§3 Fork 5).
6. **#68 single write path** — the context menu must not call `setData`/`update`;
   duplicate/restore go through `createDrawing` (POST) + `attachAllDrawings`
   (`drawings.js:37`), and reset-scale through `scale:changed` (option-only).
7. **R14** — undo replays only `for_user`-scoped CRUD; a symbol switch clears the
   stack so no cross-symbol id can be replayed.
8. **E2E flakiness (class C #149)** — new E2E must be readiness-gated
   (`_wait_ready`, `e2e:563`) and DOM+network based, never pixel-based; annotate
   the WS-flake class like `e2e:1348`.
9. **Drag coalescing** — recording per-frame instead of per-gesture is the top
   correctness risk; the persist-flag boundary (`drawing-interaction.js:187,201`)
   is the seam to hook.
10. **Patch coverage 100%** (repo invariant) — new cores need node tests
    (`history-core`, `context-menu-core`), the two controllers need pure-helper
    tests where possible (mirroring `drawing-interaction-controller.test.js`) plus
    E2E.

---

## 7. Open questions (real forks for proposal/design)

1. **History home**: confirm Fork 1(c) — pure `history-core.js` + `controllers/undo.js`,
   store stays 11 keys. If the issue's "en el store" is taken literally, does the
   project accept a 12th `STORE_KEYS` slot despite #68 and the tree re-render cost?
2. **Undo scope**: are reset-scale and add-indicator IN or OUT of the undo stack?
   Recommendation: OUT (drawing ops only).
3. **Per-tool letter shortcuts**: ship at all, or document `aria-keyshortcuts` and
   scope firing to `#chart` focus only (the tree owns `v`/`l`/`s`)?
4. **Duplicate placement**: does a duplicated drawing offset by a small Δ (TradingView
   does), or copy verbatim?
5. **Stack depth**: bound the stack (e.g. 50 ops) or unbounded in-session?
6. **Menu on right-click of empty chart**: reset-scale + add-indicator only, or also
   a "paste"/"clear all" (avoid scope creep — recommend the two the issue names).
