# design-system Specification

## Purpose

The shared visual system for the dashboard: design tokens delivered as a
same-origin stylesheet plus an app shell (topbar + nav) that every page
inherits. Dark, dense, terminal-style (TradingView-inspired functional
aesthetic — no third-party brand/assets). New capability — no prior spec.

## Requirements

### Requirement: R1 — Same-origin token stylesheet

The design tokens MUST be delivered as a stylesheet served by a Django view with
`Content-Type: text/css` at a stable route (mirroring `market.views.chart_js`).
The route MUST be reachable WITHOUT authentication (a stylesheet protects
nothing; gating it would 302 the login page's own CSS). The stylesheet MUST
define the palette (background layers, surface, border, text, muted, a single
accent, semantic up/down), typography scale, spacing, and radius as CSS custom
properties, plus a `.num` utility using `font-variant-numeric: tabular-nums`. It
MUST define the dark palette on `:root` (the default) AND a complete light
palette under `[data-theme="light"]` declaring the SAME custom-property names;
`[data-theme="dark"]` MUST resolve to the dark set. No token name MAY be missing
from either set.
(Previously: only the dark `:root` palette existed; there was no
`[data-theme]` selector and no light set.)

#### Scenario: Anonymous stylesheet loads
- GIVEN an anonymous client
- WHEN it requests the theme stylesheet route
- THEN the response is 200 with `Content-Type: text/css`

#### Scenario: Tokens are present in both sets
- GIVEN the served stylesheet
- WHEN inspected
- THEN `:root` and `[data-theme="light"]` each declare the same custom-property names (surfaces, text, accent, up/down, scale, spacing, radius)

#### Scenario: Dark is the default
- GIVEN no `data-theme` attribute on the root
- WHEN the page renders
- THEN the dark `:root` palette applies

### Requirement: R2 — App shell inherited by every page

A shared shell MUST live in the base template: a topbar with the brand, primary
navigation (Market, Positions, Journal) and the signed-in user's identity plus
logout, and a content region. Every page (home, login, signup, invite, market)
MUST render this shell. The active navigation item MUST be marked with
`aria-current="page"` derived from the resolved route name.

#### Scenario: Shell renders on each page
- GIVEN any of the home, login, signup, invite, or market pages
- WHEN it is rendered
- THEN the topbar and its navigation are present

#### Scenario: Active item marked
- GIVEN the user is on the market page
- WHEN the shell renders
- THEN the Market nav item carries `aria-current="page"`

#### Scenario: Placeholder nav does not crash
- GIVEN Positions/Journal routes do not yet exist (Fase 6c)
- WHEN any shell page renders
- THEN the nav uses static hrefs and no page raises `NoReverseMatch`

### Requirement: R3 — Logout is a POST form

Logout MUST be submitted as a POST form carrying the CSRF token (Django 5's
`LogoutView` is POST-only). The shell MUST NOT render a GET logout link that
would produce HTTP 405.

#### Scenario: POST logout works
- GIVEN an authenticated user on a shell page
- WHEN the logout form is submitted with CSRF
- THEN the user is logged out and redirected

#### Scenario: No GET logout link
- GIVEN the rendered shell
- WHEN inspected
- THEN logout is a form (method="post"), not an anchor that issues GET

### Requirement: R4 — Script extension point

A page MUST be able to inject its own scripts without breaking the shell, via a
template block. The market chart page MUST keep loading its chart script through
this block with the shell intact.

#### Scenario: Chart page keeps its script
- GIVEN the market chart page extending the shell
- WHEN rendered
- THEN the shell topbar is present AND the chart script is loaded via the scripts block

### Requirement: R5 — Existing behavior preserved

The five existing pages MUST keep their functional content after adopting the
shell: login/signup/invite forms submit, the market chart container is present,
and the previously passing suites stay green.

#### Scenario: Forms still submit
- GIVEN the login, signup, and invite pages
- WHEN their forms are submitted as before
- THEN behavior is unchanged

#### Scenario: Existing suites stay green
- GIVEN the pre-existing web tests
- WHEN the full suite runs
- THEN all previously passing tests still pass

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
sighted users.
(Previously: AA contrast was required against the dark theme only.)
(Previously: focus state covered nav links and form controls only; no focusable
chart canvas, dialog, or toolbar/tree contract.)
(Previously: the rule was silent on measure/position; the position R:R `aria-live`
node and Escape-cancels-draft behavior were verify CRITICALs C1/C2, remediated in
the F6 S4/UI slices — the rule now matches the delivered behavior.)
(Previously: the rule was silent on the F7 context menu, undo announcement, and
the visible tool shortcut letter.)

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
tokens. Because a canvas cannot read CSS custom properties directly, the canvas
color reads MUST resolve theme tokens through the shared `theme-core.js` `token()`
helper (with a fallback literal) rather than writing hard-coded palette hex — so a
future token change flows through and the measure/position canvas colors stay
on-palette in BOTH the dark and light theme (folding in the /impeccable HIGH #193).
The properties `<dialog>` MUST be styled with the same tokens as the
existing indicator-settings dialog.
(Previously: the rule covered generic drawings; the position handle set did not
exist; canvas colors were hard-coded literals.)

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
- THEN the three level handles and entry anchor are canvas-drawn (no DOM nodes) and the risk/reward zones and level strokes read their colors through `theme-core.js` `token()` (no hard-coded palette literal in the position/measure canvas paths)

#### Scenario: Canvas colors follow the theme tokens

- GIVEN `drawing-primitive.js` and `controllers/measure.js` canvas color paths
- WHEN inspected
- THEN each color resolves via `token("--…")` (e.g. `--dn`/`--up`/`--muted`/`--accent`) rather than an inline hex, so a token change (dark or light theme) flows through

#### Scenario: Dialog uses tokens

- GIVEN the properties dialog open
- WHEN its styles are inspected
- THEN it uses the design-system custom properties (no hard-coded palette)

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
- THEN `:root` and `[data-theme="light"]` each declare the toolbar/tree active/selected/hidden/locked token names (`--tree-selected`/`--tree-hidden`/`--tree-locked`)

### Requirement: R8 — Boundary and no new dependency

`src/` MUST remain framework-free. `requirements.txt` MUST be unchanged. No npm
or build step MAY be introduced.

#### Scenario: No core/Django leak
- GIVEN the new view and template
- WHEN the boundary test runs
- THEN no Django import appears in `src/`

#### Scenario: Dependency file unchanged
- GIVEN the change
- WHEN `requirements.txt` is inspected
- THEN no runtime dependency was added
