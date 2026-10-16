# Delta for design-system

Issue #118 (F5): the vertical icon toolbar and unified object tree adopt the shared
visual system. This MODIFIES R6 (a11y extends to the toolbar/tree keyboard paths
and not-color-only state) and R7 (CSP unchanged; icons via JS, no inline handler),
and ADDS R10 (toolbar/tree token requirements). R1–R5, R8, R9 stay in force and
unmodified.

## MODIFIED Requirements

### Requirement: R6 — Accessibility

Text MUST meet WCAG AA contrast against BOTH the dark and the light theme.
Interactive elements MUST have a visible focus state (`:focus-visible`).
Navigation MUST be keyboard-operable and use semantic landmarks. Critical state
MUST NOT rely on color alone. The `#chart` canvas MUST be focusable
(`tabindex="0"`) with an accessible label and MUST show a visible focus
indicator. The properties `<dialog>` MUST trap focus natively and close on
`Escape`. The F5 toolbar tools and tree rows/controls MUST have a visible focus
state and accessible names, and their active/selected/hidden/locked state MUST be
distinguishable without color (shape/border/weight in addition to `aria-pressed`/
`aria-selected`), mirroring R9's not-color-only rule.
(Previously: the rule covered nav links, form controls, the chart canvas, and the
dialog; the toolbar/tree did not exist.)

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

#### Scenario: AA holds in the light theme

- GIVEN the light token set applied via `[data-theme="light"]`
- WHEN shell text is measured against its background
- THEN the contrast is ≥4.5:1

### Requirement: R7 — CSP unchanged, no inline script

No inline `<script>` and no inline event handler MAY be introduced. The
`Content-Security-Policy` header value MUST remain unchanged (no `unsafe-inline`
for `script-src`). The pre-existing inline `onclick` in `invite_create.html`
MUST be removed. The F5 toolbar and tree icons MUST be injected by same-origin JS
(JS-built inline SVG from `tool-icons-core.js`) carrying no event attributes; no
`onclick`/`on*-attribute` MAY appear in the SVG or markup.
(Previously: the rule was silent on how icons are produced.)

#### Scenario: CSP header unchanged

- GIVEN a rendered page
- WHEN the response header is inspected
- THEN `Content-Security-Policy` equals the prior value (script-src strict, no unsafe-inline)

#### Scenario: No inline handler remains

- GIVEN the templates and the toolbar/tree markup
- WHEN scanned
- THEN no inline event handler or inline `<script>` is present, and the injected SVG carries no `on*` attribute

## ADDED Requirements

### Requirement: R10 — Toolbar and tree tokens

The toolbar and tree MUST use the design-system custom properties (no hard-coded
palette) for surfaces, borders, text, focus, and active state. The active tool and
the tree's selected/hidden/locked rows MUST be expressible with tokens in BOTH the
dark `:root` and the `[data-theme="light"]` set; no token name MAY be missing from
either set. Icons MUST inherit `currentColor` so they follow the theme.

#### Scenario: Tokens used, no hard-coded palette

- GIVEN the toolbar/tree styles
- WHEN inspected
- THEN they reference design-system custom properties and contain no literal palette hex outside the token definition

#### Scenario: Both themes define the tokens

- GIVEN the served stylesheet
- WHEN inspected
- THEN `:root` and `[data-theme="light"]` each declare the toolbar/tree active/selected/hidden/locked token names
