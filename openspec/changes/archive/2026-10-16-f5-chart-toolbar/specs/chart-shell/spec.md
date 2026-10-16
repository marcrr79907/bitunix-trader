# Delta for chart-shell

Issue #118 (F5): the chart shell gains a vertical grouped icon toolbar and a
unified object tree in the panel. This MODIFIES R25 (a11y/CSP coverage extends to
the toolbar and tree) and ADDS R28 (panel markup + modulepreload for the new
modules). The sidebar layout requirements R23 (collapsible sidebar ≤820px) and R24
(375px no horizontal overflow) are PRESERVED verbatim and MUST NOT be renumbered.
R20–R22, R26, R27 stay in force and unmodified.

## MODIFIED Requirements

### Requirement: R25 — Accessibility, CSP, no new dependency

Interactive chips, the toggle, the F8 scale/type `<select>`s, the theme control,
the F5 vertical toolbar (`role="toolbar"`), and the object tree (`role="tree"`)
MUST have a visible focus state and accessible names; state MUST NOT rely on color
alone (`aria-pressed` on chips, toolbar tools, and tree eye/lock controls; native
select value for the selects and the theme control). The toolbar MUST be
keyboard-operable (Up/Down/Home/End roving focus) and the tree MUST be
keyboard-operable (Up/Down, Left/Right expand/collapse, Enter select, Delete
delete) per the `chart-toolbar`/`chart-object-tree` capabilities. No inline
`<script>`/handler MAY be added; all icons MUST be JS-built inline SVG from the
pure `tool-icons-core.js` core; the market `Content-Security-Policy` MUST be
unchanged and `requirements.txt` MUST be unchanged.
(Previously: the rule covered the chips, the toggle, the scale/type selects, and
the theme control.)

#### Scenario: Focus and names

- GIVEN a keyboard user on the chips, the toggle, the selects, a toolbar tool, or a tree row control
- WHEN focus moves onto them
- THEN a visible focus indicator appears and each has an accessible name

#### Scenario: Toolbar and tree are keyboard-operable

- GIVEN focus on a toolbar tool and separately on a tree row
- WHEN arrow keys (and Enter/Delete on the tree) are pressed
- THEN focus and activation follow the `chart-toolbar`/`chart-object-tree` keyboard contracts

#### Scenario: CSP and manifest unchanged

- GIVEN the rendered `/market/` page and the manifest
- WHEN inspected
- THEN the CSP equals the prior value, no inline script/handler exists, and no runtime dependency was added

## ADDED Requirements

### Requirement: R28 — Panel markup and modulepreload for the toolbar and tree

The panel MUST replace the legacy drawings `fieldset`/`.draw-tool` buttons and the
indicators `fieldset`/`#drawing-list` with the toolbar and tree mount points. The
`chart.html` `modulepreload` block MUST list every served module: the two new
controllers (`draw-toolbar.js`, `object-tree.js`) and any new core
(`tool-icons-core.js`, `chart-registry-core.js`) MUST be added (mirrors the
allowlists; a missing preload is a soft miss, a missing allowlist entry is a 404).
R23 (collapsible sidebar ≤820px) and R24 (375px no horizontal overflow) MUST still
hold with the new markup.

#### Scenario: Legacy markup replaced, mount points present

- GIVEN the rendered `/market/` page
- WHEN the panel DOM is inspected
- THEN the legacy `.draw-tool` buttons, `#drawing-list`, and the indicators `fieldset` are gone and the toolbar/tree mount points exist

#### Scenario: Preload lists the new modules

- GIVEN the `chart.html` modulepreload block
- WHEN inspected
- THEN each new controller and core is listed and served 200 under `/market/`

#### Scenario: Sidebar invariants preserved

- GIVEN a 375px viewport with the toolbar and tree rendered
- WHEN the page loads
- THEN `scrollWidth <= clientWidth + 1` (R24) and the panel toggle still collapses/expands (R23)
