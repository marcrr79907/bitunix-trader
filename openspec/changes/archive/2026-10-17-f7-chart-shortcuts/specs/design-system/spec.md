# Delta for design-system

Issue #120 (F7): the F7 context menu must be keyboard-navigable with a focus
return to `#chart` and `aria-keyshortcuts` per item, built as JS DOM under the
unchanged CSP. This MODIFIES R6 (a11y: context-menu keyboard nav + focus return)
and R7 (CSP unchanged; the menu is JS-built, no inline `oncontextmenu`). R1–R5,
R8–R10 stay in force and unmodified.

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
activation, each item carrying an accessible name and an `aria-keyshortcuts`
advertising its binding, and `Escape` closing it and returning focus to `#chart`.
(Previously: AA contrast was required against the dark theme only.)
(Previously: focus state covered nav links and form controls only; no focusable
chart canvas, dialog, or toolbar/tree contract.)
(Previously: the rule was silent on measure/position; the position R:R `aria-live`
node and Escape-cancels-draft behavior were verify CRITICALs C1/C2, remediated in
the F6 S4/UI slices — the rule now matches the delivered behavior.)
(Previously: the rule was silent on the F7 context menu.)

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
- GIVEN an open context menu
- WHEN its items are inspected
- THEN each carries an accessible name and an `aria-keyshortcuts` value

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
`oncontextmenu` attribute or inline `<script>` MAY be added.
(Previously: the rule was silent on how icons are produced.)
(Previously: the rule was silent on the F7 context menu.)

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
