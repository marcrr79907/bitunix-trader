# Delta for chart-toolbar

Issue #122 (F9): the toolbar gains eight tool buttons/icons for the new drawing
kinds, grouped into the existing `Lines`/`Fib` groups (extended), plus eight
non-colliding per-tool shortcut letters
(`ray=A, vline=I, channel=C, price=U, callout=O, fib_ext=E, fib_time=W,
fib_zone=Z`) that MUST NOT collide with the existing `H/T/F/R/X/M/P` or the object
tree's `v/l/s/Delete`. Activation reuses the existing `store.tool` command — no new
bus event. This MODIFIES R1 (group structure + eight tools/icons/letters/labels)
and R3 (the per-tool letter set grows and stays `#chart`-scoped). R2/R4/R5 stay in
force and unmodified.

## MODIFIED Requirements

### Requirement: R1 — Toolbar structure and grouping

The toolbar MUST render as a `role="toolbar"` element with
`aria-orientation="vertical"` and an accessible `aria-label`, containing one
`role="group"` per icon group (lines, fib, shapes, text — plus the F6 `Measure`
and `Positions` groups) — vocabulary from `tool-icons-core.js`. Each tool MUST be
a native `<button type="button">` with an accessible `aria-label` and a
`data-kind` matching its group kind — a persisted drawing kind ∈ `DRAWING_KINDS`
(`drawing-core.js:13`) for the drawing tools, or `"measure"` for the ephemeral
measure tool (the ONLY `data-kind` that is not a `DRAWING_KINDS` member). Each
tool button MUST additionally carry an `aria-keyshortcuts` attribute advertising
its per-tool shortcut letter and a VISIBLE `<span class="tool-key">` showing that
letter; the letter MUST NOT be a global binding — it MUST fire only when focus is
inside `#chart` (the object tree owns `v`/`l`/`s`; see R3). `tool-icons-core.js`
`TOOL_GROUPS` MUST group the **fifteen** instruments as
`Lines`=`[hline,trendline,ray,vline,channel,price]`, `Fib`=`[fib,fib_ext,fib_time,
fib_zone]`, `Shapes`=`[rect]`, `Text`=`[text,callout]`,
`Measure`=`["measure"]`, `Positions`=`["position"]` (`6/4/1/2/1/1`), with a
matching `TOOL_LABELS` entry in `draw-toolbar.js` for every kind and an
`ICON_BODIES` entry for each kind (`tool-icons-core.js`). The eight F9 icons MUST
be JS-built inline SVG strings carrying NO `on*` attribute. `draw-toolbar.js`
`TOOL_KEYS` MUST gain the eight F9 letters `ray=A`, `vline=I`, `channel=C`,
`price=U`, `callout=O`, `fib_ext=E`, `fib_time=W`, `fib_zone=Z`, which MUST NOT
collide with `H/T/F/R/X/M/P` or the object tree's `v/l/s`. Activating a tool MUST
set `store.tool` and emit the SAME command the legacy `.draw-tool` buttons used
(`drawings.js`); it MUST NOT introduce a new bus event. A singleton group MAY be
rendered.
(Previously: `TOOL_GROUPS` grouped seven instruments `2/1/1/1/1/1` with seven
letters `H/T/F/R/X/M/P`; no F9 tools.)

#### Scenario: Toolbar and groups render

- GIVEN the rendered `/market/` page
- WHEN the toolbar DOM is inspected
- THEN exactly one `role="toolbar"` with a vertical orientation and an accessible name exists, containing `role="group"` parents each with an accessible name, and no `.draw-tool` legacy text button remains

#### Scenario: Buttons advertise per-tool shortcuts

- GIVEN the rendered toolbar
- WHEN a tool button is inspected
- THEN it carries an `aria-keyshortcuts` value, an accessible name, and a visible `<span class="tool-key">` with the same letter

#### Scenario: Tool activation sets store and command

- GIVEN the vertical toolbar
- WHEN the `hline` tool button is activated
- THEN `store.tool === "hline"` and the same create-tool command the legacy button emitted is observed (no new bus event)

#### Scenario: Eight F9 tools render in the extended groups

- GIVEN `tool-icons-core` groups the 15 instruments `6/4/1/2/1/1`
- WHEN the toolbar renders
- THEN the eight F9 buttons appear with `data-kind` ∈ `{ray,vline,channel,price,callout,fib_ext,fib_time,fib_zone}`, each with an icon and an accessible name (`tool-icons-core.test.js::TOOL_GROUPS: F9 groups the 15 instruments`)

#### Scenario: F9 letters are non-colliding

- GIVEN the eight F9 `TOOL_KEYS` letters
- WHEN compared to `H/T/F/R/X/M/P` and `v/l/s`
- THEN no collision exists and each F9 button advertises its own `aria-keyshortcuts` (`draw-toolbar.test.js`)

#### Scenario: Activating an F9 tool writes store.tool with no new event

- GIVEN the vertical toolbar
- WHEN the `channel` tool button is activated
- THEN `store.tool === "channel"` and no bus event beyond the pre-existing set is emitted (the toolbar writes `store.tool` uniformly for every kind)

### Requirement: R3 — Keyboard operation (roving focus)

Tool buttons MUST be keyboard-focusable with a single roving `tabindex="0"`
(all others `-1`). Up/Down MUST move focus between tool buttons; Home/End MUST
jump to first/last. Enter/Space MUST activate the focused tool natively. A
per-tool **letter** shortcut (`H`/`T`/`F`/`R`/`X`/`M`/`P` for the pre-F9 kinds plus
`A`/`I`/`C`/`U`/`O`/`E`/`W`/`Z` for the F9 kinds — the inverse of `TOOL_KEYS`)
MUST activate its tool ONLY while focus is inside `#chart`
(`draw-toolbar.js` binds the letter `keydown` on the `#chart` element); when
focus is elsewhere in the page the letter MUST NOT fire, so the object tree's
`v`/`l`/`s` (`object-tree.js:137-142,201-205`) are never stolen. The letter router
MUST ignore modifiers (`meta`/`ctrl`/`alt`) and MUST not fire for a focused text
input/textarea/select/contenteditable. Behavior MUST mirror the interval-chip
pattern (`toolbar.js:63-71`).
(Previously: the letter set was `H/T/F/R/X/M/P` only.)

#### Scenario: Arrows move focus

- GIVEN focus on a tool button
- WHEN `ArrowDown` is pressed
- THEN `document.activeElement` moves to the next tool button

#### Scenario: Home and End jump

- GIVEN focus on a middle tool button
- WHEN `Home` then `End` are pressed
- THEN focus moves to the first tool, then the last tool

#### Scenario: Letter firing is chart-scoped only

- GIVEN the page loaded
- WHEN a tool letter is pressed while focus is OUTSIDE `#chart` (e.g. a tree row)
- THEN no tool activates (the tree owns `v`/`l`/`s`)

#### Scenario: Letter fires inside the chart

- GIVEN focus inside `#chart`
- WHEN the `hline` letter (`h`) is pressed
- THEN the `hline` tool activates (its `store.tool` is set)

#### Scenario: F9 letter activates its tool

- GIVEN focus inside `#chart`
- WHEN the `channel` letter (`c`) is pressed
- THEN `store.tool === "channel"` (the letter router is `#chart`-scoped)
