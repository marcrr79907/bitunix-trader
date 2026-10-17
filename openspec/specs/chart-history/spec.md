# chart-history Specification

## Purpose

In-session undo/redo for drawing **operations** (issue #120, F7). New capability —
no prior spec. The stack models operations, not pixels: one user gesture = one
entry. It is a pure core (`market/history-core.js`) owned by a controller
(`controllers/undo.js`, named so because `controllers/history.js` already owns REST
pagination). Server-coupled replay through `drawings.js`'s existing verbs keeps the
DB consistent. NOT a `STORE_KEYS` slot (#68, `chart-store.js:13-27`). Delivered on
`develop`; the verify-report C1 (a `chart-toolbar` letter-router gap, not this
capability) was resolved in the S4/UI slices, and the #200/#201/#205/#209
hardening landed in the S4 and concurrency slices.

## Requirements

### Requirement: R1 — Operation stack

The pure `market/history-core.js` MUST export `createHistory({limit}) ->
{push, undo, redo, canUndo, canRedo, clear, size}`. The stack MUST be a bounded
(default 50) LIFO of operation records `{op, id, before, after}` where `op` ∈
`create|move|delete|duplicate|style`. `push` MUST clear the redo list. `undo` MUST
return the popped record and move it to the redo list; `redo` MUST return the
reversed record and move it back. The core MUST be pure (no DOM, no imports, no
network), so it runs under `node --test`. The core MUST be opaque — it MUST NOT
inspect the record fields, only move references, so the controller MAY mutate a
returned entry's `id` in place after an async re-mint.

#### Scenario: Push then undo then redo round-trips

- GIVEN an empty history
- WHEN `push({op:"create",id:1})`, `undo()`, `redo()` run
- THEN `canUndo`/`canRedo` transition false→true→false→true and `size` returns to 1
- AND the redo returns the same record moved back

#### Scenario: New push clears redo

- GIVEN an undone operation (redo available)
- WHEN a new `push` runs
- THEN `canRedo()` is false and `size` grows by exactly 1

#### Scenario: Bounded at the limit

- GIVEN `createHistory({limit:50})`
- WHEN 51 pushes run
- THEN `size() === 50` and the oldest record was dropped

### Requirement: R2 — Coalescing boundary (one gesture = one entry)

A drag emits many `drawing:changed` with `persist:false` and exactly ONE with
`persist:true` at gesture end (`drawing-interaction.js:187,201`). The controller
MUST record an entry ONLY at the `persist:true` boundary. The pre-drag `before`
points MUST come from a cached last-committed snapshot per id, refreshed on
`drawings:changed` (`drawings.js:51`), NOT from the per-frame event. The committed
cache MUST be synced on a replay's own change too, so it sits at the reverted value
and a following gesture records the correct `before` (#200).

#### Scenario: One drag yields one entry

- GIVEN a committed drawing `d` with cached points `P0`
- WHEN a drag emits 200 `persist:false` frames then one `persist:true`
- THEN exactly one entry is pushed, with `before == P0` and `after ==` the final points

#### Scenario: Per-frame persistence is rejected

- GIVEN a drag in progress
- WHEN only `persist:false` frames are observed
- THEN the stack `size` is unchanged (no entry recorded)

#### Scenario: Committed cache survives an undo

- GIVEN a committed drawing `d`
- WHEN a move is undone (the replay PUTs `before`) and then a new gesture records
- THEN the new entry's `before` is the reverted points, not the stale pre-undo points (#200)

### Requirement: R3 — Server-coupled replay

Undo/redo MUST replay through `drawings.js`'s existing HTTP verbs, never patch
`currentDrawings` locally. The pure `replayOps(entry, dir)` MUST map: `update` →
`drawing:changed {persist:true}` with the `before`/`after` side; `create` (incl.
`duplicate`) → undo `drawing:delete`, redo `drawing:restore`; `delete` → undo
`drawing:restore`, redo `drawing:delete`. `undo(delete)` MUST re-POST (a new id is
minted); `undo(create)` MUST DELETE; `undo(move|style)` MUST PUT the `before`
points/style; `redo` MUST mirror. A local-patch-only implementation MUST fail the
E2E scenario.

#### Scenario: Undo a delete re-POSTs a new id

- GIVEN a deleted drawing recorded as `{op:"delete"}`
- WHEN undo runs
- THEN a `POST /market/api/drawings` is captured and the restored row carries a NEW id (E2E network intercept)

#### Scenario: Undo a create DELETEs

- GIVEN a created drawing recorded as `{op:"create",id:N}`
- WHEN undo runs
- THEN a `DELETE /market/api/drawings/<N>` is captured

#### Scenario: Undo a move PUTs the prior points

- GIVEN a moved drawing with `before` points
- WHEN undo runs
- THEN a `PUT /market/api/drawings/<id>` with the `before` points is captured

#### Scenario: Local-patch-only fails

- GIVEN an implementation that mutates `currentDrawings` without HTTP
- WHEN the undo-delete scenario runs
- THEN the captured-POST assertion fails (the DB row is not restored)

### Requirement: R4 — Lifecycle

On a SYMBOL switch the controller MUST `clear()` the stack (a symbol-scoped id is
invalid after the switch; mirror `clearForSwitch` `main.js:161-167`). The stack
scope MUST be in-session only and MUST NOT survive a page reload. `clearForSwitch`
MUST also reset the committed cache, so no op keyed to a gone id can replay after
the switch (R14).

#### Scenario: Symbol switch clears the stack

- GIVEN a non-empty stack on `BTCUSDT`
- WHEN `switchTo("ETHUSDT", ...)` runs
- THEN `size() === 0` and `canUndo()` is false

#### Scenario: Reload starts empty

- GIVEN a non-empty stack
- WHEN the page reloads
- THEN the new stack is empty (nothing persisted)

### Requirement: R5 — Keyboard router

The controller MUST bind on `document` for `Ctrl/Cmd+Z` (undo) and
`Ctrl/Cmd+Shift+Z` OR `Ctrl/Cmd+Y` (redo), guarded by `e.metaKey || e.ctrlKey`, and
MUST `preventDefault`. It MUST NOT re-handle `Escape` or `Delete` (owned by
`#chart`, `drawing-interaction.js:213-231`), and MUST NOT fire when a focused
element is a text input, textarea, select, or contenteditable.

#### Scenario: Ctrl+Z undoes

- GIVEN a non-empty stack
- WHEN `Ctrl+Z` (or `Cmd+Z`) fires on `document`
- THEN undo runs and the event default is prevented

#### Scenario: Shift+Z and Y redo

- GIVEN an undone operation
- WHEN `Ctrl+Shift+Z` or `Ctrl+Y` fires
- THEN redo runs

#### Scenario: Escape and Delete untouched

- GIVEN focus on `#chart`
- WHEN `Escape` or `Delete` fires
- THEN the router ignores it (the existing `#chart` handler owns it)

#### Scenario: Text input is exempt

- GIVEN focus in a text input
- WHEN `Cmd+Z` fires
- THEN the router does not undo (native edit behavior preserved)

### Requirement: R6 — Replay safety and feedback

While a replay is in flight the controller MUST guard re-entrancy: a
`replaying` marker MUST suppress recording of the replay's own `drawing:changed`/
`drawing:delete`, and MUST patch the recorded entry's `id` from the async
`drawing:created` (the restore re-mints the id). A failed restore MUST emit
`drawing:create-failed` and clear the guard so undo is not wedged for the session
(#201). A second undo/redo press while a replay is in flight MUST be ignored, so
it cannot mutate the stack or overwrite the guard's entry (#209). Each successful
undo/redo MUST announce the operation ("Undo"/"Redo") in the polite
`#history-status` `aria-live` region (`chart.html:60`), one write per op (#205).

#### Scenario: A replay never records a new op

- GIVEN a replay emitting `drawing:changed`/`drawing:delete`
- WHEN the recorder observes those events
- THEN no new entry is pushed (the `replaying` guard suppresses recording)

#### Scenario: Undo in flight ignores a second press

- GIVEN an async restore replay awaiting `drawing:created`
- WHEN a second `Ctrl+Z` / `Ctrl+Y` fires before it settles
- THEN it is ignored (no stack mutation, the guard's entry is preserved) — #209

#### Scenario: Failed restore unblocks undo

- GIVEN a restore whose POST fails
- WHEN `drawing:create-failed` fires
- THEN the guard clears and a later undo/redo is not ignored — #201

#### Scenario: Undo and redo announce

- GIVEN a non-empty stack and undo available
- WHEN `Ctrl+Z` undoes (or a redo runs)
- THEN `#history-status` (`aria-live="polite"`) carries "Undo" (or "Redo") — #205

### Requirement: R7 — Constraints

The change MUST keep `STORE_KEYS` at 11 (pure core, no 12th key;
`chart-store.js:13-27`), keep `window.marketChart` at its 8 frozen keys, keep every
module ≤300 lines, keep `Content-Security-Policy` unchanged, and replay only
`for_user`-scoped CRUD (R14, `views.py:403,487`). The controller MUST live in
`CONTROLLER_ALLOWLIST` and the core in `MODULE_ALLOWLIST`.

#### Scenario: Store stays 11 keys

- GIVEN `chart-store.js`
- WHEN `STORE_KEYS` is read
- THEN exactly 11 names exist and no `history` key was added

#### Scenario: Replay is user-scoped

- GIVEN undo of any operation
- WHEN the verb executes
- THEN it routes through `Drawing.for_user(request.user)` (cross-user id → 404)

#### Scenario: Size and CSP

- GIVEN the delivered modules and headers
- WHEN the guard and CSP checks run
- THEN each module is ≤300 lines and `Content-Security-Policy` equals the prior value
