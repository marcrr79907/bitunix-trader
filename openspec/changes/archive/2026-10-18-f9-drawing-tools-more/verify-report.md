# Verify Report: f9-drawing-tools-more

```yaml
schema: gentle-ai.verify-result/v1
verdict: pass_with_warnings
blockers: 0
critical_findings: 1
requirements: 12
scenarios: 69
test_command: node --test "tests/js/**/*.test.js" && .venv/bin/python -m pytest -p no:randomly
test_exit_code: 0
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
```

**Change**: f9-drawing-tools-more (issue #122, Fase F9)
**Mode**: Strict TDD (`openspec/config.yaml: strict_tdd: true`)
**Branch**: `feat/f9-drawing-tools-more` @ `729612a` (tracker, S1+S2+S3+S3b merged). Base `develop` @ `1150b07`.
**Chain**: S1 (`6c772ec`/`3349924`/`2cb4540` → merge `d089efc…`/`473dea7`) → S2 (`ed83660`/`abd34aa` → merge `d089efc`) → S3 (`e5febcd`…`06f0fac` → merge `650274f`) → S3b (`2b63606`/`295d038` → merge `729612a`). 28 files, +2151/−162.

## Verdict

`PASS_WITH_WARNINGS` — every gate is green, all frozen invariants hold, and all 8 kinds are covered by node/API/migration/E2E evidence. One spec scenario has no covering test: `market-chart` R20 / "F9 render is option-only" requires the E2E `setData`/`update` spies for an F9 create and drag; the delivered E2E only asserts the ONE-PUT write path. Reported as **CRITICAL** per the brief ("Report a CRITICAL, do not fix it"); the production code has no writer (`drawings.js` contains zero `setData`/`update`), so no invariant is broken and the verdict is `PASS_WITH_WARNINGS`, mirroring the F6/F7 precedents.

## Requirement coverage matrix

Legend: ✅ PASS · ⚠️ PARTIAL · ❌ MISSING (no covering assertion).

### chart-drawings (MODIFIED R1/R4/R5/R6/R10)

| # | Scenario | Evidence | Result |
|---|---|---|---|
| 1 | Many drawings coexist on one chart | `test_market_api.py::test_drawings_many_per_symbol_coexist_without_unique_violation` | ✅ |
| 2 | position is a valid kind | `test_market_api.py::test_position_kind_is_a_member_of_drawing_kinds` | ✅ |
| 3 | The eight F9 kinds are valid members | `test_market_api.py::test_f9_kinds_are_members_of_drawing_kinds` (`DRAWING_KINDS`); `drawing-core.test.js::DRAWING_KINDS exposes the six legacy kinds plus the eight F9 kinds` | ✅ |
| 4 | 0016 is choices-only and reversible | `test_migration_0016.py::test_0016_adds_eight_kinds_forward_then_reverses_without_data_loss` (leaf pin, rows survive both directions); `makemigrations --check` green | ✅ |
| 5 | 0015 is choices-only and reversible | `test_migration_0015.py::test_0015_adds_position_choice_forward_then_reverses_without_data_loss` (adapted for the new 0016 leaf) | ✅ |
| 6 | Unknown kind → 400 before write | `test_market_api.py` invalid matrix (`kind="notreal"`) + `test_parse_drawing_rejects_bad_input` | ✅ |
| 7 | Interval in body never 400 | `test_market_api.py::test_drawings_f9_interval_key_ignored_not_400` | ✅ |
| 8 | Bad shape for kind → 400 | `test_market_api.py` param matrix (`trendline` single point) | ✅ |
| 9 | F9 kind matrix validates per kind | `test_market_api.py::test_drawings_f9_kind_post_get_put_round_trip` (8 kinds) + `::test_drawings_f9_invalid_points_is_400_and_writes_nothing` (24 variants) + `::test_parse_drawing_accepts_each_f9_kind` | ✅ |
| 10 | hline accepts one point | `test_market_api.py` F9 round-trip baseline + legacy hline tests | ✅ |
| 11 | position rejects bad points | `test_market_api.py::test_drawings_position_post_invalid_points_is_400_and_writes_nothing` | ✅ |
| 12 | vline accepts a time-only point | `_F9_VALID_POINTS["vline"]` round-trip + invalid `{"time":"x"}`, `{}`, `{time,price}` variants | ✅ |
| 13 | price accepts a price-only point | `_F9_VALID_POINTS["price"]` round-trip + invalid `{}`, `"x"`, `True`, `{time,price}` | ✅ |
| 14 | channel requires three points | round-trip + invalid 2-point / 4-point / missing p3 price | ✅ |
| 15 | fib_ext requires three points | round-trip + invalid 2-point / extra key | ✅ |
| 16 | ray and fib kinds require two points | invalid 1-point and 3-point variants for `ray`/`fib_time`/`fib_zone` | ✅ |
| 17 | callout requires two points plus text | round-trip + missing/blank/non-str text | ✅ |
| 18 | Validation error matrix | `test_market_api.py` per-key matrix (unknown kind, interval, empty symbol, wrong count, malformed point, vline+price, callout no text, valid→201) | ✅ |
| 19 | Attach one primitive per drawing | `drawing-primitive.test.js` `makeDrawingPrimitive`; E2E `test_boot_restores_saved_drawings` | ✅ |
| 20 | Hidden drawing renders blank without detaching | `drawing-primitive.test.js::renderShape honours the hidden rule for F9 kinds too` (all 8) + hidden-hline/position cases | ✅ |
| 21 | Off-bar anchor degrades gracefully | `drawing-primitive.test.js::renderShape position degrades (no throw) when the entry is off-bar`; `drawing-core.test.js` off-bar legs. F9: `renderTool` guards `ray`/`vline`/`channel`/`callout`/`price`/fib levels `y`, but `fib_ext`/`fib_zone` pass `x1`/`x2` unguarded to `moveTo`/`fillRect` (`drawing-primitive.js:127,143`), so a null x maps to pixel 0 instead of skipping the leg | ⚠️ PARTIAL |
| 22 | Drag never touches the series data path | `drawings.js` contains no `setData`/`update`; primitive redraws via `requestUpdate` (`drawing-primitive.js:220`); node `renderShape` takes no series; E2E `test_drag_f9_kind_is_one_put` asserts ONE PUT. No spy installed for F9 (see CRITICAL) | ✅ code / ❌ scenario spy |
| 23 | Each F9 kind draws its geometry | `drawing-primitive.test.js::renderShape dispatches each F9 kind to renderTool without throwing` + shape/label cases (`price` label, `callout` balloon, fib ratio labels) | ✅ |
| 24 | F9 autoscale includes all anchors | `drawing-primitive.test.js::autoscaleInfo of a channel/fib_ext includes p3` + `…of a price drawing includes its price` | ✅ |
| 25 | Drag a trendline endpoint | `drawing-interaction-core.test.js::applyDrag moves only the grabbed trendline anchor` | ✅ |
| 26 | Drag position level | `…position moves ONLY the dragged stop level` (+ take_profit, entry) | ✅ |
| 27 | F9 handle counts resolve per kind | `drawing-interaction-core.test.js::handlesFor resolves the F9 per-kind counts 2/2/2/2/3/3/1/1` | ✅ |
| 28 | Drag an F9 anchor moves only it | `…applyDrag moves ONLY the dragged F9 anchor (channel p3)` | ✅ |
| 29 | Drag a vline moves time only | `…applyDrag vline moves time only and adds no price` + `drawing-tools-core.test.js::toolDrag for vline…` | ✅ |
| 30 | Move an F9 shape body | `…applyDrag F9 body translates every anchor (fib_ext)` + `toolDrag moving a channel body shifts every anchor` | ✅ |

### chart-toolbar (MODIFIED R1/R3)

| # | Scenario | Evidence | Result |
|---|---|---|---|
| 31 | Toolbar and groups render | `draw-toolbar.test.js::renders a vertical role=toolbar with one role=group per tool group`; E2E `test_draw_toolbar_renders_groups_and_sets_store` (6 groups, 15 buttons) | ✅ |
| 32 | Buttons advertise per-tool shortcuts | `draw-toolbar.test.js::each tool button carries an aria-keyshortcuts value` + `…shows its letter visibly in a .tool-key span` | ✅ |
| 33 | Tool activation sets store and command | `draw-toolbar.test.js::activating a tool writes store.tool and flips aria-pressed` | ✅ |
| 34 | Eight F9 tools render in the extended groups | `tool-icons-core.test.js::TOOL_GROUPS: F9 groups the 15 instruments 6/4/1/2/1/1` + `F9 icons: the eight new tools yield valid, CSP-clean inline SVGs` | ✅ |
| 35 | F9 letters are non-colliding | `draw-toolbar.test.js::TOOL_KEYS gains the eight F9 letters with no collision` | ✅ |
| 36 | Activating an F9 tool writes store.tool with no new event | `draw-toolbar.test.js::an F9 letter fires inside #chart and activates its tool`; `chart-bus.test.js` EVENTS unchanged | ✅ |
| 37 | Arrows move focus | `draw-toolbar.test.js::roving tabindex: exactly one 0 … ArrowDown moves focus` | ✅ |
| 38 | Home and End jump | Same test (`End` → btns[14], `Home` → btns[0]) | ✅ |
| 39 | Letter firing is chart-scoped only | `draw-toolbar.test.js::a tool letter outside #chart does nothing`; E2E `test_tool_letter_fires_only_inside_chart` | ✅ |
| 40 | Letter fires inside the chart | `…a tool letter fires inside #chart`; E2E same | ✅ |
| 41 | F9 letter activates its tool | `…an F9 letter fires inside #chart and activates its tool` (`c`→channel, `z`→fib_zone) | ✅ |

### design-system (MODIFIED R6/R7)

| # | Scenario | Evidence | Result |
|---|---|---|---|
| 42 | Visible focus | `theme.css:47,152` unchanged (`button:focus-visible`, `#chart:focus-visible`) | ✅ |
| 43 | Chart is keyboard-focusable and labelled | Pre-existing `test_market_ux.py` shell a11y (unchanged) | ✅ |
| 44 | Toolbar/tree state is not color-only | `theme.css:186` `aria-pressed` border; pre-existing tree tests | ✅ |
| 45 | Long vs Short is not color-only | Pre-existing F6 marker (`drawing-primitive.js` LONG/SHORT + arrow) | ✅ |
| 46 | Readouts are live DOM | `chart.html:65` `#position-readout[aria-live=polite]`; `test_market_ux.py:301` | ✅ |
| 47 | Escape cancels a draft | `chart-controllers.test.js::Escape cancels a half-collected draft (no POST)`; `drawings.js:230` | ✅ |
| 48 | Context menu keyboard-navigable | Pre-existing F7 tests | ✅ |
| 49 | Undo and redo are announced | Pre-existing F7 `undo.test.js` + E2E | ✅ |
| 50 | Tool shortcut letters are visible | `draw-toolbar.test.js::…visible in a .tool-key span`; E2E count 15 | ✅ |
| 51 | F9 kinds are not color-only | `drawing-primitive.test.js` price label / callout text / fib ratio labels / shape strokes | ✅ |
| 52 | AA holds in the light theme | Pre-existing `theme-core.test.js` contrast (theme.css untouched) | ✅ |
| 53 | CSP header unchanged | `test_market_ux.py::test_csp_present_on_market_page` (middleware untouched) | ✅ |
| 54 | No inline handler remains | `test_market_ux.py::test_market_page_has_no_inline_script_or_handler`; icons are plain strings (`tool-icons-core.js:40-55`) | ✅ |
| 55 | Menu is CSP-clean | Pre-existing F7 (`addEventListener`, no `oncontextmenu`) | ✅ |

### market-chart (MODIFIED R14/R18/R20)

| # | Scenario | Evidence | Result |
|---|---|---|---|
| 56 | Inventory and no-cycle | `test_market_ux.py::test_import_graph_routes_resolve` (every relative import → 200) green; no controller imports `main`; `drawing-core → drawing-tools-core → drawing-core` is an ES-module live binding, not a boot cycle | ✅ |
| 57 | Store never holds candles | `chart-store.test.js::STORE_KEYS is exactly the UI/config vocabulary (11 …)` | ✅ |
| 58 | Size ceiling with empty allowlist | `test_module_size_guard.py` green (`CEILING=300`, `ALLOWLIST=frozenset()`); `drawings.js` 298→264 | ✅ |
| 59 | New cores are served | `test_market_ux.py::test_f9_cores_are_served` (3×200, `text/javascript`) | ✅ |
| 60 | Controller allowlist count unchanged | `views.CONTROLLER_ALLOWLIST` == 15 (asserted in same test) | ✅ |
| 61 | No behavior change | node 486/486, pytest 1048/1048 (+101 E2E); only the toolbar count assertion moved 7→15 | ✅ |
| 62 | Seam shape frozen | `test_market_e2e.py::test_shell_keeps_seam_at_eight_keys` (`Object.keys(...).length == 8`) | ✅ |
| 63 | F9 kinds assert without a seam key | E2E `test_f9_tools_create_their_kind_and_drag_is_one_put` (`marketChart.drawings` + captured POST) | ✅ |
| 64 | SMC core reachable | Pre-existing E2E `SmcOverlayCore.setupMarkers` | ✅ |
| 65 | Seam stays 8 keys | Same as #62 (8-key assertions at `:2246,2357,2586,2892,3060,3181,3267,3423,3490,3530,3692`) | ✅ |
| 66 | Exactly one new bus event (unchanged set) | `chart-bus.js` untouched; F9 emits only the pre-existing string literals `drawing:created` / `drawing:create-failed` | ✅ |
| 67 | STORE_KEYS stays 11 | `chart-store.test.js` (`length === 11`); store file untouched | ✅ |
| 68 | F9 render is option-only | **No test installs the `setData`/`update` spies while creating/dragging an F9 kind.** The delivered E2E asserts ONE POST / ONE PUT only; the spies exist only for the live stream, 5m rebuild, and theme flip | ❌ **MISSING (CRITICAL)** |
| 69 | Existing E2E stays green except replaced assertions | 100/101 in a full run; the single failure rotates between untouched tests (`test_keyboard_delete_removes_selected`, `test_context_menu_duplicate_then_undo_deletes`, `test_drag_put_returns_200…`, `test_undo_announces…`) and each passes in isolation → pre-existing class-C flake #149 | ✅ |

**Compliance summary**: 67/69 fully compliant; 1 PARTIAL (#21); 1 MISSING/CRITICAL (#68).

## Gates

| Gate | Command | Result |
|---|---|---|
| Node unit | `node --test "tests/js/**/*.test.js"` | ✅ `tests 486 / pass 486 / fail 0` |
| Python suite | `.venv/bin/python -m pytest -p no:randomly` | ✅ `1048 passed, 101 deselected in 555.55s` |
| E2E (dev-only) | `.venv/bin/python -m pytest tests/web/test_market_e2e.py -m e2e` | ⚠️ `1 failed, 100 passed` — failure rotates across untouched tests, each green in isolation (#149). F9-specific: `-k f9` → `2 passed` |
| Ruff lint | `.venv/bin/ruff check .` | ✅ `All checks passed!` |
| Ruff format | `.venv/bin/ruff format --check .` | ✅ `147 files already formatted` |
| Migrations | `.venv/bin/python web/manage.py makemigrations --check --dry-run` | ✅ `No changes detected` |
| Patch coverage | `diff-cover` vs `origin/develop` | ➖ not runnable (binary absent). Proxy: `pytest --cov=market.quotes` → `web/market/quotes.py 314 0 100%`; `0016` exercised forward+reverse by `test_migration_0016.py` |

## Invariants

| Invariant | Command / evidence | Result |
|---|---|---|
| `window.marketChart` exactly 8 keys | `main.js:59-68` untouched; E2E `Object.keys(...).length == 8` (11 assertions) | ✅ |
| `STORE_KEYS` exactly 11 | `chart-store.js:13-27` (11 entries) + `chart-store.test.js` | ✅ |
| Every market module ≤300, empty allowlist | `test_module_size_guard.py` green; `ALLOWLIST=frozenset()` | ✅ |
| Module sizes | `drawing-tools-core` **264**, `object-tree` **299**, `smc` **300**, `drawings` **264** (was 298), `drawing-interaction-core` **285**, `drawing-primitive` **242**, `draw-toolbar` **163**, `tool-icons-core` **88**, `fib-tools-core` **108**, `drawing-click-flow-core` **74**, `drawing-core` **172** | ✅ |
| `controllers/smc.js`, `object-tree.js`, `chart-bus.js` byte-untouched | `git diff --exit-code origin/develop...HEAD -- …` → exit 0 | ✅ |
| #68 no `setData`/`update` writer added | grep of the whole diff for added `.setData(`/`.update(` → none; `drawings.js` has zero writer calls; POST only via `createDrawing` (`drawings.js:142-160`) | ✅ |
| No new bus event | `chart-bus.js` unchanged; new code emits pre-existing literals only | ✅ |
| `MODULE_ALLOWLIST` +3 cores | 23→26; `drawing-tools-core`/`fib-tools-core`/`drawing-click-flow-core` present | ✅ |
| `CONTROLLER_ALLOWLIST` == 15 | `views.py:74-92`; asserted in `test_f9_cores_are_served` | ✅ |
| `requirements.txt` / `src/` unchanged | `git diff --stat` → empty | ✅ |
| No inline handler / script | `test_market_page_has_no_inline_script_or_handler`; icons are plain strings with no `on*` | ✅ |
| CSP unchanged | `web/market/middleware.py` untouched; `test_csp_present_on_market_page` | ✅ |
| Read-only boundary | no order/execution path touched; `src/` unchanged | ✅ |

## Findings

### CRITICAL

- **C1 — `market-chart` R20 "F9 render is option-only" has no covering test.** The scenario requires: *"GIVEN a built chart with the `setData`/`update` spies installed / WHEN an F9 drawing is created or dragged / THEN it renders via `requestUpdate` … and neither `setData` nor `update` is called."* Tasks `3.13` explicitly listed "`setData` spy green" in the F9 E2E. The delivered `test_market_e2e.py::test_f9_tools_create_their_kind_and_drag_is_one_put` (`:1016`) asserts only the captured POST/PUT counts; `test_drag_f9_kind_is_one_put` (`:1124`) likewise. The spies in the file (`:441`, `:510`, `:3626`) cover the live stream, the 5m rebuild and the theme flip — never an F9 gesture. **Reported, not fixed** per the brief. Production code is clean (`drawings.js` contains no `setData`/`update`; the primitive redraws through `requestUpdate`), so this is a test-coverage gap, not a behavior defect.

### WARNING

- **W1 — `fib_ext`/`fib_zone` do not skip an off-bar x leg.** `drawing-primitive.js:127` (`ctx.moveTo(p.x1, l.y)`, `lineTo(p.x2, …)`) and `:143` (`ctx.fillRect(p.x1, top, p.x2 - p.x1, …)`) pass possibly-null `x1`/`x2` (from `map.x` in `drawing-tools-core.js:116-119,123-126`) straight to canvas, where `null` coerces to `0`. R6 requires "skip that leg rather than throw"; it does not throw, but it draws a spurious 0-pixel-anchored leg. Every other F9 kind guards its nullable coordinate (`ray` a/b, `vline` x, `channel` segments, `callout` a/b, `price` y, fib level `y`). No covering test exercises an off-bar x for these two kinds (scenario #21 is therefore PARTIAL).
- **W2 — `diff-cover` gate could not be executed.** The tool is not installed in the venv (`command not found: diff-cover`); the proxy measurement is `quotes.py` 100% line coverage and the migration test, but the TDD task's literal gate (`V.2`, `diff-cover` vs `origin/develop` → 100% patch) is unverified.

### SUGGESTION

- **S1 — `tasks.md` checkboxes are all unticked (47 `- [ ]`, 0 `- [x]`).** Consistent with the apply hard contract forbidding `openspec/**` edits; needs the same archive-reconciliation note the F7 `tasks.md` carries, otherwise the tracker under-reports completion.
- **S2 — `debug` string in `drawing-primitive.js` labels `price` at `x=2` (left edge) with the comment "right-axis tag".** The visible label is present (not color-only, requirement met), but a right-axis tag is drawn on the right. Cosmetic; spec only mandates "a right-axis price label".
- **S3 — `drawing-interaction-core.applyDrag` resolves an F9 handle index through `toolHandles(...)[target]`, where off-bar anchors are omitted from the list.** If the coordinate map shifts between pointerdown and move (a pan mid-drag), the index can resolve to a different anchor than the one grabbed. The existing tests use a static map, so this is latent, not observed.

## Non-blockers / notes

- **E2E class-C flake (#149) confirmed pre-existing.** Three full E2E runs produced one failure each, always a *different*, F9-untouched test (`test_keyboard_delete_removes_selected`, `test_context_menu_duplicate_then_undo_deletes`, `test_drag_put_returns_200_and_persists_across_reload`, `test_undo_announces_and_advertises_shortcut`); each passed in isolation. `git diff` shows none of their bodies changed by F9 (`tests/web/test_market_e2e.py`: +174/−3, all in the new F9 test and the toolbar count 7→15).
- **`smc.js`=300 / `object-tree.js`=299 fragility** stands: they are one edit away from tripping the empty-allowlist guard. Both are byte-untouched here (`git diff --exit-code` clean), so the risk is unchanged by F9, not increased.
- **E2E is dev-only** (`pyproject.toml`: `addopts = "-q -m 'not e2e'"`), so the default suite never sees the flake; CI parity holds.
- **All 8 kinds round-trip** through the single write path (`createDrawing` → `parse_drawing` → primitive), and `createDrawing` is the only POST site in `drawings.js`.
- **`channel`/`fib_ext` 3-point schema** is enforced with exact-key `set(points) != {…}` checks (`quotes.py:470-485`), matching the existing `trendline`/`fib`/`rect` branch.
- **E2E covers a representative subset** (`ray`, `channel`, `price`, `fib_zone`) of the 8 kinds; the remaining 4 (`vline`, `callout`, `fib_ext`, `fib_time`) are covered by node controller tests (`chart-controllers.test.js`, 1/2/3-click + dialog) and the API matrix. This matches the task text ("a representative subset").
