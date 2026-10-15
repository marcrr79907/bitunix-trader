# Delta for chart-shell

Issue #148 (DEBT-7). The shell toolbar gains one native theme control above the
fold; the applier sets `data-theme` on the root and wires `matchMedia`. R21/R23
layout and the frozen chart shell stay in force; the new control lives beside the
existing scale/type selects, in the existing `toolbar` controller — no new
controller. R25 (a11y/CSP/no-dep) extends to the theme control.

## MODIFIED Requirements

### Requirement: R25 — Accessibility, CSP, no new dependency

Interactive chips, the toggle, the F8 scale/type `<select>`s, and the theme
control MUST have a visible focus state and accessible names; state MUST NOT rely
on color alone (`aria-pressed` on chips, native select value for the selects and
the theme control). No inline `<script>`/handler MAY be added; the market
`Content-Security-Policy` MUST be unchanged and `requirements.txt` MUST be
unchanged.
(Previously: the rule covered the chips, the toggle, and the scale/type selects.)

#### Scenario: Focus and names

- GIVEN a keyboard user on the chips, the toggle, or the selects
- WHEN focus moves onto them
- THEN a visible focus indicator appears and each has an accessible name

#### Scenario: CSP and manifest unchanged

- GIVEN the rendered `/market/` page and the manifest
- WHEN inspected
- THEN the CSP equals the prior value, no inline script/handler exists, and no runtime dependency was added

## ADDED Requirements

### Requirement: R27 — Theme control

The toolbar MUST render one native theme control with options from the frozen
vocabulary `light`/`dark`/`system` and an accessible name, placed in the panel
near the interval/scale/type controls. Changing it MUST set
`document.documentElement.dataset.theme` to the RESOLVED value, call the host's
option-only `setTheme` (no rebuild), and debounce-PUT `{theme}` to
`/market/api/preference`. It MUST NOT be `display:none`/`hidden` (native and
Playwright-actionable), MUST live in the existing `toolbar` controller (no new
controller), and MUST NOT add a bus event or a `window.marketChart` key.

#### Scenario: Theme control exists and is labelled

- GIVEN the rendered `/market/` page
- WHEN the toolbar is inspected
- THEN the theme control exists with an accessible name and options `light`/`dark`/`system`

#### Scenario: Change flips both layers live

- GIVEN the theme control
- WHEN `light` is chosen
- THEN `document.documentElement.dataset.theme === "light"`, the host `setTheme` runs option-only, and exactly one debounced `PUT {theme:"light"}` is observed

#### Scenario: Control restores the preference

- GIVEN a saved `theme="dark"`
- WHEN the page boots
- THEN the theme control reflects `dark` and the root `data-theme` is `"dark"`

#### Scenario: No new controller or bus event

- GIVEN the change
- WHEN the controller inventory and bus events are inspected
- THEN the control lives in `controllers/toolbar.js`, no controller was added, and no new bus event exists

## Non-Applicable Domains

- **core-domain-boundary**: N/A — served template/CSS/JS only; `src/` untouched.
- **security-invariants**: no new CSP surface; the read-only scanner stays clean.
