# chart-shell Specification

## Purpose

Visible shell around the merged F0/F1 market chart (issue #116, Fase F3): a
full-height responsive chart, TradingView-style interval chips that preserve the
`#interval` select, and a collapsible sidebar. HTML/CSS + small controller JS
only; no new dependency, CSP unchanged. Frozen seams (`window.marketChart` 8
keys, `window.SmcOverlayCore`) are untouched. New capability — no prior spec.

## Requirements

### Requirement: R20 — Full-height chart (autoSize host + resolved container)

`chart-host.js` `build()` MUST construct the chart with `autoSize: true` (v5
ResizeObserver) and MUST NOT pass a fixed `height`. `#chart` MUST have a
resolved height derived from the viewport (`dvh`-based, with a `min-height`
floor) so the chart fills the available viewport height instead of a fixed
480px. The old CSS `min-height:460px` floor MAY remain as the fallback. No
fixed pixel height MUST be the authoritative sizing.

#### Scenario: Chart fills the viewport height

- GIVEN a logged-in browser on `/market/` at a normal desktop viewport
- WHEN the chart boots
- THEN the canvas bounding box height is greater than 480 and approximately the resolved `#chart` height

#### Scenario: Resize follows the container

- GIVEN a booted chart
- WHEN the viewport is resized
- THEN the canvas height tracks `#chart` (ResizeObserver via `autoSize`) without a re-boot

#### Scenario: No fixed height option remains

- GIVEN `chart-host.js`
- WHEN `build()` options are inspected
- THEN `autoSize: true` is present and no numeric `height` option is passed

### Requirement: R21 — Interval chips preserve the hidden select and the command

A `role="group"` of `button.interval-chip[data-interval][aria-pressed]` MUST be
rendered from the SAME 14 intervals as the `<option>` list. The
`<select id="interval">` MUST stay in the DOM visually hidden via `clip`/
`clip-path` (NOT `display:none`/`hidden`) so Playwright `select_option("#interval",…)`
stays actionable. Activating a chip MUST emit the SAME `config:changed` bus
command as the select, set `aria-pressed="true"` on the active chip and
`"false"` on its siblings, and sync `select.value` to the chosen interval. A
select-driven change MUST likewise sync the chips' `aria-pressed`. The active
chip MUST reflect the store's `interval`.

#### Scenario: Chip click switches the interval

- GIVEN a booted chart with `1m` active
- WHEN the `5m` chip is activated
- THEN `aria-pressed` moves from the `1m` chip to the `5m` chip and the chart switches to `5m`

#### Scenario: Hidden select stays action-able (E2E invariant)

- GIVEN the rendered page
- WHEN `page.select_option("#interval", "5m")` runs
- THEN the select is found and set, and the chips reflect `5m` — the 15 existing E2E calls stay green with no assertion edits

#### Scenario: Both paths emit one command

- GIVEN a chip activation and a select change
- WHEN each occurs
- THEN each emits exactly one `config:changed` with the same `{symbol, interval}` shape

#### Scenario: Active chip reflects store

- GIVEN the store `interval` is `1h` after any switch
- WHEN the chips are inspected
- THEN only the `1h` chip has `aria-pressed="true"`

### Requirement: R22 — Keyboard-operable chips

Chips MUST be focusable and activatable from the keyboard; Enter and Space MUST
activate the focused chip, and arrow keys MUST move focus across the chip group.

#### Scenario: Enter/Space activates

- GIVEN focus on the `15m` chip
- WHEN Enter (or Space) is pressed
- THEN the interval switches to `15m` and `aria-pressed` updates

#### Scenario: Arrows move focus

- GIVEN focus on a chip
- WHEN Left/Right arrows are pressed
- THEN focus moves to the adjacent chip

### Requirement: R23 — Collapsible sidebar ≤820px

A `<button type="button" aria-expanded aria-controls>` MUST toggle the sidebar
(`.panel`: pairs, interval, indicators, smc, drawings) between expanded and
collapsed via a CSS class (e.g. `.panel-collapsed`). The toggle MUST be visible
at ≤820px and MUST update `aria-expanded` to match the panel's state. Desktop
(>820px) MAY keep the panel always visible with the toggle hidden.

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
- WHEN the page loads
- THEN the sidebar is visible and the shell behavior is unchanged

### Requirement: R24 — 375px: no horizontal overflow

At a 375px viewport the page MUST NOT scroll horizontally
(`scrollWidth <= clientWidth + 1`). In particular the chip row MUST wrap
(`flex-wrap`) rather than overflow, and the single-column grid MUST fit.

#### Scenario: No overflow at 375px

- GIVEN a logged-in browser at 375×800
- WHEN the page loads
- THEN `document.documentElement.scrollWidth <= clientWidth + 1`

### Requirement: R25 — Accessibility, CSP, no new dependency

Interactive chips and the toggle MUST have a visible focus state and accessible
names; state MUST NOT rely on color alone (`aria-pressed` present). No inline
`<script>`/handler MAY be added; the market `Content-Security-Policy` MUST be
unchanged and `requirements.txt` MUST be unchanged.

#### Scenario: Focus and names

- GIVEN a keyboard user on the chips or the toggle
- WHEN focus moves onto them
- THEN a visible focus indicator appears and each has an accessible name

#### Scenario: CSP and manifest unchanged

- GIVEN the rendered `/market/` page and the manifest
- WHEN inspected
- THEN the CSP equals the prior value, no inline script/handler exists, and no runtime dependency was added

## Non-Applicable Domains

- **core-domain-boundary**: N/A — served template/CSS/JS only; `src/` untouched.
- **security-invariants**: no new CSP surface; R11 read-only scanner stays clean.
