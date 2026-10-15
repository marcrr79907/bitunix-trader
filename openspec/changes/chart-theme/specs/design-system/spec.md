# Delta for design-system

Issue #148 (DEBT-7). The token stylesheet gains a second, authored light palette
selected by `[data-theme="light"]`; the existing `:root` block becomes the
default/explicit dark set (`[data-theme="dark"]` equivalent). R1 changes; R6 (a11y)
tightens to require AA in BOTH themes. R7 (CSP) and R8 (boundary/deps) stay in
force.

## MODIFIED Requirements

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

### Requirement: R6 — Accessibility

Text MUST meet WCAG AA contrast against BOTH the dark and the light theme.
Interactive elements MUST have a visible focus state (`:focus-visible`).
Navigation MUST be keyboard-operable and use semantic landmarks. Critical state
MUST NOT rely on color alone.
(Previously: AA contrast was required against the dark theme only.)

#### Scenario: Visible focus

- GIVEN a keyboard user
- WHEN focus moves to a nav link or form control
- THEN a visible focus indicator appears

#### Scenario: AA holds in the light theme

- GIVEN the light token set applied via `[data-theme="light"]`
- WHEN shell text is measured against its background
- THEN the contrast is ≥4.5:1
