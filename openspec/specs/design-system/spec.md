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
properties, plus a `.num` utility using `font-variant-numeric: tabular-nums`.

#### Scenario: Anonymous stylesheet loads
- GIVEN an anonymous client
- WHEN it requests the theme stylesheet route
- THEN the response is 200 with `Content-Type: text/css`

#### Scenario: Tokens are present
- GIVEN the served stylesheet
- WHEN inspected
- THEN it declares the `:root` custom properties (surfaces, text, accent, up/down, scale, spacing, radius)

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

Text MUST meet WCAG AA contrast against the dark theme. Interactive elements
MUST have a visible focus state (`:focus-visible`). Navigation MUST be
keyboard-operable and use semantic landmarks. Critical state MUST NOT rely on
color alone.

#### Scenario: Visible focus
- GIVEN a keyboard user
- WHEN focus moves to a nav link or form control
- THEN a visible focus indicator appears

### Requirement: R7 — CSP unchanged, no inline script

No inline `<script>` and no inline event handler MAY be introduced. The
`Content-Security-Policy` header value MUST remain unchanged (no `unsafe-inline`
for `script-src`). The pre-existing inline `onclick` in `invite_create.html`
MUST be removed (its behavior moved to same-origin JavaScript).

#### Scenario: CSP header unchanged
- GIVEN a rendered page
- WHEN the response header is inspected
- THEN `Content-Security-Policy` equals the prior value (script-src strict, no unsafe-inline)

#### Scenario: No inline handler remains
- GIVEN the templates
- WHEN scanned
- THEN no inline event handler or inline `<script>` is present

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
