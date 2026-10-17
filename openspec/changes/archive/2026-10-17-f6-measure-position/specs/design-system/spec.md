# Delta for design-system

Issue #119 (F6): the measure and position instruments adopt the shared visual
system. This MODIFIES R6 (a11y: Long/Short distinguishable not by color alone;
measure/position readouts are `aria-live` DOM; focus/keyboard) and R9 (the
selected position's level handles stay canvas-drawn and not-color-only). R1–R5,
R7, R8, R10 stay in force and unmodified.

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
and the position R:R readout MUST live in DOM nodes with `aria-live="polite"`;
and `Escape` MUST cancel a measure or a pending position draft.
(Previously: the rule covered the F5 toolbar/tree; measure/position did not exist.)

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
- THEN each carries a text label ("LONG"/"SHORT") and a directional arrow, so they differ by more than color

#### Scenario: Readouts are live DOM

- GIVEN a completed measurement and a rendered position
- WHEN the DOM is inspected
- THEN the measure figures and the R:R figure each live in an `[aria-live="polite"]` node

#### Scenario: Escape cancels a draft

- GIVEN an in-progress measurement or a pending position draft
- WHEN `Escape` is pressed
- THEN the draft is cancelled and no drawing is written

#### Scenario: AA holds in the light theme

- GIVEN the light token set applied via `[data-theme="light"]`
- WHEN shell text is measured against its background
- THEN the contrast is ≥4.5:1

### Requirement: R9 — Drawing selection and handles styling

The selected drawing's highlight and its handles MUST use the design tokens (no
hard-coded colors) and MUST be distinguishable without relying on color alone
(e.g. handle shape/ring in addition to stroke weight). Handles are drawn on the
chart canvas by the primitive, not as DOM elements, so no per-pan DOM re-layout
occurs. The selected position's three level handles and entry anchor MUST follow
the same rule (canvas-drawn, not-color-only), and its risk/reward zones MUST use
tokens. The properties `<dialog>` MUST be styled with the same tokens as the
existing indicator-settings dialog.
(Previously: the rule covered generic drawings; the position handle set did not exist.)

#### Scenario: Selection is not color-only

- GIVEN a selected drawing
- WHEN the highlight and handles render
- THEN they differ from the unselected state by more than color (weight/shape)

#### Scenario: Handles are canvas-drawn

- GIVEN a rendered drawing
- WHEN the DOM is inspected
- THEN the handles are not DOM nodes (drawn by the primitive)

#### Scenario: Position handles are canvas-drawn and tokenized

- GIVEN a selected position
- WHEN its handles and zones render
- THEN the three level handles and entry anchor are canvas-drawn (no DOM nodes) and the risk/reward zones use design tokens

#### Scenario: Dialog uses tokens

- GIVEN the properties dialog open
- WHEN its styles are inspected
- THEN it uses the design-system custom properties (no hard-coded palette)
