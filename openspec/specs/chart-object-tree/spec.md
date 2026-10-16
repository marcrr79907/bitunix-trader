# chart-object-tree Specification

## Purpose

Unified Object Tree for the market chart (issue #118, F5): one `role="tree"`
listing drawings AND active indicators, each row carrying per-row visible / lock /
delete / select. Replaces `#drawing-list` (`drawings.js:32-46`) and the indicators
`fieldset` (`chart.html:46-68`). Hide and lock are persistent (owner decision B).
Renders from `tool-icons-core.js`; every icon is JS-built inline SVG — no inline
handler/script, CSP unchanged, no new dependency, `src/` untouched. New
capability — no prior spec.

## Requirements

### Requirement: R1 — Tree structure (role tree / treeitem / group)

The tree MUST render as `<ul role="tree" aria-label="…">` with one group-parent
`role="treeitem"` `aria-expanded` per category (Drawings, Indicators) wrapping a
`role="group"` `<ul>`. Each object row MUST be a `role="treeitem"` with
`aria-selected` reflecting selection. Group parents MUST expand/collapse without
refetch. Membership MUST be **active-only**: drawings for the current
`(user, symbol)` and indicators that are in the loaded layout — the registry's
inactive tokens MUST NOT be listed (the ADD counterpart lives in the sibling
`chart-indicator-add` capability).

#### Scenario: Tree lists drawings and active indicators

- GIVEN a chart with 2 drawings and a layout holding `{sma20, ema20}`
- WHEN the tree renders
- THEN the Drawings group lists 2 rows and the Indicators group lists exactly the 2 active tokens (no registry tokens)

#### Scenario: Group parents expand/collapse

- GIVEN the Indicators group expanded
- WHEN its parent is toggled
- THEN the child rows hide and `aria-expanded="false"`; toggling back shows them with `aria-expanded="true"` and no network request

### Requirement: R2 — Per-row actions

Each row MUST expose native `<button type="button">` controls: **eye**
(visibility toggle, `aria-pressed` = current visible), **lock** (drawings only,
`aria-pressed` = current locked), **delete** (`aria-label="Delete …"`), and
**select** (row focus / Enter sets `aria-selected`). Eyeball/lock state MUST
reflect the PERSISTED value on render. The eye MUST emit `drawing:changed` with
`{visible}` (drawings) or `indicator:visibility` with `{token, visible}`
(indicators); lock MUST emit `drawing:changed` with `{locked}`; delete MUST emit
the existing `drawing:delete`; select MUST emit the existing
`drawing:selected`. No new drawing bus event MAY be added.

#### Scenario: Eye toggles drawing visibility and persists

- GIVEN a drawing row with `visible:true`
- WHEN its eye is activated
- THEN `drawing:changed {visible:false, persist:true}` is emitted, the eye shows `aria-pressed="false"`, and a partial `PUT` is observed

#### Scenario: Eye toggles indicator visibility

- GIVEN an indicator row for `sma20`
- WHEN its eye is activated
- THEN `indicator:visibility {token:"sma20", visible:false}` is emitted and no `indicator:changed`/refetch occurs

#### Scenario: Lock toggles and persists

- GIVEN a drawing row with `locked:false`
- WHEN its lock is activated
- THEN `drawing:changed {locked:true, persist:true}` is emitted and the lock shows `aria-pressed="true"`

#### Scenario: Delete and select use existing events

- GIVEN a drawing row
- WHEN delete is activated
- THEN `drawing:delete` is emitted with its id
- WHEN the row is selected (Enter/click)
- THEN `drawing:selected` is emitted and `aria-selected="true"` moves to that row

#### Scenario: Indicators have no lock control

- GIVEN an indicator row
- WHEN its controls are inspected
- THEN it exposes eye and delete but no lock button

### Requirement: R3 — Keyboard tree navigation

The tree MUST be keyboard-operable with a single roving `tabindex="0"` (rest
`-1`): Up/Down MUST move focus between visible `treeitem`s; Right/Left MUST
expand/collapse a focused group parent; Enter MUST select the focused row; Delete
MUST delete the focused row (drawings). Focus MUST be visible.

#### Scenario: Up/Down moves focus

- GIVEN focus on the first row
- WHEN `ArrowDown` is pressed
- THEN `document.activeElement` is the next visible treeitem

#### Scenario: Left/Right collapse and expand

- GIVEN focus on a group parent
- WHEN `ArrowRight` then `ArrowLeft` are pressed
- THEN it expands then collapses, with `aria-expanded` tracking

#### Scenario: Enter selects, Delete deletes

- GIVEN a focused drawing row
- WHEN `Enter` is pressed, then `Delete`
- THEN the row is selected (event emitted) then deleted (event emitted)

### Requirement: R4 — Hidden/locked reflect persisted state; reveal does not refetch

A row's eye/lock state MUST render from the persisted model (`Drawing.visible`/
`locked`, layout `visible`). Toggling an indicator eye MUST NOT trigger a rebuild,
refetch, or `setData` (#68); drawings hide via render, not removal. A hidden
object MUST stay listed (parked), not deleted.

#### Scenario: Reload reflects persistence

- GIVEN a drawing saved with `visible:false, locked:true`
- WHEN the page reloads
- THEN its row shows the eye `aria-pressed="false"` and lock `aria-pressed="true"` while the row still exists

#### Scenario: Indicator hide is option-only

- GIVEN an active indicator
- WHEN its eye hides it
- THEN the series visibility changes via the option-only host path with no `setData`/`update` and no `indicator:changed`

### Requirement: R5 — Accessibility, CSP, size ceiling, seam

Every control MUST have an accessible name and state MUST NOT be color-only. No
inline `<script>`/handler MAY be added; CSP and `requirements.txt` unchanged.
`controllers/object-tree.js` MUST stay ≤300 lines, live in `CONTROLLER_ALLOWLIST`
and the modulepreload block, and MUST NOT import `main.js`. `window.marketChart`
MUST keep exactly its 8 frozen keys.

#### Scenario: CSP and names

- GIVEN the rendered tree
- WHEN inspected
- THEN the CSP equals the prior value, no inline script/handler exists, and every button/row has an accessible name

#### Scenario: Ceiling and seam

- GIVEN the delivered `object-tree.js`
- WHEN the size guard and seam check run
- THEN it is ≤300 lines, served 200 under `/market/`, and `window.marketChart` has exactly 8 keys
