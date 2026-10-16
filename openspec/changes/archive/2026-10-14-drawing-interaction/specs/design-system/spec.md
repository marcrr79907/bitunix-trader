# Delta for design-system

Issue #117 (Fase F4, Ola 4): the chart gains a focusable canvas (`#chart`), a
selection highlight, handles, and a native properties `<dialog>`. This MODIFIES
R6 (accessibility) to cover the chart focus ring and the dialog, and ADDS the
selection/handle styling contract. R1–R5, R7, R8 stay in force.

## ADDED Requirements

### Requirement: R9 — Drawing selection and handles styling

The selected drawing's highlight and its handles MUST use the design tokens (no
hard-coded colors) and MUST be distinguishable without relying on color alone
(e.g. handle shape/ring in addition to stroke weight). Handles are drawn on the
chart canvas by the primitive, not as DOM elements, so no per-pan DOM re-layout
occurs. The properties `<dialog>` MUST be styled with the same tokens as the
existing indicator-settings dialog.

#### Scenario: Selection is not color-only

- GIVEN a selected drawing
- WHEN the highlight and handles render
- THEN they differ from the unselected state by more than color (weight/shape)

#### Scenario: Handles are canvas-drawn

- GIVEN a rendered drawing
- WHEN the DOM is inspected
- THEN the handles are not DOM nodes (drawn by the primitive)

#### Scenario: Dialog uses tokens

- GIVEN the properties dialog open
- WHEN its styles are inspected
- THEN it uses the design-system custom properties (no hard-coded palette)

## MODIFIED Requirements

### Requirement: R6 — Accessibility

Text MUST meet WCAG AA contrast against BOTH the dark and the light theme.
Interactive elements MUST have a visible focus state (`:focus-visible`).
Navigation MUST be keyboard-operable and use semantic landmarks. Critical state
MUST NOT rely on color alone. The `#chart` canvas MUST be focusable
(`tabindex="0"`) with an accessible label and MUST show a visible focus
indicator, so keyboard delete/deselect is reachable. The properties `<dialog>`
MUST trap focus natively and close on `Escape`.
(Previously: focus state covered nav links and form controls only; no focusable
chart canvas or dialog contract.)
(Delivered with: chart focus ring, keyboard delete/deselect scope.)

#### Scenario: Visible focus

- GIVEN a keyboard user
- WHEN focus moves to a nav link, form control, or the `#chart` canvas
- THEN a visible focus indicator appears

#### Scenario: Chart is keyboard-focusable and labelled

- GIVEN the rendered market page
- WHEN the user Tabs to `#chart`
- THEN it receives focus and exposes an accessible label

#### Scenario: Dialog traps focus and closes on Escape

- GIVEN the properties dialog open
- WHEN the user presses `Escape`
- THEN the dialog closes without applying changes

#### Scenario: AA holds in the light theme

- GIVEN the light token set applied via `[data-theme="light"]`
- WHEN shell text is measured against its background
- THEN the contrast is ≥4.5:1
