# Archive Report: f5-chart-toolbar

**Archived**: 2026-10-16
**Change**: `f5-chart-toolbar` (issue #118, Fase F5)
**Verdict**: `PASS_WITH_WARNINGS` (0 blockers, 0 critical; 2 warnings carried —
W1 R14 controller-count drift 10→11, W2 toolbar Enter-activation untested; 4
non-blocking suggestions S1–S4)
**Delivery**: Feature Branch Chain, 8 PRs, all **based on the tracker**
`feat/f5-chart-toolbar` — **#170 / #171 / #178 / #179 / #180 / #181 / #182** →
tracker **#183** → `develop` @ `b5cfcde`, merged.
**Branch**: `feat/f5-chart-toolbar` (tracker) → `develop`.
**Issue**: #118 (Ola 4 / F5). Slice chain: S1 (`da233e3`/`bc0d710`/`ca2a0be`) →
S2 (`42e0267`/`3257191`/`139784d`) → S3 (`2adc12c`/`f78a4e7`/`a08066b`/`f714604`/
`2605718`/`d308e0a`) → S4 (`fd1a9ce`/`1f98557`/`0bd5b5a`/`0a996f4`/`e614e45`/
`83e2092`) → S5 (`0033e6f`/`d9c2598`). All slices merged to the tracker.

## What Shipped

TradingView parity for the chart sidebar: a **vertical grouped icon toolbar**
replacing the five flat text draw buttons, and one **Object Tree** listing drawings
*and* active indicators with per-row eye / lock / delete / select. Hide and lock
are **persistent** (owner decision B): a hidden object stays on the chart, parked,
not deleted. Two new capabilities, five modified, one migration.

| Area | Delivered |
|------|-----------|
| `chart-toolbar` (NEW) | `role="toolbar"` vertical, grouped `aria-label`s, `aria-pressed` active state, Up/Down/Home/End roving focus; icons from pure `tool-icons-core.js`. |
| `chart-object-tree` (NEW) | `role="tree"`, grouped parents, per-row eye/lock/delete/select, keyboard tree nav, active-only membership. |
| `chart-indicator-add` (NEW, S5/#176) | Add affordance listing registry-minus-active; add = rebuild path, hide = option-only path, distinct. |
| `Drawing.visible`/`locked` + migration `0014` | Additive `AddField` pair (mirrors `0013`), reversible, zero data loss; `parse_drawing`/`_post_drawing`/`_put_drawing` carry both; partial PUT gains `{visible?,locked?}`. |
| `setSeriesVisible` (option-only) | `host.setSeriesVisible(token,bool)` via `applyOptions({visible})`; `indicator:visibility` bus event routed by `main`. |
| Store `indicatorVisible` | 11th `STORE_KEYS` slot; reactive source for the tree; never enters `params`. |
| Toolbar + tree wiring | `chart.html` `#draw-tools`/`#object-tree` replace legacy markup; modulepreload +5; `theme.css` tree tokens. |
| S4 remediation | #177 lost-refetch coverage restored; E2E removed-DOM reconciliation documented; D11 `preference.js` extraction. |

| Area | Delivered |
|------|-----------|
| Size ceiling held | `test_module_size_guard.py` green, EMPTY allowlist; `object-tree.js` 299, `smc.js` 300 (untouched), `chart-host.js` 267, `main.js` 250. |
| Seams held | `window.marketChart` exactly 8 keys; `STORE_KEYS` exactly 11; `#68` — no `setData`/`update` in the visibility path; CSP unchanged; `src/` + `requirements.txt` unchanged. |
| Patch coverage | `diff-cover` vs `origin/develop` = **100%** (`quotes.py`/`views.py`/`models.py`, 15 lines, 0 missing). |

## Requirements Satisfied

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-toolbar | R1–R5 (NEW) | ✅ Toolbar structure/grouping, `aria-pressed` active state, roving-focus keyboard, CSP-clean icons from the pure core, size/allowlist/seam. R3 "Enter activates" holds by native `<button>` construction (see W2). |
| chart-object-tree | R1–R5 (NEW) | ✅ Tree structure (active-only), per-row eye/lock/delete/select reusing existing events, keyboard nav, persisted-state render with option-only indicator hide, a11y/CSP/ceiling/seam. |
| chart-indicator-add | R1–R7 (NEW, #176) | ✅ Registry-minus-active add affordance, rebuild+persist, add-vs-hide boundary, no new bus event, invariants, empty state, reload round-trip. R2 overlay (`vwap`) add has no dedicated E2E (S4, shared code). |
| chart-drawings | R1 (MODIFIED) | ✅ `visible`/`locked` fields + additive reversible `0014`; defaults on new rows. |
| chart-drawings | R2 (MODIFIED) | ✅ CRUD accepts/returns both flags; partial PUT gains `{visible?,locked?}`; non-bool → 400 before write; `interval` accepted-and-ignored. |
| chart-drawings | R6 (MODIFIED) | ✅ `visible:false` renders blank with primitive attached, `autoscaleInfo` null; reveal via `requestUpdate` only. |
| chart-drawings | R9 (MODIFIED) | ✅ Hit-test excludes a `locked:true` **OR** `visible:false` drawing (shared guard `row.locked !== true && row.visible !== false`); still tree-selectable. |
| market-chart | R11 (MODIFIED) | ✅ Drawings endpoint gains flags + hidden/locked render/restore; `visible:false`/`locked:true` excluded from pointer hits. |
| market-chart | R14 (MODIFIED) | ✅ Store vocabulary 10→11; +`tool-icons-core`/`chart-registry-core`; controller inventory +`draw-toolbar`/`object-tree`/`preference`; count is **11** (W1 reconciled). |
| market-chart | R18 (MODIFIED) | ✅ 8-key seam frozen; E2E green **except** removed-DOM assertions, replaced + documented (W2/#177 reconciled). |
| market-chart | R20 (MODIFIED) | ✅ Envelope extends to toolbar/tree/visibility; exactly ONE new event `indicator:visibility`; drawing hide/lock reuse `drawing:changed`. |
| chart-indicator-settings | F2.4 (MODIFIED) | ✅ Store gains `indicatorVisible` top-level key; never leaks into `params`. |
| chart-indicator-settings | F2.5 (MODIFIED) | ✅ `setSeriesVisible` option-only; hidden-at-build set via `applyOptions`; one rebuild per style change. |
| chart-indicator-settings | F2.7 (MODIFIED) | ✅ Layout `visible` round-trips verbatim; absent defaults true; non-bool → 400. |
| chart-shell | R25 (MODIFIED) | ✅ a11y/CSP coverage extends to toolbar + tree; keyboard contracts; CSP/manifest unchanged. |
| chart-shell | R28 (ADDED) | ✅ Legacy `fieldset`/`.draw-tool`/`#drawing-list` replaced by `#draw-tools`/`#object-tree`; modulepreload lists new modules; R23/R24 preserved verbatim. |
| design-system | R6 (MODIFIED) | ✅ Toolbar/tree focus + names; not-color-only active/selected/hidden/locked state; AA light theme. |
| design-system | R7 (MODIFIED) | ✅ Icons via JS-built inline SVG, no `on*`; CSP header unchanged. |
| design-system | R10 (ADDED) | ✅ Toolbar/tree tokens (no literal palette); `:root` + `[data-theme=light]` both declare the tokens; icons inherit `currentColor`. |

**Compliance summary**: 19/19 requirements compliant, all scenarios
compliant-or-documented (verify-report `PASS_WITH_WARNINGS`).

**Preserved untouched** (no requirement dropped):
- `chart-drawings`: R3, R4, R5, R7, R8, R10–R14.
- `market-chart`: R1–R10, R12, R13, R15–R17, R19, R21–R23.
- `chart-shell`: R20–R24 (R23/R24 preserved **verbatim**, not renumbered), R26, R27.
- `chart-indicator-settings`: F2.1–F2.3, F2.6, F2.8–F2.10.
- `design-system`: R1–R5, R8, R9.

## Verify Warnings Carried (non-blocking)

- **W1 — `market-chart` R14 controller count drifted 10→11.** The delta stated
  `8→10`; `views.py:65-79` holds **11** and `test_market_ux.py:146` asserts
  `== 11`. The third controller is `preference` (`0a996f4`), the D11 contingency
  extraction pre-specified in `design.md:55-57`. **Reconciled at archive**: the
  canonical `market-chart` R14 clause now states 11, names `preference`, and
  cites the count assertion. Functional invariant held (all entries served 200;
  import graph resolves).
- **W2 — `chart-toolbar` R3 "Enter activates" has no dedicated test.** No
  `draw-toolbar.test.js`/E2E case presses `Enter`/`Space`. It holds by native
  `<button>` semantics (`draw-toolbar.js:73-81`); the activation path IS covered
  (click + store assert). **Documented at archive** as an explicit coverage note
  inside the canonical `chart-toolbar` R3 scenario — no coverage is claimed that
  does not exist.
- **W2/#177 — `market-chart` R18 "green with NO assertion edits" was unmeetable.**
  S3 deleted the DOM (`#drawing-list`, indicators `fieldset`) those assertions
  checked. **Reconciled at archive**: R18/R20 now read "green except the
  assertions covering the removed DOM, replaced by equivalent coverage
  documented in the E2E" (`test_market_e2e.py:582-620`). Every removed scenario
  got a replacement EXCEPT adding-an-indicator, which became the new
  `chart-indicator-add` capability (issue #176).

## Verify Suggestions Carried (documented gaps)

- **S1** — no automated assertion for the `chart-shell` R28 modulepreload block
  (manually verified: `chart.html:106,110,112,126,127,129`).
- **S2** — no automated assertion that legacy markup (`#drawing-list`/`fieldset`)
  is gone; E2E checks `.drawings .draw-tool == 0`.
- **S3** — `design-system` R10 token names are source-verified only (no stylesheet
  palette scan).
- **S4** — `chart-indicator-add` R2 overlay-add (`vwap`) has no dedicated E2E;
  pane-add (`macd`) path is covered, shared code.

## Follow-up Issues

- **#172–#177** (raised in-chain) — all resolved within the chain. #177 restored
  the lost-refetch coverage; #176 (new capability) delivered as slice **S5**.
- **#149** — pre-existing class-C E2E flake (`test_scale_and_type_round_trip_
  persists_across_reload`), reproduced on a clean `origin/develop` worktree at
  `96bd2f6`; **not introduced by F5**.

## Final Invariant State (verified on develop @ b5cfcde)

| Invariant | Proof | Result |
|---|---|---|
| `window.marketChart` EXACTLY 8 keys | `main.js:55-64`; e2e `test_shell_keeps_seam_at_eight_keys` | ✅ |
| `STORE_KEYS` EXACTLY 11 | `chart-store.js:13-27`; `chart-store.test.js` | ✅ |
| Every `market/**/*.js` ≤300, empty allowlist | `test_module_size_guard.py` (ALLOWLIST `frozenset()`) | ✅ |
| `#68`: no `setData`/`update` writer for visibility | `chart-host.js` `setSeriesVisible` → `applyOptions`; spies green | ✅ |
| Controller allowlist = 11 | `views.py:65-79`; `test_market_ux.py:146` | ✅ |
| No inline handler/script in the diff | `test_market_page_has_no_inline_script_or_handler` | ✅ |
| `requirements.txt`/`src/` unchanged | `git diff` empty | ✅ |
| Migration `0014` additive + reversible | `test_migration_0014.py`; `makemigrations --check` clean | ✅ |
| Patch coverage 100% | `diff-cover` vs `origin/develop` | ✅ |

**Test gates**: `node --test` **254 pass / 0 fail**; `pytest` **972 passed, 84
deselected**; `ruff check`/`format --check` clean; E2E **84/84** on the first full
run (second run showed only the documented readiness-gated flake class).

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-toolbar | **Created** | Full canonical spec (R1–R5); R3 carries the Enter-activation coverage note (W2). |
| chart-object-tree | **Created** | Full canonical spec (R1–R5). |
| chart-indicator-add | **Created** | Full canonical spec (R1–R7); R2 carries the overlay-add coverage note (S4). |
| chart-drawings | Updated | R1 (fields + `0014` scenarios), R2 (flags + partial PUT), R6 (hidden blank + null autoscale), R9 (locked **OR** visible exclusion). R3/R4/R5/R7/R8/R10–R14 preserved. |
| market-chart | Updated | R11 (flags + hidden/locked render), R14 (store 11 keys, cores, controllers = **11** incl. `preference`), R18 (replaced-assertion reconciliation), R20 (toolbar/tree + one new event). R1–R10, R12/R13, R15–R17, R19, R21–R23 preserved. |
| chart-indicator-settings | Updated | F2.4 (`indicatorVisible` slot), F2.5 (`setSeriesVisible` option-only), F2.7 (`visible` round-trip). F2.1–F2.3, F2.6, F2.8–F2.10 preserved. |
| chart-shell | Updated | R25 (a11y/CSP for toolbar+tree); R28 **appended**. R23/R24 preserved **verbatim**. |
| design-system | Updated | R6 (toolbar/tree focus + not-color-only), R7 (icons via JS); R10 **appended**. R1–R5, R8, R9 preserved. |

Delta fit: 3 capabilities NEW (created whole); `chart-drawings` R1/R2/R6/R9
MODIFIED; `market-chart` R11/R14/R18/R20 MODIFIED; `chart-indicator-settings`
F2.4/F2.5/F2.7 MODIFIED; `chart-shell` R25 MODIFIED + R28 ADDED; `design-system`
R6/R7 MODIFIED + R10 ADDED. Every MODIFIED requirement matched by name and
replaced in place; every ADDED/created appended. No requirement dropped.

## Rollback (per-slice, independently revertible)

- **S5 (add)** / **S4 (remediation)**: revert PRs — add affordance gone; refetch
  coverage reverted.
- **S3 (tree + indicator visibility)**: revert PR → tree gone; layout `visible`
  unset (absent = true) — no migration.
- **S2 (toolbar)**: revert PR → legacy draw buttons restored; `setSeriesVisible`
  unused.
- **S1 (flags + registry)**: revert PR → flags gone; registry back inline in
  `chart-host.js`; `python manage.py migrate trading 0013` (additive, zero data
  loss).
- **Tracker**: drop `feat/f5-chart-toolbar`; nothing merged to `develop`/`main`
  until green.

## Bookkeeping

`tasks.md` checkboxes were reconciled to `[x]` at archive (the apply hard contract
forbids editing `openspec/**` during apply); all S1–S5 tasks and the Guard/Edge
Matrix are complete per the verify-report. S4/S5 were remediation/add slices
beyond the original 3-slice task list — noted in the tasks header and here.
