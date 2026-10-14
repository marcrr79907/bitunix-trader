# Delta for chart-shell

Issue #145: **verification-evidence only**. F3 shell behavior already holds and is unchanged; these deltas record that three probe-only scenarios are now guarded by committed E2E tests in `tests/web/test_market_e2e.py`. No production file, no seam key, no CSP change.

## MODIFIED Requirements

### Requirement: R20 — Full-height chart (autoSize host + resolved container)

`chart-host.js` `build()` MUST construct the chart with `autoSize: true` (v5 ResizeObserver) and MUST NOT pass a fixed `height`. `#chart` MUST have a resolved height derived from the viewport (`dvh`-based, with a `min-height` floor) so the chart fills the available viewport height instead of a fixed 480px. The old CSS `min-height:460px` floor MAY remain as the fallback. No fixed pixel height MUST be the authoritative sizing. The "resize follows the container" scenario MUST now be proven by a committed E2E (`tests/web/test_market_e2e.py`) that resizes the viewport and asserts the canvas height tracks `#chart` (absolute delta ≤ 2) while `window.marketChart.ready` stays `true` (no re-boot).
(Previously: resize-follows-container was proven only by a session probe.)

#### Scenario: Chart fills the viewport height

- GIVEN a logged-in browser on `/market/` at a normal desktop viewport
- WHEN the chart boots
- THEN the canvas bounding box height is greater than 480 and approximately the resolved `#chart` height

#### Scenario: Resize follows the container

- GIVEN a booted chart
- WHEN `tests/web/test_market_e2e.py` resizes the viewport
- THEN the canvas height tracks `#chart` (absolute delta ≤ 2) via `autoSize`, and `ready` stays `true` (no re-boot)

#### Scenario: No fixed height option remains

- GIVEN `chart-host.js`
- WHEN `build()` options are inspected
- THEN `autoSize: true` is present and no numeric `height` option is passed

### Requirement: R22 — Keyboard-operable chips

Chips MUST be focusable and activatable from the keyboard; Enter and Space MUST activate the focused chip, and arrow keys MUST move focus across the chip group. The keyboard scenario MUST now be proven by a committed E2E (`tests/web/test_market_e2e.py`) that moves focus with `ArrowRight` (asserting `document.activeElement`), activates with `Enter`/`Space`, and asserts the `aria-pressed` state and `#interval` value update.
(Previously: keyboard operation was proven only by a session probe.)

#### Scenario: Enter/Space activates

- GIVEN focus on the `15m` chip
- WHEN Enter (or Space) is pressed
- THEN the interval switches to `15m`, `aria-pressed` updates, and `#interval` value syncs

#### Scenario: Arrows move focus

- GIVEN focus on a chip
- WHEN Left/Right arrows are pressed
- THEN `document.activeElement` moves to the adjacent chip

### Requirement: R23 — Collapsible sidebar ≤820px

A `<button type="button" aria-expanded aria-controls>` MUST toggle the sidebar (`.panel`: pairs, interval, indicators, smc, drawings) between expanded and collapsed via a CSS class (e.g. `.panel-collapsed`). The toggle MUST be visible at ≤820px and MUST update `aria-expanded` to match the panel's state. Desktop (>820px) MAY keep the panel always visible with the toggle hidden. The desktop scenario MUST now be proven by a committed E2E (`tests/web/test_market_e2e.py`) that at >820px asserts `.panel-toggle` is not visible, `#panel` and `#chart` are visible, and the accessible names / `aria-expanded` / `aria-pressed` and a visible focus outline hold.
(Previously: the desktop-hidden invariant was proven only by a session probe.)

#### Scenario: Toggle collapses the panel on small screens

- GIVEN a 375px-wide viewport
- WHEN the toggle is activated
- THEN the sidebar is hidden and `aria-expanded="false"`

#### Scenario: Toggle expands again

- GIVEN a collapsed panel
- WHEN the toggle is activated again
- THEN the sidebar is shown and `aria-expanded="true"`

#### Scenario: Desktop unchanged

- GIVEN a viewport wider than 820px
- WHEN `tests/web/test_market_e2e.py` loads the page
- THEN `.panel-toggle` is not visible while `#panel` and `#chart` are visible, the group/toggle chips carry accessible names and `aria-pressed`/`aria-expanded`, and a focused chip shows a visible outline
