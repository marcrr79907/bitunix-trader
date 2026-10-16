# chart-toolbar Specification

## Purpose

TradingView-style vertical grouped icon toolbar for the market chart (issue #118,
F5). Replaces the five flat text draw buttons in `chart.html:80-89`
(`fieldset.drawings` → `.draw-tool[data-kind]`). Renders from the pure
`tool-icons-core.js`, sets `store.tool`, and reflects active state reactively.
Icons are JS-built inline SVG — no inline handler/script, CSP unchanged, no new
dependency, `src/` untouched. New capability — no prior spec.

## Requirements

### Requirement: R1 — Toolbar structure and grouping

The toolbar MUST render as a `role="toolbar"` element with
`aria-orientation="vertical"` and an accessible `aria-label`, containing one
`role="group"` per icon group (lines, fib, shapes, text — vocabulary from
`tool-icons-core.js`). Each tool MUST be a native `<button type="button">` with
an accessible `aria-label` and `data-kind` ∈ `DRAWING_KINDS`
(`drawing-core.js:13`). Activating a tool MUST set `store.tool` and emit the SAME
command the legacy `.draw-tool` buttons used (`drawings.js:218-232`); it MUST NOT
introduce a new bus event. A singleton group (one tool) MAY be rendered.

#### Scenario: Toolbar and groups render

- GIVEN the rendered `/market/` page
- WHEN the toolbar DOM is inspected
- THEN exactly one `role="toolbar"` with a vertical orientation and an accessible name exists, containing `role="group"` parents each with an accessible name, and no `.draw-tool` legacy text button remains

#### Scenario: Tool activation sets store and command

- GIVEN the vertical toolbar
- WHEN the `hline` tool button is activated
- THEN `store.tool === "hline"` and the same create-tool command the legacy button emitted is observed (no new bus event)

#### Scenario: Singleton group allowed

- GIVEN `tool-icons-core` groups 5 kinds into 2/1/1/1
- WHEN the toolbar renders
- THEN each group renders regardless of member count and no fault occurs

### Requirement: R2 — Active state via aria-pressed

The active tool MUST carry `aria-pressed="true"`; every sibling MUST carry
`"false"`. Active state MUST be reflected from the store
(`store.subscribe`) so an external `store.tool` change (cancel, switch) syncs the
toolbar. State MUST NOT rely on color alone (design-system R6).

#### Scenario: Pressed follows store

- GIVEN `store.tool` becomes `"fib"`
- WHEN the toolbar re-renders
- THEN only the `fib` button has `aria-pressed="true"`

#### Scenario: Cancel clears pressed

- GIVEN an active tool
- WHEN the create is cancelled (`store.tool` → `null`)
- THEN every tool button shows `aria-pressed="false"`

### Requirement: R3 — Keyboard operation (roving focus)

Tool buttons MUST be keyboard-focusable with a single roving `tabindex="0"`
(all others `-1`). Up/Down MUST move focus between tool buttons; Home/End MUST
jump to first/last. Enter/Space MUST activate the focused tool natively.
Behavior MUST mirror the interval-chip pattern (`toolbar.js:63-71`).

#### Scenario: Arrows move focus

- GIVEN focus on a tool button
- WHEN `ArrowDown` is pressed
- THEN `document.activeElement` moves to the next tool button

#### Scenario: Home and End jump

- GIVEN focus on a middle tool button
- WHEN `Home` then `End` are pressed
- THEN focus moves to the first tool, then the last tool

#### Scenario: Enter activates

- GIVEN focus on the `trendline` tool
- WHEN `Enter` is pressed
- THEN the tool activates exactly as a click would

> **Coverage note (documented gap, verify W2 / archive 2026-10-16).** This
> scenario has no dedicated test. It holds by construction: every tool is a native
> `<button type="button">` (`draw-toolbar.js:73-81`), so `Enter`/`Space` fire the
> button's `click` handler with no custom key handling. The activation path itself
> IS covered (`tests/js/draw-toolbar.test.js::activating a tool writes
> store.tool…` and the E2E click case); only the explicit Enter-keystroke case is
> missing. Add a `draw-toolbar.test.js` case pressing `Enter` if a future change
> replaces the native `<button>` with a custom element.

### Requirement: R4 — Icons from the pure core (CSP-clean)

Icons MUST render from `tool-icons-core.js` (pure, no imports, no DOM) as
JS-built inline SVG with no event attributes. The toolbar MUST NOT introduce an
inline `<script>` or inline handler; the market `Content-Security-Policy` MUST be
unchanged and `requirements.txt` unchanged. Every control MUST have an accessible
name.

#### Scenario: No inline handler

- GIVEN the rendered toolbar markup and the template
- WHEN scanned
- THEN no `onclick`/inline `<script>` exists, icons are present, and the CSP equals the prior value

#### Scenario: Core is dependency-free

- GIVEN `tool-icons-core.js` source
- WHEN inspected
- THEN it has no `import` statement and builds no network/DOM side effect

### Requirement: R5 — Size ceiling and module boundary

`controllers/draw-toolbar.js` MUST stay ≤300 lines and MUST live in
`CONTROLLER_ALLOWLIST` (`views.py:62-73`) and in the `chart.html` modulepreload
block; it MUST NOT import `main.js`. `tool-icons-core.js` MUST be a pure module
in `MODULE_ALLOWLIST` served same-origin under `/market/`. `window.marketChart`
MUST keep exactly its 8 frozen keys (no new key).

#### Scenario: Guard and allowlist

- GIVEN the delivered modules
- WHEN `tests/web/test_module_size_guard.py` and the allowlist check run
- THEN every touched module is ≤300 lines, `draw-toolbar` and `tool-icons-core` are served 200 under `/market/`, and `window.marketChart` has exactly 8 keys
