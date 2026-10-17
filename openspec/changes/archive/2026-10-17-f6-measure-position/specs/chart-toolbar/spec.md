# Delta for chart-toolbar

Issue #119 (F6): the toolbar gains the two TradingView instruments the F5
substrate was built to carry — a `Measure` group and a `Positions` group. This
MODIFIES R1 (two groups + two `TOOL_LABELS` + two `ICON_BODIES`; activation writes
`store.tool` via the existing command, no new bus event). R2/R3/R4/R5 stay in
force and unmodified.

## MODIFIED Requirements

### Requirement: R1 — Toolbar structure and grouping

The toolbar MUST render as a `role="toolbar"` element with
`aria-orientation="vertical"` and an accessible `aria-label`, containing one
`role="group"` per icon group (lines, fib, shapes, text — plus the F6 `Measure`
and `Positions` groups) — vocabulary from `tool-icons-core.js`. Each tool MUST be
a native `<button type="button">` with an accessible `aria-label` and `data-kind`
∈ `DRAWING_KINDS` (`drawing-core.js:13`). `tool-icons-core.js` `TOOL_GROUPS` MUST
include a `Measure` group (`kinds:["measure"]`) and a `Positions` group
(`kinds:["position"]`), with a matching `TOOL_LABELS` entry in
`draw-toolbar.js:17-23` and an `ICON_BODIES` entry for each kind
(`tool-icons-core.js:33-46`). Activating a tool MUST set `store.tool` and emit the
SAME command the legacy `.draw-tool` buttons used (`drawings.js:218-232`); it MUST
NOT introduce a new bus event. A singleton group (one tool) MAY be rendered.
(Previously: groups were lines/fib/shapes/text only; five kinds.)

#### Scenario: Toolbar and groups render

- GIVEN the rendered `/market/` page
- WHEN the toolbar DOM is inspected
- THEN exactly one `role="toolbar"` with a vertical orientation and an accessible name exists, containing `role="group"` parents each with an accessible name, and no `.draw-tool` legacy text button remains

#### Scenario: Measure and Positions groups render

- GIVEN `tool-icons-core` includes a `Measure` group and a `Positions` group
- WHEN the toolbar renders
- THEN both groups appear, each with a labelled button whose `data-kind` is `measure` / `position` and which carries an icon

#### Scenario: Tool activation sets store and command

- GIVEN the vertical toolbar
- WHEN the `hline` tool button is activated
- THEN `store.tool === "hline"` and the same create-tool command the legacy button emitted is observed (no new bus event)

#### Scenario: Activating position writes store.tool with no new event

- GIVEN the vertical toolbar
- WHEN the `position` tool button is activated
- THEN `store.tool === "position"` and no bus event beyond the pre-existing set is emitted

#### Scenario: Singleton group allowed

- GIVEN `tool-icons-core` groups kinds into singleton and multi-member groups
- WHEN the toolbar renders
- THEN each group renders regardless of member count and no fault occurs
