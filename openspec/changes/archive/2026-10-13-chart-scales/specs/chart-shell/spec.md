# Delta for chart-shell

Issue #121 (Fase F8). The shell toolbar gains two native controls (price-scale
mode, chart type). R21/R23 layout and the frozen chart shell stay in force; the
new controls live beside the interval chips, not in a new controller. R25
(a11y/CSP/no-dep) extends to the two selects.

## MODIFIED Requirements

### Requirement: R25 — Accessibility, CSP, no new dependency

Interactive chips, the toggle, and the F8 scale/type `<select>`s MUST have a
visible focus state and accessible names; state MUST NOT rely on color alone
(`aria-pressed` on chips, native select value for the new controls). No inline
`<script>`/handler MAY be added; the market `Content-Security-Policy` MUST be
unchanged and `requirements.txt` MUST be unchanged.
(Previously: the rule covered the chips and the collapse toggle only.)

#### Scenario: Focus and names

- GIVEN a keyboard user on the chips, the toggle, or the two selects
- WHEN focus moves onto them
- THEN a visible focus indicator appears and each has an accessible name

#### Scenario: CSP and manifest unchanged

- GIVEN the rendered `/market/` page and the manifest
- WHEN inspected
- THEN the CSP equals the prior value, no inline script/handler exists, and no runtime dependency was added

## ADDED Requirements

### Requirement: R26 — Scale and chart-type controls

The toolbar MUST render two native `<select>` controls, one for price-scale mode
(options from `SCALE_MODES`) and one for chart type (options from `CHART_TYPES`),
each with an accessible name, placed in the panel near the interval control. A
scale change MUST emit `scale:changed` (`{mode}`); a type change MUST emit the
rebuild command (`indicator:changed`). Both MUST reflect the restored preference on
boot and MUST NOT be `display:none`/`hidden` (native and Playwright-actionable).
The controls MUST live in the existing `toolbar` controller — no new controller.

#### Scenario: Two native selects exist

- GIVEN the rendered `/market/` page
- WHEN the toolbar is inspected
- THEN both `<select>`s exist with accessible names and no inline handler

#### Scenario: Scale change emits the light event

- GIVEN the scale select
- WHEN a different mode is chosen
- THEN exactly one `scale:changed` is emitted and no `fetchHistory` occurs

#### Scenario: Type change triggers rebuild

- GIVEN the type select
- WHEN a different type is chosen
- THEN the rebuild command is emitted and no `fetchHistory`-less path is skipped

#### Scenario: Controls restore the preference

- GIVEN a saved `scale_mode`/`chart_type`
- WHEN the page boots
- THEN each select reflects the saved value

#### Scenario: No new controller

- GIVEN the change
- WHEN the controller inventory is inspected
- THEN the two selects live in `controllers/toolbar.js` and no controller was added

## Non-Applicable Domains

- **core-domain-boundary**: N/A — served template/CSS/JS only; `src/` untouched.
- **security-invariants**: no new CSP surface; the read-only scanner stays clean.
