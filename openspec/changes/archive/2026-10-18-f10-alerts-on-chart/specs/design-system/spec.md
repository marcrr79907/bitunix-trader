# Delta for design-system

Issue #123 (F10): the alert bell is a real focusable `<button>` with an accessible
name; the alert `<dialog>` traps focus natively and returns focus to `#chart`; the
alert state also lives in an `aria-live` DOM node; and the canvas markers are not
color-only (shape + text). The alert UI introduces no inline script or handler and
the CSP value is unchanged. This MODIFIES R6 (a11y) and R7 (CSP). R1–R5, R8–R10
stay in force and unmodified.

## MODIFIED Requirements

### Requirement: R6 — Accessibility

Text MUST meet WCAG AA contrast against BOTH the dark and the light theme.
Interactive elements MUST have a visible focus state (`:focus-visible`).
Navigation MUST be keyboard-operable and use semantic landmarks. Critical state
MUST NOT rely on color alone. The `#chart` canvas MUST be focusable
(`tabindex="0"`) with an accessible label and MUST show a visible focus
indicator, so keyboard delete/deselect is reachable. The properties `<dialog>`
MUST trap focus natively and close on `Escape`. The F5 toolbar tools and tree
rows/controls MUST have a visible focus state and accessible names, and their
active/selected/hidden/locked state MUST be distinguishable without color
(shape/border/weight in addition to `aria-pressed`/`aria-selected`), mirroring
R9's not-color-only rule. The F6 measure tool and position box MUST follow the
same rules: the measure tool button MUST carry a visible focus state and an
accessible name; a Long vs Short position MUST be distinguishable WITHOUT color
alone (a text label "LONG"/"SHORT" plus a directional arrow); the measure readout
(`#measure-readout`) and the position R:R readout (`#position-readout`) MUST each
live in a DOM node with `aria-live="polite"` — the canvas-drawn `R:R` text is
supplementary, the DOM node is the accessible source — and their writes MUST be
coalesced to at most ONE per animation frame (via the pure
`readout-coalesce-core.js`) rather than one per pointer-move, never dropping the
final value; and `Escape` MUST cancel a measure or a pending position draft. The
F7 context menu MUST be keyboard-navigable: it MUST be a DOM `role="menu"` of
`role="menuitem"` items with ArrowUp/Down/Home/End roving focus, Enter/Space
activation, each item carrying an accessible name and, when it has one, an
`aria-keyshortcuts` advertising its binding (an empty shortcut MUST be omitted),
and `Escape` closing it and returning focus to `#chart`. The F7 undo/redo MUST
announce each operation ("Undo"/"Redo") in a polite `aria-live` region
(`#history-status`), and the F5 tool buttons MUST surface their advertised
shortcut letter visibly (`.tool-key`), so the `aria-keyshortcuts` is honest to
sighted users. The eight F9 tool buttons MUST follow the same toolbar model: each
MUST have a visible focus state, an accessible name (its human `TOOL_LABELS`
name — never the slug), and a visible `.tool-key`, and MUST NOT be distinguished
by color alone — `price` MUST show a right-axis price label formatted like the
axis, `callout` MUST show its text in a rounded balloon with an arrowhead,
`fib_ext`/`fib_time`/`fib_zone` MUST show ratio labels (as `fib` does) with a
contrasting halo, and `ray`/`vline`/`channel` MUST differ by shape
(line/extension/parallel geometry). A pending 2/3-click draft MUST be previewed
on the canvas and the chart cursor MUST be a crosshair while a tool is active, so
a partial gesture is visible rather than silent.
(Previously: AA contrast was required against the dark theme only.)
(Previously: focus state covered nav links and form controls only; no focusable
chart canvas, dialog, or toolbar/tree contract.)
(Previously: the rule was silent on measure/position; the position R:R `aria-live`
node and Escape-cancels-draft behavior were verify CRITICALs C1/C2, remediated in
the F6 S4/UI slices — the rule now matches the delivered behavior.)
(Previously: the rule was silent on the F7 context menu, undo announcement, and
the visible tool shortcut letter.)
(Previously: the rule was silent on the F9 drawing tools, their human labels, the
draft preview, and the crosshair.)
(Previously: the rule was silent on the F10 alert bell, dialog focus return,
`#alert-status` live region, and not-color-only markers.)

#### Scenario: Alert bell is focusable and named

- GIVEN the rendered market page with a crosshair point
- WHEN the bell is inspected
- THEN it is a `<button type="button">` with an accessible name containing the price, reachable by Tab, with a visible `:focus-visible` state

#### Scenario: Alert dialog returns focus

- GIVEN `#alert-dialog` opened from the bell
- WHEN `Escape` or Cancel closes it
- THEN focus returns to `#chart` and no request was captured

#### Scenario: Alert state is live in the DOM

- GIVEN 1 fired and 2 armed alerts on the active pair
- WHEN the list renders
- THEN `#alert-status[aria-live="polite"]` reads a summary such as "3 alerts: 1 fired, 2 armed"

#### Scenario: Alert markers are not color-only

- GIVEN an armed and a fired rule rendered as markers
- WHEN the marker payload is inspected
- THEN armed and fired differ in `shape` AND in `text` ("A"/"F"), not only in `color`

#### Scenario: Visible focus
- GIVEN a keyboard user
- WHEN focus moves to a nav link, form control, the `#chart` canvas, a toolbar tool, or a tree control
- THEN a visible focus indicator appears

#### Scenario: Chart is keyboard-focusable and labelled
- GIVEN the rendered market page
- WHEN the user Tabs to `#chart`
- THEN it receives focus and exposes an accessible label

#### Scenario: Dialog traps focus and closes on Escape
- GIVEN the properties dialog open
- WHEN the user presses `Escape`
- THEN the dialog closes without applying changes

#### Scenario: Toolbar/tree state is not color-only
- GIVEN an active tool and a hidden/locked tree row
- WHEN their styles are inspected
- THEN each differs from the inactive state by more than color (border/weight/shape) alongside `aria-pressed`/`aria-selected`

#### Scenario: Long vs Short is not color-only
- GIVEN a rendered long position and a rendered short position
- WHEN their rendering is inspected
- THEN each carries a text label ("LONG"/"SHORT") and a directional arrow, so they differ by more than color (`drawing-primitive.js` writes the label + ▲/▼)

#### Scenario: Readouts are live DOM
- GIVEN a completed measurement and a selected position
- WHEN the DOM is inspected
- THEN the measure figures live in `#measure-readout[aria-live="polite"]` and the R:R figure lives in `#position-readout[aria-live="polite"]`

#### Scenario: Readout writes coalesce per frame
- GIVEN a live drag or measure pointer-move stream
- WHEN the readout updates
- THEN the DOM write is coalesced to at most one per animation frame (never one per pointer-move, never dropping the final value) via `readout-coalesce-core.js`

#### Scenario: Escape cancels a draft
- GIVEN an in-progress measurement or a pending position draft
- WHEN `Escape` is pressed
- THEN the draft is cancelled and no drawing is written (measure: `chart-controllers.test.js`; position: `drawings.js` keydown handler + `position-draft-core` `cancel`)

#### Scenario: Context menu is keyboard-navigable with focus return
- GIVEN the F7 context menu open
- WHEN `ArrowDown`/`End`/`Enter`/`Escape` are pressed
- THEN focus roves across items, Enter activates the focused item, and `Escape` closes the menu and returns focus to `#chart`

#### Scenario: Menu items advertise accessible names and shortcuts
- GIVEN an open context menu on a drawing row
- WHEN its items are inspected
- THEN each carries an accessible name and its `aria-keyshortcuts` when it has one (an empty shortcut is omitted)

#### Scenario: Undo and redo are announced
- GIVEN an undo or a redo run
- WHEN it completes
- THEN the polite `#history-status` region carries "Undo" (or "Redo")

#### Scenario: Tool shortcut letters are visible
- GIVEN the rendered draw toolbar
- WHEN a tool button is inspected
- THEN it shows a visible `.tool-key` letter alongside its `aria-keyshortcuts`

#### Scenario: F9 kinds are not color-only
- GIVEN a rendered `price`, `callout`, and each fib kind
- WHEN their rendering is inspected
- THEN `price` shows a right-axis price label formatted like the axis, `callout` shows its text in a balloon with an arrowhead, the fib kinds show ratio labels with a contrasting halo, and `ray`/`vline`/`channel` differ by shape — so each is distinguishable without color (`tool-render-core.js`; `drawing-primitive.test.js` price label / callout balloon / fib ratio cases)

#### Scenario: F9 tool labels are human names
- GIVEN a rendered F9 tool button and its object-tree row
- WHEN the accessible name and the row label are read
- THEN each shows the human `TOOL_LABELS` name ("Fibonacci extension", not `fib_ext`; `tool-icons-core.labelFor`)

#### Scenario: A pending draft is previewed
- GIVEN a 2/3-click tool with one or two anchors placed
- WHEN the chart renders
- THEN the partial shape is previewed on its own primitive (never POSTed, never in autoscale) and the chart cursor is a crosshair while the tool is active (`controllers/draft-preview.js`; `drawings.js` cursor)

#### Scenario: AA holds in the light theme
- GIVEN the light token set applied via `[data-theme="light"]`
- WHEN shell text is measured against its background
- THEN the contrast is ≥4.5:1

### Requirement: R7 — CSP unchanged, no inline script

No inline `<script>` and no inline event handler MAY be introduced. The
`Content-Security-Policy` header value MUST remain unchanged (no `unsafe-inline`
for `script-src`). The pre-existing inline `onclick` in `invite_create.html`
MUST be removed (its behavior moved to same-origin JavaScript). The F5 toolbar and
tree icons MUST be injected by same-origin JS (JS-built inline SVG from
`tool-icons-core.js`) carrying no event attributes; no `onclick`/`on*` attribute
MAY appear in the SVG or markup. The F7 context menu MUST be JS-built DOM (a
`role="menu"` node created by `controllers/context-menu.js`) and its
`contextmenu` listener MUST be registered via `addEventListener`; NO inline
`oncontextmenu` attribute or inline `<script>` MAY be added. The F10 alert bell,
`<dialog>` and its controls MUST be built/declared without inline handlers (the
`<dialog>` markup is static, the bell is created with `createElement` +
`setAttribute`), and the CSP value MUST stay unchanged.
(Previously: the rule was silent on how icons are produced.)
(Previously: the rule was silent on the F7 context menu.)
(Previously: the rule was silent on the F10 alert bell/dialog.)

#### Scenario: Alert dialog is CSP-clean

- GIVEN the rendered market page with `#alert-dialog` and the bell
- WHEN the markup and scripts are scanned
- THEN no inline `<script>` or `on*` attribute exists for the alert UI and the CSP equals the prior value

#### Scenario: CSP header unchanged
- GIVEN a rendered page
- WHEN the response header is inspected
- THEN `Content-Security-Policy` equals the prior value (script-src strict, no unsafe-inline)

#### Scenario: No inline handler remains
- GIVEN the templates and the toolbar/tree markup
- WHEN scanned
- THEN no inline event handler or inline `<script>` is present, and the injected SVG carries no `on*` attribute

#### Scenario: Menu is CSP-clean
- GIVEN the rendered market page
- WHEN the markup and scripts are scanned
- THEN no inline `oncontextmenu`/`<script>` exists, the `contextmenu` listener is attached with `addEventListener`, and the CSP equals the prior value
