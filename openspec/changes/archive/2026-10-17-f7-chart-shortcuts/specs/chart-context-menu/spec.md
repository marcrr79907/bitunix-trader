# chart-context-menu Specification

## Purpose

Right-click context menu over the chart (issue #120, F7): a *transient view* over
`(target-under-cursor, selection)` → an action list. New capability — no prior
spec. Menu logic is a pure core (`market/context-menu-core.js`); the DOM
`role="menu"`, hit-test, and focus trap live in `controllers/context-menu.js`, a
sibling of `drawing-interaction.js` (which stays byte-untouched). JS-built DOM
only (CSP `script-src 'self'`, `middleware.py:28` — no inline `oncontextmenu`).

## ADDED Requirements

### Requirement: R1 — Menu model (pure)

The pure `market/context-menu-core.js` MUST export
`menuModel(target, row, selection, scaleMode)` returning an ordered list of items
`{id, label, keyshortcuts}`. Items by target: a drawing row → `delete`,
`duplicate`; empty chart → `reset-scale`, `add-indicator`; `reset-scale` MUST be
included only when `scaleMode` is non-linear. The core MUST be pure (no DOM, no
imports) and node-testable.

#### Scenario: Drawing row yields delete and duplicate

- GIVEN `target="drawing"` with a row
- WHEN `menuModel` runs
- THEN the items are exactly `delete` then `duplicate`

#### Scenario: Empty chart yields reset-scale and add-indicator

- GIVEN `target="chart"`, `scaleMode="log"`
- WHEN `menuModel` runs
- THEN the items include `reset-scale` and `add-indicator`

#### Scenario: reset-scale only when non-linear

- GIVEN `scaleMode="linear"`
- WHEN `menuModel` runs for an empty chart
- THEN `reset-scale` is absent and `add-indicator` remains

### Requirement: R2 — DOM menu and CSP

The controller MUST build the menu as DOM with `role="menu"` and native
`role="menuitem"` items, MUST bind `contextmenu` ONCE on `#chart` via
`addEventListener` with `e.preventDefault()`, and MUST NOT use an inline
`oncontextmenu` or inline `<script>`. The menu MUST be removed from the DOM on close.

#### Scenario: Menu is JS-built DOM

- GIVEN the rendered `/market/` page
- WHEN the markup and handlers are inspected
- THEN no inline `oncontextmenu` exists and the menu (when open) is a `role="menu"` node with `role="menuitem"` children

#### Scenario: Right-click opens at cursor

- GIVEN an empty chart
- WHEN `contextmenu` fires on `#chart`
- THEN the default is prevented and a `role="menu"` node appears

### Requirement: R3 — a11y and keyboard operation

While the menu is open: ArrowUp/Down and Home/End MUST move roving focus across
items, Enter/Space MUST activate the focused item, and `Escape` MUST close the menu
and return focus to `#chart`. Each item MUST carry an accessible name and an
`aria-keyshortcuts` attribute.

#### Scenario: Escape returns focus to chart

- GIVEN the menu open
- WHEN `Escape` is pressed
- THEN the menu closes and `document.activeElement` is `#chart`

#### Scenario: Arrows and Home/End move focus

- GIVEN the menu open on the first item
- WHEN `ArrowDown` then `End` are pressed
- THEN focus moves to the next item, then to the last item

#### Scenario: Items advertise shortcuts

- GIVEN an open menu
- WHEN its items are inspected
- THEN each has an accessible name and an `aria-keyshortcuts` value

### Requirement: R4 — Commands reuse existing seams

Activating an item MUST invoke the existing path with NO new endpoint.
`delete` MUST emit `drawing:delete` (`drawings.js:125`); `duplicate` MUST emit
`drawing:duplicate`, handled in `drawings.js` by reusing `createDrawing`
(`drawings.js:139`); `reset-scale` MUST route through the F8 `scale:changed` path
(`main.js:204`); `add-indicator` MUST reuse the F5 `add-indicator-core` seam
(`add-indicator-core.js:30,79`). No `setData`/`update` MAY be called (#68).

#### Scenario: Delete reuses drawing:delete

- GIVEN a drawing row selected
- WHEN the `delete` item activates
- THEN `drawing:delete` fires with the id and one `DELETE` is captured

#### Scenario: Duplicate clones then POSTs

- GIVEN a drawing row selected
- WHEN the `duplicate` item activates
- THEN `drawing:duplicate` fires and one `POST /market/api/drawings` with cloned points is captured

#### Scenario: Reset-scale reuses the F8 seam

- GIVEN `scaleMode` non-linear
- WHEN `reset-scale` activates
- THEN `store.scaleMode` becomes `linear` and `scale:changed` fires with no new endpoint

#### Scenario: Add-indicator reuses the F5 seam

- GIVEN an empty chart
- WHEN `add-indicator` activates
- THEN the F5 add path runs (`store.set` + `indicator:changed`) with no new endpoint

### Requirement: R5 — Constraints

The hit-test MUST reuse the pure `grabHandle(pointerRows(rows), x, y, map())`
(`drawing-interaction-core.js:85`); `controllers/object-tree.js` and
`controllers/drawing-interaction.js` MUST stay byte-untouched; every module MUST
stay ≤300 lines; and the menu MUST NOT call `setData`/`update` (#68).

#### Scenario: Hit-test reuses the pure helpers

- GIVEN a right-click on a shape
- WHEN the target is resolved
- THEN it uses `grabHandle`/`pointerRows` (no duplicated hit-test logic)

#### Scenario: Untouched controllers and size

- GIVEN the delivered change
- WHEN the guard and diff run
- THEN `object-tree.js` and `drawing-interaction.js` are unchanged and each module is ≤300 lines

#### Scenario: No series data write

- GIVEN the `setData`/`update` spies installed
- WHEN any menu command runs
- THEN neither spy is called
