# Verify Report: f5-chart-toolbar

**Verdict**: `PASS_WITH_WARNINGS`
**Verified by**: sdd-verify executor (evidence-based; gates re-run on this machine).
**Branch**: `feat/f5-chart-toolbar` (tracker) @ `d9c2598`; base `origin/develop` @ `96bd2f6`.
**Chain**: S1 (`da233e3`/`bc0d710`/`ca2a0be`) → S2 (`42e0267`/`3257191`/`139784d`) →
S3 (`2adc12c`/`f78a4e7`/`a08066b`/`f714604`/`2605718`/`d308e0a`) →
S4 (`fd1a9ce`/`1f98557`/`0bd5b5a`/`0a996f4`/`e614e45`/`83e2092`) →
S5 (`0033e6f`/`d9c2598`). All slices merged to the tracker.

## Verdict rationale

Every gate is green, every frozen invariant holds, patch coverage is 100%, and the
full E2E suite passes 84/84 on a clean run. Two spec scenarios lack a dedicated
covering test (toolbar Enter-activation; modulepreload/R28 + design-token source
scans) and the `market-chart` R14 "controller count grows to 10" clause drifted to
11 via the D11 `preference.js` extraction — all non-functional. Hence
`PASS_WITH_WARNINGS`, not a clean `PASS` and not a `FAIL`.

## Requirement coverage matrix

Legend: **file:test-name** — ✅ PASS (test asserts the scenario) ·
⚠️ PARTIAL (asserted indirectly / weaker than the scenario text) ·
❌ MISSING (no covering assertion).

### chart-toolbar

| Scenario | Evidence | Result |
|---|---|---|
| R1 Toolbar and groups render | `tests/web/test_market_e2e.py::test_draw_toolbar_renders_groups_and_sets_store` (role=toolbar, 4 groups, 5 tools, `.drawings .draw-tool` == 0); `tests/js/draw-toolbar.test.js::renders a vertical role=toolbar…` | ✅ |
| R1 Tool activation sets store and command | `tests/web/…::test_draw_toolbar_renders_groups_and_sets_store` (fib click → `aria-pressed`); `tests/js/draw-toolbar.test.js::activating a tool writes store.tool…` | ✅ |
| R1 Singleton group allowed | `tests/js/tool-icons-core.test.js::TOOL_GROUPS: 5 kinds grouped 2/1/1/1`; e2e group count 4 | ✅ |
| R2 Pressed follows store | `tests/js/draw-toolbar.test.js` (activation) + `an external store.tool change syncs aria-pressed` | ✅ |
| R2 Cancel clears pressed | `tests/js/draw-toolbar.test.js::an external store.tool change syncs…` (store.set tool:null → all false) | ✅ |
| R3 Arrows move focus | `tests/js/draw-toolbar.test.js::roving tabindex…ArrowDown moves focus`; e2e keyboard ArrowDown | ✅ |
| R3 Home and End jump | `tests/js/draw-toolbar.test.js` (End → btns[4], Home → btns[0]) | ✅ |
| R3 Enter activates | — native `<button>`; **no dedicated Enter/Space activation test** | ❌ **WARNING** |
| R4 No inline handler | `tests/web/test_market_ux.py::test_market_page_has_no_inline_script_or_handler`; e2e icon count 5 | ✅ |
| R4 Core is dependency-free | `tests/js/tool-icons-core.test.js::purity: the icon core imports nothing` | ✅ |
| R5 Guard and allowlist | `tests/web/test_module_size_guard.py` (draw-toolbar 99 lines); `test_market_ux.py::test_controller_allowlist_routes_serve_javascript` + import-graph; seam 8 keys (`test_shell_keeps_seam_at_eight_keys`) | ✅ |

### chart-object-tree

| Scenario | Evidence | Result |
|---|---|---|
| R1 Tree lists drawings and active indicators | `tests/js/object-tree.test.js::renders role=tree with Drawings + Indicators groups (active-only)`; e2e `test_boot_restores_saved_layout` | ✅ |
| R1 Group parents expand/collapse (no refetch) | `tests/js/object-tree.test.js::Left/Right collapse/expand a focused group parent` (aria-expanded; no fetch in controller) | ✅ |
| R2 Eye toggles drawing visibility and persists | `tests/web/…::test_tree_drawing_eye_persists_visible_false` (PUT body `{"visible": false}`); `tests/js/object-tree.test.js::drawing eye emits drawing:changed {visible,persist}` | ✅ |
| R2 Eye toggles indicator visibility | `tests/js/object-tree.test.js::indicator eye emits indicator:visibility + store slot, no rebuild`; e2e `test_tree_keyboard_navigation_and_indicator_visibility` | ✅ |
| R2 Lock toggles and persists | `tests/js/object-tree.test.js::drawing lock emits drawing:changed {locked,persist}`; e2e `test_tree_row_actions_reachable_and_activatable_by_keyboard` (locked===true) | ✅ |
| R2 Delete and select use existing events | `tests/js/object-tree.test.js::delete emits drawing:delete…` + `select emits drawing:selected…`; e2e `test_tree_row_delete_fires_delete` | ✅ |
| R2 Indicators have no lock control | `tests/js/object-tree.test.js::indicators expose eye + delete + settings but no lock` | ✅ |
| R3 Up/Down moves focus | `tests/js/object-tree.test.js::roving tabindex…ArrowDown moves focus`; e2e tree keyboard test | ✅ |
| R3 Left/Right collapse/expand | `tests/js/object-tree.test.js::Left/Right collapse/expand a focused group parent` | ✅ |
| R3 Enter selects, Delete deletes | `tests/js/object-tree.test.js` (Enter → drawing:selected); Delete via `bindNav` + e2e delete | ✅ |
| R4 Reload reflects persistence | `tests/js/object-tree.test.js::persisted flags render on first paint`; e2e `test_hidden_drawing_is_not_pointer_grabbable` (visible:false row present) | ✅ |
| R4 Indicator hide is option-only | e2e `test_indicator_eye_hides_option_only_and_delete_removes_pane` (no kline refetch); `chart-host.test.js::setSeriesVisible flips options().visible` | ✅ |
| R5 CSP and names | `test_market_page_has_no_inline_script_or_handler`; accessible names in controller (`aria-label` on every action button) | ✅ |
| R5 Ceiling and seam | `test_module_size_guard.py` (object-tree 299 ≤ 300); seam 8 keys e2e | ✅ |

### chart-drawings

| Scenario | Evidence | Result |
|---|---|---|
| R1 0014 additive and reversible | `tests/web/test_migration_0014.py::test_0014_adds_two_fields_forward_then_reverses_without_data_loss` | ✅ |
| R1 Defaults on new rows | `tests/web/test_isolation.py::test_drawing_visible_locked_defaults` | ✅ |
| R2 GET lists flags | `tests/web/test_market_api.py::test_drawings_post_carries_explicit_flags_and_get_lists_them` | ✅ |
| R2 POST creates row with id and flags | same test | ✅ |
| R2 POST defaults absent flags | `test_drawings_post_defaults_absent_flags` | ✅ |
| R2 Stale interval accepted and ignored | `test_drawings_post_accepts_and_ignores_stale_interval` | ✅ |
| R2 PUT updates points, style, and flags | `test_drawings_put_updates_both_flags_round_trip` | ✅ |
| R2 PUT partial body keeps other fields | `test_drawings_put_partial_visible_only_keeps_locked_and_points` | ✅ |
| R2 PUT non-bool flag → 400 before write | `test_drawings_put_non_bool_flag_is_400_and_writes_nothing` | ✅ |
| R2 PUT miss or A≠B is 404 | `test_drawings_put_miss_is_404` + `test_isolation.py::test_drawing_cross_user_get_denied` | ✅ |
| R2 PUT kind is immutable | `test_drawings_put_kind_immutable_differing_is_400_and_no_write` | ✅ |
| R2 DELETE + 404 + anon + CSRF | `test_drawings_put_requires_csrf`, anon redirects, delete by id e2e | ✅ |
| R6 Hidden drawing renders blank, autoscale null | `tests/js/drawing-primitive.test.js::renderShape early-returns blank…` + `autoscaleInfo is null when the drawing is hidden` | ✅ |
| R6 Reveal uses requestUpdate only | `drawing-primitive.js:37` live read; `drawings.js:105` requestUpdate on toggle; reveal e2e via eye | ✅ |
| R6 Drag never touches series data path | `tests/js/drawing-primitive.test.js` + drawing-interaction E2E PUT | ✅ |
| R9 Locked not pointer-selectable/draggable | `tests/web/…::test_locked_drawing_is_not_pointer_grabbable_but_tree_selectable`; `drawing-interaction-controller.test.js::pointerRows…` | ✅ |
| R9 Locked stays tree-selectable | same e2e test (tree click → aria-selected) | ✅ |

### market-chart

| Scenario | Evidence | Result |
|---|---|---|
| R11 GET/POST/PUT/DELETE flags matrix | `tests/web/test_market_api.py` drawings flag tests (see chart-drawings) | ✅ |
| R11 Hidden and locked render and restore | e2e `test_hidden_drawing_is_not_pointer_grabbable`, `test_locked_…tree_selectable` | ✅ |
| R11 Market page stays CSP-clean | `test_market_page_has_no_inline_script_or_handler` | ✅ |
| R14 Inventory and no-cycle | `tests/web/test_market_ux.py::test_import_graph_routes_resolve`; controllers never import `main` (grep) | ✅ |
| R14 Store never holds candles | `tests/js/chart-store.test.js::set never admits candle data…` + `STORE_KEYS is exactly the UI/config vocabulary (11…)` | ✅ |
| R14 Size ceiling with empty allowlist | `test_module_size_guard.py` (ALLOWLIST empty; smc 300, object-tree 299) | ✅ |
| R14 New cores and controllers are served | `test_controller_allowlist_routes_serve_javascript` + module serve test | ✅ |
| R14 Controller allowlist count grows | `tests/web/test_market_ux.py:146` asserts `== 11`; **spec text says 10** | ⚠️ **WARNING** (spec drift) |
| R18 Seam shape frozen | e2e `test_shell_keeps_seam_at_eight_keys`, `test_dialog_has_no_inline_handler_and_seam_frozen` | ✅ |
| R20 Seam stays 8 keys | e2e seam tests | ✅ |
| R20 Exactly one new bus event | `tests/js/chart-bus.test.js`; `chart-bus.js:8-20` (only `indicator:visibility` added) | ✅ |
| R20 Visibility toggle is option-only | `chart-host.test.js::setSeriesVisible flips options().visible…`, e2e indicator-eye hide (no refetch) | ✅ |
| R20 Existing E2E stays green unedited | 84/84 E2E pass; removed-DOM reconciliation documented in `test_market_e2e.py:582-620` | ✅ |

### chart-indicator-settings

| Scenario | Evidence | Result |
|---|---|---|
| F2.4 Store vocabulary | `tests/js/chart-store.test.js::STORE_KEYS is exactly…(11 incl. indicatorVisible)` | ✅ |
| F2.4 No visibility leak into params | `tests/js/chart-controllers.test.js::klineUrlFrom…styles never leak` (params path); store key is top-level | ✅ |
| F2.5 setSeriesVisible is option-only | `tests/js/chart-host.test.js::setSeriesVisible flips options().visible for the token only (option-only, #68)` | ✅ |
| F2.5 Hidden at build stays option-only | `chart-host.test.js::build applies initial hidden state from state.indicatorVisible` (`chart-host.js:143`) | ✅ |
| F2.5 One rebuild per style change | e2e `test_style_change_rebuilds_exactly_once` (createChart counter === 1) | ✅ |
| F2.5 Legend output ignores style precision | `tests/js/legend-core.test.js::style guard rejects modules that read styles or priceFormat` | ✅ |
| F2.7 Round-trip verbatim | `test_market_api.py::test_layout_put_then_get_round_trips_visible_verbatim` | ✅ |
| F2.7 Absent visible defaults to true | `test_parse_layout_indicators_absent_visible_is_not_injected` | ✅ |
| F2.7 Bad style / non-bool visible → 400 | `test_parse_layout_indicators_non_bool_visible_is_400` + `test_layout_put_non_bool_visible_is_400_and_writes_nothing` | ✅ |

### chart-indicator-add

| Scenario | Evidence | Result |
|---|---|---|
| R1 Lists only inactive tokens | `tests/js/object-tree.test.js::add affordance lists ONLY inactive registry tokens`; `tests/js/add-indicator-core.test.js::inactiveTokens…` | ✅ |
| R1 Keyboard-operable | `tests/js/object-tree.test.js::add control is a native keyboard-operable button` | ✅ |
| R2 Adding a pane indicator renders and refetches | e2e `test_add_indicator_renders_pane_and_refetches` (MACD pane + `indicators=…macd` kline) | ✅ |
| R2 Adding an overlay indicator renders + PUT | **no dedicated overlay-add (vwap) e2e**; path shared with pane-add (store.set+emit+saveLayout) | ⚠️ **SUGGESTION** |
| R3 Add rebuilds while hide stays option-only | e2e `test_indicator_eye_hides_option_only_and_delete_removes_pane` + add-refetch test (two distinct paths) | ✅ |
| R4 Event vocabulary unchanged | `tests/js/chart-bus.test.js`; object-tree test `add reuses indicator:changed; no add-specific bus event` | ✅ |
| R5 Seam and store frozen | `chart-store.test.js` (11); e2e seam 8 keys; guard ≤300 | ✅ |
| R6 Empty state when all tokens active | `tests/js/object-tree.test.js::all tokens active disables the add affordance` | ✅ |
| R7 Reload restores the added indicator | e2e `test_add_indicator_persists_across_reload` | ✅ |

### chart-shell

| Scenario | Evidence | Result |
|---|---|---|
| R25 Focus and names | `test_market_page_has_no_inline_script_or_handler`; e2e focus tests; accessible names in controllers | ✅ |
| R25 Toolbar and tree keyboard-operable | toolbar + tree JS/E2E keyboard tests | ✅ |
| R25 CSP and manifest unchanged | `test_csp_present_on_market_page`; `requirements.txt` diff empty | ✅ |
| R28 Legacy markup replaced, mount points present | e2e toolbar test (`.drawings .draw-tool` == 0) + manual `chart.html:58,60` (`#draw-tools`, `#object-tree`); **no test asserts `#drawing-list`/fieldset gone** | ⚠️ **SUGGESTION** |
| R28 Preload lists the new modules | Manual: `chart.html:106,112,126,127` list `tool-icons-core`, `chart-registry-core`, `draw-toolbar`, `object-tree`; **no automated preload assertion** | ⚠️ **SUGGESTION** |
| R28 Sidebar invariants preserved | e2e `test_no_horizontal_overflow_at_375`, `test_panel_toggle_collapses_and_expands_at_375` | ✅ |

### design-system

| Scenario | Evidence | Result |
|---|---|---|
| R6 Visible focus | `test_shell_desktop_panel_and_chip_a11y`; `theme.css:43-48` focus-visible rule | ✅ |
| R6 Toolbar/tree state is not color-only | `theme.css:169` (2px border + surface lift) + `object-tree.js` icon swap (`syncBtn`); js tests assert `aria-pressed` | ✅ |
| R6 AA holds in light theme | `tests/js/theme-core.test.js::contrast…` (contrast checks) | ✅ |
| R7 CSP header unchanged | `test_csp_present_on_market_page` | ✅ |
| R7 No inline handler remains | `tests/web/test_shell.py::test_no_inline_event_handler_in_templates` + `test_no_inline_script_tag`; `tool-icons-core.test.js::iconFor…CSP-clean` | ✅ |
| R10 Tokens used, no hard-coded palette | Manual: `theme.css:169,185-186,198-199` use tokens only; **no automated palette scan** | ⚠️ **SUGGESTION** |
| R10 Both themes define the tokens | Manual: `:root` (`theme.css:16`) and `[data-theme=light]` (`theme.css:31`) both declare `--tree-selected/--tree-hidden/--tree-locked`; **no automated assertion** | ⚠️ **SUGGESTION** |

## Gates

| Command | Result |
|---|---|
| `node --test "tests/js/**/*.test.js"` | **254 pass, 0 fail**, 0 skipped (`tests 254 / pass 254 / fail 0`) |
| `.venv/bin/python -m pytest` | **972 passed, 84 deselected** in 253.73s (E2E are `-m 'not e2e'` deselected per `pyproject.toml:18`) |
| `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | `All checks passed!` / `143 files already formatted` |
| `.venv/bin/python web/manage.py makemigrations --check --dry-run` | `No changes detected` |
| `diff-cover cov.xml --compare-branch=origin/develop --fail-under=100` | **100%** — `quotes.py` 100%, `views.py` 100%, `models.py` 100%; Total 15 lines, 0 missing |
| E2E `pytest tests/web/test_market_e2e.py -m e2e` (first full run) | **84/84 pass** |

## Invariants

| Invariant | Proof | Result |
|---|---|---|
| `window.marketChart` EXACTLY 8 keys | `main.js:55-64` (8 literal keys); e2e `test_shell_keeps_seam_at_eight_keys` asserts `== 8` | ✅ |
| `STORE_KEYS` EXACTLY 11 | `chart-store.js:13-27`; `node` import → `STORE_KEYS len: 11 symbol,interval,indicators,params,styles,smc,scaleMode,chartType,theme,tool,indicatorVisible`; `chart-store.test.js` | ✅ |
| Every `market/**/*.js` ≤300, empty allowlist | `test_module_size_guard.py` (ALLOWLIST `frozenset()`); `wc -l` → smc 300, object-tree 299, chart-host 267, main 250 (guard passes) | ✅ |
| #68: no `setData`/`update` writer for visibility | `chart-host.js:190-194` (`setSeriesVisible` → `applyOptions`); grep finds no `setData/update` in the visibility path; `chart-host.test.js` + e2e spies green | ✅ |
| No inline handler/script in the diff | `git diff … \| grep '^+.*onclick\|onerror\|<script'` → empty; `test_no_inline_event_handler_in_templates`, `test_market_page_has_no_inline_script_or_handler` | ✅ |
| `requirements.txt`/`src/` unchanged | `git diff --stat origin/develop...HEAD -- requirements.txt src/` → **empty** | ✅ |
| `object-tree.js` ≤300 | 299 lines (`test_module_size_guard` green) | ✅ (fragility note below) |

## Findings

### CRITICAL

None.

### WARNING

- **W1 — `market-chart` R14 "controller count grows to 10" drifted to 11.**
  `web/market/views.py:65-79` holds 11 controllers and
  `tests/web/test_market_ux.py:146` asserts `len(...) == 11`. The delta spec
  (`specs/market-chart/spec.md:159-163`) and `tasks.md:38` both state `8→10`. The
  third controller is `preference` (`0a996f4`), the D11 contingency extraction
  pre-specified in `design.md:55-57`. Functional invariant holds (every entry is
  served 200 and the import graph resolves — `test_import_graph_routes_resolve`),
  but the spec/task text is stale and the count test no longer matches its own
  documented delta. Recommend archiving one of: (a) amend the spec clause to 11
  with the `preference` addition noted, or (b) revert the preference extraction.
- **W2 — `chart-toolbar` R3 "Enter activates" has no dedicated test.**
  No `tests/js/draw-toolbar.test.js` case and no E2E case press `Enter`/`Space`
  on a tool button. Native `<button>` semantics make it true by construction
  (`draw-toolbar.js:73-81`), but the scenario text is not directly exercised.

### SUGGESTION

- **S1 — No automated assertion for `chart-shell` R28 modulepreload block.**
  Manually verified correct (`chart.html:106,112,126,127`), but nothing fails if a
  future module is added to an allowlist and omitted from the preload list.
- **S2 — No automated assertion that legacy markup is gone (`chart-shell` R28).**
  `#drawing-list`/indicators `fieldset` are absent from `chart.html` (manual), and
  the E2E toolbar test checks `.drawings .draw-tool` == 0, but no test asserts the
  removal directly.
- **S3 — `design-system` R10 token names are source-verified only.** Both `:root`
  (`theme.css:16`) and `[data-theme=light]` (`theme.css:31`) declare
  `--tree-selected/--tree-hidden/--tree-locked` and icons use `currentColor`
  (`tool-icons-core.js:29`; `tool-icons-core.test.js:53,78`), but no test scans
  the stylesheet for missing token names or literal palette hex in the new rules.
- **S4 — `chart-indicator-add` R2 overlay-add (`vwap`) untested directly.** Only
  the pane-add (`macd`) path has E2E; the overlay path shares the same
  `store.set`+`indicator:changed` code, so the gap is coverage breadth, not logic.

## Non-blockers / notes

- **Known E2E flake reproduced and confirmed pre-existing.**
  `test_scale_and_type_round_trip_persists_across_reload` fails in isolation on
  HEAD (`playwright … TimeoutError`, DB-teardown noise) **and** on a clean
  `origin/develop` worktree at `96bd2f6` (same `Page.wait_for_function` timeout).
  It is the class-C `#149` flake named in the task brief; not introduced by F5.
- **E2E run variance.** A first full F5 E2E run passed 84/84; a second run showed
  4 failures (`test_panel_toggle_collapses_and_expands_at_375`,
  `test_no_horizontal_overflow_at_375`, `test_confirm_updates_series_and_persists_across_reload`,
  `test_interval_chips_keyboard_navigation`) — all readiness-gated, dev-only
  browser smoke (deselected in CI per `pyproject.toml:18`). Consistent with the
  documented flakiness class, not a feature regression; the deterministic suites
  (254 unit + 972 integration) are stable and green.
- **`object-tree.js` at 299/300 lines** — one line of headroom. S5 added the
  `createAddIndicator` extraction (`add-indicator-core.js`) specifically to stay
  under; any further tree work must extract again. Fragility note only (guard green).
- **`smc.js` AT 300** — untouched by F5 (confirmed by diff stat); guard passes
  (fail triggers only when *over* the ceiling).
- **E2E reconciliation is documented, not silently edited.** `test_market_e2e.py:582-620`
  records each removed-DOM scenario and its replacement (the R18/R20
  "green unedited" clause was legitimately unmeetable by the slice that deletes
  the DOM); adding-an-indicator had no replacement and became issue #176 (S5).

## Blockers

None. W1/W2 are warnings for archive reconciliation, not merge blockers.
