# Delta for chart-toolbar

Issue #120 (F7): the toolbar's tool buttons gain `aria-keyshortcuts` advertising
their per-tool letter, and per-tool letter firing is scoped to `#chart` focus only
(the object tree already owns `v`/`l`/`s`, `object-tree.js:137-142,201-205`). This
MODIFIES R1 (each tool button carries an `aria-keyshortcuts`; no global letter
router) and R3 (letter activation is `#chart`-scoped). R2/R4/R5 stay in force and
unmodified.

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
its per-tool shortcut letter, but the letter MUST NOT be a global binding — it
MUST fire only when focus is inside `#chart` (the object tree owns `v`/`l`/`s`).
`tool-icons-core.js` `TOOL_GROUPS` MUST
group the seven instruments as `2/1/1/1/1/1` (`Lines`=`hline,trendline`, `Fib`,
`Shapes`, `Text`, `Measure`=`["measure"]`, `Positions`=`["position"]`), with a
matching `TOOL_LABELS` entry in `draw-toolbar.js` for `measure`/`position` and an
`ICON_BODIES` entry for each kind (`tool-icons-core.js`). The two new icons MUST be
JS-built inline SVG strings carrying NO `on*` attribute. Activating a tool MUST set
`store.tool` and emit the SAME command the legacy `.draw-tool` buttons used
(`drawings.js`); it MUST NOT introduce a new bus event — activating `position`
writes `store.tool="position"` through the existing command, and `measure` is a
tool value with no drawing kind. A singleton group (one tool) MAY be rendered.
(Previously: tool buttons carried no `aria-keyshortcuts` and per-tool letter
firing was not scoped.)

#### Scenario: Toolbar and groups render

- GIVEN the rendered `/market/` page
- WHEN the toolbar DOM is inspected
- THEN exactly one `role="toolbar"` with a vertical orientation and an accessible name exists, containing `role="group"` parents each with an accessible name, and no `.draw-tool` legacy text button remains

#### Scenario: Buttons advertise per-tool shortcuts

- GIVEN the rendered toolbar
- WHEN a tool button is inspected
- THEN it carries an `aria-keyshortcuts` value and an accessible name

#### Scenario: Tool activation sets store and command

- GIVEN the vertical toolbar
- WHEN the `hline` tool button is activated
- THEN `store.tool === "hline"` and the same create-tool command the legacy button emitted is observed (no new bus event)

#### Scenario: Measure and Positions groups render

- GIVEN `tool-icons-core` includes a `Measure` group and a `Positions` group
- WHEN the toolbar renders
- THEN both groups appear, each with a labelled button whose `data-kind` is `measure` / `position` and which carries an icon (`tool-icons-core.test.js::TOOL_GROUPS: F6 groups the 7 instruments 2/1/1/1/1/1`)

#### Scenario: Activating position writes store.tool with no new event

- GIVEN the vertical toolbar
- WHEN the `position` tool button is activated
- THEN `store.tool === "position"` and no bus event beyond the pre-existing set is emitted (E2E `test_position_three_click_persists_and_drag_one_put`; the toolbar writes `store.tool` uniformly for every kind)

#### Scenario: Singleton group allowed

- GIVEN `tool-icons-core` groups the 7 kinds into 2/1/1/1/1/1
- WHEN the toolbar renders
- THEN each group renders regardless of member count and no fault occurs

### Requirement: R3 — Keyboard operation (roving focus)

Tool buttons MUST be keyboard-focusable with a single roving `tabindex="0"`
(all others `-1`). Up/Down MUST move focus between tool buttons; Home/End MUST
jump to first/last. Enter/Space MUST activate the focused tool natively. A
per-tool **letter** shortcut MAY activate a tool ONLY while
`document.activeElement` is inside `#chart`; when focus is elsewhere in the page
the letter MUST NOT fire, so the object tree's `v`/`l`/`s` (`object-tree.js`) are
never stolen. Behavior MUST mirror the interval-chip pattern (`toolbar.js:63-71`).

#### Scenario: Arrows move focus

- GIVEN focus on a tool button
- WHEN `ArrowDown` is pressed
- THEN `document.activeElement` moves to the next tool button

#### Scenario: Home and End jump

- GIVEN focus on a middle tool button
- WHEN `Home` then `End` are pressed
- THEN focus moves to the first tool, then the last tool

#### Scenario: Enter activates

- GIVEN focus on the `trendline` tool
- WHEN `Enter` is pressed
- THEN the tool activates exactly as a click would

#### Scenario: Letter firing is chart-scoped only

- GIVEN the page loaded
- WHEN a tool letter is pressed while focus is OUTSIDE `#chart` (e.g. a tree row)
- THEN no tool activates (the tree owns `v`/`l`/`s`)

#### Scenario: Letter fires inside the chart

- GIVEN focus inside `#chart`
- WHEN the `hline` letter is pressed
- THEN the `hline` tool activates
