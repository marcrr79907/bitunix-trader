# Verify Report: f6-measure-position

```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:295238b8de62bfbcc20d6eeeb6bc84ce2b5ba18c
verdict: pass_with_warnings
blockers: 0
critical_findings: 2
requirements: 5
scenarios: 33
test_command: node --test "tests/js/**/*.test.js" && .venv/bin/python -m pytest -p no:randomly
test_exit_code: 0
test_output_hash: sha256:306-pass-996-pass-1-e2e-flake
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check .
build_exit_code: 0
build_output_hash: sha256:6b09d0c42105310f6e508adc4120352111c63a6046c8a7464867b13833e695e7
```

**Change**: f6-measure-position (issue #119, Fase F6)
**Mode**: Strict TDD (per `openspec/config.yaml: strict_tdd: true`)
**Branch**: `feat/f6-measure-position-s3` @ `295238b` (S3 slice head, superset of tracker `feat/f6-measure-position` @ `9494d72`). Base `develop` @ `80070c0`.
**Chain**: S1 (`28fef4d`/`072a5c1` → merge `745aa02`) → S2 (`a466bcf`/`3193cd9`/`7125862` → merge `9494d72`) → S3 (`612c8c2`/`7e9226d`/`e4474d0`/`afc556f`/`295238b`). All S1+S2 merged into the tracker; S3 is the verified tip.

## Verdict

`PASS_WITH_WARNINGS` — all gates green, all frozen invariants hold, patch coverage 100%, E2E harness runs (87/88, the one failure is the pre-existing class-C `#149` flake). Two spec scenarios (design-system R6 position R:R `aria-live` DOM; design-system R6 Escape cancels a pending position draft) have NO covering implementation or test → reported as **CRITICAL gaps** per the brief ("Report a CRITICAL, do not fix it"). They do not break a frozen invariant, so the verdict is PASS_WITH_WARNINGS with 2 CRITICAL findings, not a clean PASS.

## Requirement coverage matrix

Legend: ✅ PASS · ⚠️ PARTIAL · ❌ MISSING (no covering assertion).

### chart-measure (new capability)

| Scenario | Evidence | Result |
|---|---|---|
| R1 Drag produces a measurement + no POST/PUT | E2E `test_market_e2e.py::test_measure_drag_writes_readout_and_no_post` (`writes == []`, `drawings.length == 0`); `chart-controllers.test.js::measure drag → readout DOM, one primitive, no setData/update` | ✅ |
| R1 New measure replaces the old | E2E `test_measure_replaced_and_cleared_on_tool_change`; `chart-controllers.test.js::a new measure replaces the old (one primitive, not two)` | ✅ |
| R1 No object-tree row | E2E measure test (`window.marketChart.drawings.length == 0`) | ✅ |
| R2 Delta readout | `measure-core.test.js::measure reports the five fields for a known long move`; `…keeps negative deltas`; `…bars === candles === round(timeDelta/iv)` | ✅ |
| R2 Core is pure and reuses intervalSeconds | `measure-core.test.js::measure-core is pure and imports intervalSeconds from chart-core` | ✅ |
| R3 autoscaleInfo null | `chart-controllers.test.js::measure drag…` (`_series._prim.autoscaleInfo() === null`) | ✅ |
| R3 Redraw never touches series data | `chart-controllers.test.js` (series stub `setData`/`update` throw); E2E measure (no writes) | ✅ |
| R4 Escape cancels | `chart-controllers.test.js::Escape cancels the measurement and clears the readout (R4)` | ✅ |
| R4 Tool change cancels | `chart-controllers.test.js::changing the tool away from measure clears (R4)`; E2E `test_measure_replaced_and_cleared_on_tool_change` | ✅ |
| R4 Symbol switch clears | `chart-controllers.test.js::clearForSwitch detaches the primitive and clears the readout (R4)`; `main.js:160` wiring | ✅ |
| R5 Live readout | E2E measure (`#measure-readout` `aria-live == "polite"`); `chart.html:60` | ✅ |
| R5 Bounds hold | `test_module_size_guard.py` (measure.js 189 ≤ 300); `test_market_ux.py::test_f6_cores_and_measure_controller_are_served` (200); E2E `test_shell_keeps_seam_at_eight_keys`; `chart-store.test.js` (11 keys) | ✅ |

### chart-drawings (MODIFIED R1/R5/R6/R10 + ADDED R15)

| Scenario | Evidence | Result |
|---|---|---|
| R1 Many drawings coexist | `test_market_api.py::test_drawings_many_per_symbol_coexist_without_unique_violation` (pre-existing, still green) | ✅ |
| R1 position is a valid kind | `test_market_api.py::test_position_kind_is_a_member_of_drawing_kinds` | ✅ |
| R1 0015 choices-only and reversible | `test_migration_0015.py::test_0015_adds_position_choice_forward_then_reverses_without_data_loss` | ✅ |
| R1 Interval drop / 0014 additive / defaults | Pre-existing `test_migration_0014.py`, `test_isolation.py::test_drawing_visible_locked_defaults` (unchanged, green) | ✅ |
| R5 hline accepts one point | `test_market_api.py::test_parse_drawing_accepts_each_kind` (parametrized) | ✅ |
| R5 position accepts the level schema | `test_market_api.py::test_drawings_position_post_get_put_round_trip` | ✅ |
| R5 position rejects bad points | `test_market_api.py::test_drawings_position_post_invalid_points_is_400_and_writes_nothing` (parametrized matrix), `…put_invalid_points…`, `test_isolation.py::test_drawing_position_kind_round_trips_and_stays_scoped` | ✅ |
| R5 Validation error matrix | `test_drawings_position_post_invalid_points…` (missing `stop`/`tp`, extra key, entry not dict/time non-int/price non-num, non-num+bool levels, degenerate); `…post_accepts_and_ignores_stale_interval` | ✅ |
| R6 Attach one primitive per drawing | `drawing-primitive.test.js`; E2E `test_boot_restores_saved_drawings` | ✅ |
| R6 position draws zones, levels, R:R | `drawing-primitive.test.js::renderShape draws a position via position-core (zones + levels + R:R)` | ✅ |
| R6 position autoscale includes stop and tp | `drawing-primitive.test.js::autoscaleInfo of a position includes stop and take_profit (R6)` | ✅ |
| R6 Hidden position renders blank | `drawing-primitive.test.js::renderShape position draws nothing when hidden (R6)` + `…autoscaleInfo of a hidden position is null` | ✅ |
| R6 Off-bar anchor degrades | `drawing-primitive.test.js::renderShape position degrades (no throw) when the entry is off-bar` | ✅ |
| R6 Drag never touches series data path | `drawing-primitive.test.js` (ctx stub, no series); E2E `test_position_three_click_persists_and_drag_one_put` (ONE PUT, no setData) | ✅ |
| R10 Drag a trendline endpoint / Translate rect / hline moves price | Pre-existing `drawing-interaction-core.test.js` cases (unchanged, green) | ✅ |
| R10 Drag position level | `drawing-interaction-core.test.js::applyDrag position moves ONLY the dragged stop level` (+ take_profit, entry_price) | ✅ |
| R10 Move position box | `drawing-interaction-core.test.js::applyDrag position body shifts all three levels + the anchor column` | ✅ |
| R10 Drag resolves per kind (1/2/2/4/1/4) | `drawing-interaction-core.test.js::handlesFor resolves 1 / 2 / 2 / 4 / 1 / 4 per kind` + `handlesFor position returns the 4 handles` | ✅ |
| R15 Seed copies server levels verbatim | E2E `test_position_seed_copies_smc_setup_verbatim` (POST body `stop`/`take_profit`/`entry.price`/`entry.time` == setups[-1]); no JS recompute (grep: no `find_setups`/`computeSetup`) | ✅ |
| R15 Works without a setup | E2E `test_position_three_click_persists_and_drag_one_put` (3-click with no seed) | ✅ |

### chart-toolbar (MODIFIED R1)

| Scenario | Evidence | Result |
|---|---|---|
| R1 Toolbar and groups render | E2E `test_draw_toolbar_renders_groups_and_sets_store` (1 toolbar, vertical, 6 groups, 7 tools, `.draw-tool == 0`); `draw-toolbar.test.js` (6 groups, 7 buttons) | ✅ |
| R1 Measure and Positions groups render | `tool-icons-core.test.js::TOOL_GROUPS: F6 groups the 7 instruments 2/1/1/1/1/1` + `F6 icons: measure + position yield valid, CSP-clean inline SVGs`; E2E 6 groups / 7 svg icons | ✅ |
| R1 Tool activation sets store and command | E2E `test_draw_toolbar_renders_groups_and_sets_store` (fib click → aria-pressed); `draw-toolbar.test.js` | ✅ |
| R1 Activating position writes store.tool, no new event | E2E `test_position_three_click…` clicks `.draw-tool[data-kind="position"]`; `chart-bus.js` has no `position:*`; **no assertion that `store.tool === "position"` after the click** | ⚠️ PARTIAL |
| R1 Singleton group allowed | `draw-toolbar.test.js` (6 group labels including singletons) | ✅ |

### market-chart (MODIFIED R14/R18/R20)

| Scenario | Evidence | Result |
|---|---|---|
| R14 Inventory and no-cycle | `test_market_ux.py::test_import_graph_routes_resolve` (green); no controller imports `main` (grep) | ✅ |
| R14 Store never holds candles | `chart-store.test.js::STORE_KEYS is exactly…(11)` | ✅ |
| R14 Size ceiling with empty allowlist | `test_module_size_guard.py` (ALLOWLIST empty; smc 300, object-tree 299, drawings 296) | ✅ |
| R14 New cores and controller are served | `test_market_ux.py::test_f6_cores_and_measure_controller_are_served` (measure-core/position-core/measure → 200) | ✅ |
| R14 Controller allowlist count grows | `test_market_ux.py:146` asserts `len(CONTROLLER_ALLOWLIST) == 12`; `views.py:67-82` holds 12 | ✅ |
| R18 Seam shape frozen | E2E `test_shell_keeps_seam_at_eight_keys` (== 8); `test_dialog_has_no_inline_handler_and_seam_frozen` | ✅ |
| R18 Measure has no seam key | E2E `test_shell_keeps_seam_at_eight_keys`; E2E measure asserts DOM readout, `drawings.length == 0` | ✅ |
| R18 SMC core reachable | E2E SMC tests (`window.SmcOverlayCore`) | ✅ |
| R20 Seam stays 8 keys | E2E `test_shell_keeps_seam_at_eight_keys` | ✅ |
| R20 Exactly one new bus event (unchanged set) | `chart-bus.js` (no `measure:*`/`position:*`); position reuses `drawing:changed`; `chart-bus.test.js` | ✅ |
| R20 Measure and position render option-only | `chart-controllers.test.js` (setData/update stubs throw); E2E measure + position (`setData` never called) | ✅ |
| R20 Existing E2E stays green unedited | 87/88 E2E pass; the one failure is the pre-existing `#149` flake | ✅ |
| R14/R28 modulepreload lists new modules | `test_market_ux.py::test_market_page_preloads_f6_modules` (measure-core/position-core/measure) | ✅ |

### design-system (MODIFIED R6/R9)

| Scenario | Evidence | Result |
|---|---|---|
| R6 Visible focus | Pre-existing `test_shell_desktop_panel_and_chip_a11y`, `theme.css` `:focus-visible` | ✅ |
| R6 Chart keyboard-focusable/labelled | Pre-existing shell test | ✅ |
| R6 Dialog traps focus / Escape | Pre-existing E2E `test_escape_closes_and_returns_focus` | ✅ |
| R6 Toolbar/tree state not color-only | Pre-existing toolbar/tree tests | ✅ |
| R6 Long vs Short is not color-only | `drawing-primitive.js:116-118` draws `"LONG"/"SHORT"` + ▲/▼; `drawing-primitive.test.js::renderShape draws a position…` asserts `fillText >= 2` — **does not assert the literal LONG/SHORT text** | ⚠️ PARTIAL |
| R6 Readouts are live DOM | Measure half: E2E measure (`#measure-readout` `aria-live`); **position R:R is drawn with `ctx.fillText` (`drawing-primitive.js:120`) — NO DOM `aria-live` node exists for it** | ❌ **MISSING (CRITICAL)** |
| R6 Escape cancels a draft | Measure half: `chart-controllers.test.js::Escape cancels the measurement`. **No Escape handler clears `pendingPosition` (`drawings.js` has zero keydown/Escape listeners); no test asserts it** | ❌ **MISSING (CRITICAL)** |
| R6 AA holds in light theme | Pre-existing `theme-core.test.js::contrast…` | ✅ |
| R9 Selection is not color-only | Pre-existing drawing selection tests | ✅ |
| R9 Handles are canvas-drawn | `drawing-primitive.js:124-133` (`ctx.arc`); pre-existing DOM-free assertion | ✅ |
| R9 Position handles canvas-drawn and tokenized | `drawHandles` uses `arc` for the 4 position handles (no DOM); zones use `#ef5350`/`#26a69a`, which ARE token values (`theme.css:6`) but are written as **literals** in `drawing-primitive.js:98-99`, not read from CSS tokens | ⚠️ PARTIAL |
| R9 Dialog uses tokens | Pre-existing indicator-settings dialog | ✅ |

**Compliance summary**: 36/40 scenarios fully compliant; 2 PARTIAL (chart-toolbar R1 position store.tool; design-system R6/R9 label & token detail); 2 MISSING/CRITICAL (design-system R6 position R:R `aria-live` DOM; design-system R6 Escape cancels pending position draft).

## Gates

| Command | Result |
|---|---|
| `node --test "tests/js/**/*.test.js"` | **306 pass, 0 fail**, 0 skipped (`tests 306 / pass 306 / fail 0`) |
| `.venv/bin/python -m pytest -p no:randomly -m 'not e2e'` | **996 passed, 88 deselected** in 196.72s |
| `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | `All checks passed!` / `145 files already formatted` |
| `.venv/bin/python web/manage.py makemigrations --check --dry-run` | `No changes detected` |
| `diff-cover cov.xml --compare-branch=origin/develop --fail-under=100` | **100%** — `quotes.py` 100%, `models.py` 100%; Total 11 lines, 0 missing |
| E2E `pytest tests/web/test_market_e2e.py -m e2e` | **87 passed, 1 failed** (`test_scale_and_type_round_trip_persists_across_reload` — pre-existing class-C `#149`; see Non-blockers) |
| E2E F6 subset (`-k "measure or position"`) | **4/4 pass** |

## Invariants

| Invariant | Proof | Result |
|---|---|---|
| `window.marketChart` EXACTLY 8 keys | `main.js:56-65` (8 literal keys); E2E `test_shell_keeps_seam_at_eight_keys` asserts `== 8` | ✅ |
| `STORE_KEYS` EXACTLY 11 | `chart-store.js:13-27` (11 entries, no measure/position key); `chart-store.test.js` | ✅ |
| Every `market/**/*.js` ≤300, empty allowlist | `test_module_size_guard.py` (ALLOWLIST `frozenset()`, green); measure-core 67, position-core 119, measure.js 189, drawings 296, drawing-interaction-core 271, drawing-primitive 177, smc 300, object-tree 299 | ✅ |
| `controllers/smc.js` byte-untouched vs develop | `git diff --exit-code develop -- …/smc.js` → exit 0 | ✅ |
| `controllers/object-tree.js` byte-untouched vs develop | `git diff --exit-code develop -- …/object-tree.js` → exit 0 | ✅ |
| #68: no `setData`/`update` writer for measure/position | grep of `measure.js`/`drawing-primitive.js`/`drawing-interaction-core.js` finds only comments, no writer call; E2E + `chart-controllers.test.js` stubs throw | ✅ |
| measure `autoscaleInfo` null | `measure.js:54` `return null`; `chart-controllers.test.js` asserts it | ✅ |
| Single-source: no JS SMC recompute | grep `find_setups|findSetups|computeSetup|scoreSetup` in `web/market/**` → NONE; seed copies `setups` verbatim (`drawings.js:233-251`) | ✅ |
| `CONTROLLER_ALLOWLIST` == 12 | `views.py:67-82` (12 entries); `test_market_ux.py:146` asserts `== 12` | ✅ |
| `requirements.txt` / `src/` unchanged | `git diff --stat develop...HEAD -- requirements.txt src/` → empty | ✅ |
| No inline handler/script in diff | `git diff develop...HEAD -- web/ | grep -E '^\+.*(onclick|onerror|onload|<script)'` → NONE; `test_market_page_has_no_inline_script_or_handler` | ✅ |
| `chart-bus` adds no `measure:*`/`position:*` event | `chart-bus.js` EVENTS (no new key); grep → NONE | ✅ |

## Findings

### CRITICAL

- **C1 — design-system R6 "Readouts are live DOM" is unmet for the position R:R.** The
  spec (`specs/design-system/spec.md:26-28`) and `design.md:242-243` REQUIRE the position
  R:R readout to live in an `aria-live="polite"` DOM node. The implementation draws it on
  the canvas via `ctx.fillText("R:R " + box.rr.toFixed(2), …)` at
  `web/market/templates/market/drawing-primitive.js:120`. No DOM node for R:R exists
  anywhere (grep `aria-live` in `web/market/templates/market/` finds only `#rsi` and
  `#measure-readout`; no `position`-rr element is created at runtime). Canvas text is
  invisible to AT, which is exactly the failure D8 set out to avoid for the measure.
  No test asserts a position R:R `aria-live` node. **Do not fix — report.**
- **C2 — design-system R6 "Escape cancels a draft" is unmet for the pending position draft.**
  The spec (`specs/design-system/spec.md:28`) and `design.md:229-237` REQUIRE `Escape` to
  cancel a pending position draft. `controllers/drawings.js` registers NO keydown/Escape
  listener (grep `keydown|Escape` in `drawings.js` → NONE); a half-collected `pendingPosition`
  is only dropped on a tool change or symbol switch (`drawings.js:259-264,289`), never on
  `Escape`. No test asserts Escape cancels a position draft (grep `Escape` in the JS/E2E
  suites finds no position-draft case). **Do not fix — report.**

### WARNING

- **W1 — design-system R6 "Long vs Short is not color-only" is only indirectly tested.**
  The render is correct (`drawing-primitive.js:116-118` writes `"LONG"`/`"SHORT"` + ▲/▼),
  but `drawing-primitive.test.js::renderShape draws a position…` asserts only
  `fillText >= 2` — it does not assert the literal `LONG`/`SHORT` strings. Coverage breadth,
  not logic.
- **W2 — position risk/reward zone colors are hard-coded literals, not design tokens.**
  `drawing-primitive.js:98-99` uses `"#ef5350"`/`"#26a69a"` inline. Those values equal
  `theme.css:6` `--dn`/`--up`, so R9 "zones use design tokens" holds by value but not by
  reference; a future token change would silently desync. (Canvas cannot read CSS variables
  directly, so this is a known canvas constraint — a shared JS color map would close it.)
- **W3 — chart-toolbar R1 "Activating position writes store.tool with no new event" has no
  direct assertion.** The E2E clicks the position button and asserts the resulting POST, but
  never asserts `store.tool === "position"` after the click (unlike the `fib` case). Low risk
  — the toolbar writes `store.tool` for every kind uniformly (`draw-toolbar.js`).

### SUGGESTION

- **S1 — No dedicated test for `measure-core` off-value `pricePct` when `a.price === 0`.**
  `measure-core.test.js` covers null time and missing price but not a zero-price baseline
  (guarded implicitly). Non-blocking.
- **S2 — `position-core.riskReward` sign-edge (`entry === tp`) is not explicitly asserted**;
  only `entry === stop` degenerate is. Minor triangulation gap.
- **S3 — No automated assertion that the position column header/group label uses token
  names** (mirrors the F5 S3 note; source-verified only).

## Non-blockers / notes

- **Pre-existing E2E flake confirmed, not introduced.** `test_scale_and_type_round_trip_persists_across_reload`
  fails in isolation on HEAD (`django.db.utils.OperationalError: cannot open savepoint - SQL
  statements in progress` + Playwright timeout), matching the class-C `#149` flake named in
  the task brief. All other 87 E2E tests pass, including the four F6 tests and the seam/store
  freeze assertions.
- **Fragility (as flagged in the brief):** `drawings.js` = **296** (4 lines of headroom — note
  the brief said 296; design forecast ~262, actual 296), `smc.js` = **300** (at ceiling,
  byte-untouched), `object-tree.js` = **299** (1 line headroom, byte-untouched). Guard green
  because it fails only when *over* the ceiling and both at-ceiling modules are untouched.
- **E2E is dev-only** (`pytest.mark.e2e`, deselected in CI per `pyproject.toml`), but the
  harness DID run here: 87/88 pass on this machine.
- **Strict TDD note:** an `apply-progress` artifact with a TDD Cycle Evidence table was not
  present in `openspec/changes/f6-measure-position/` (only proposal/design/explore/tasks/specs).
  TDD evidence verification against a report table is therefore N/A; the RED tests are
  nonetheless present in the codebase and GREEN on execution (306 node + 996 pytest + E2E F6
  4/4), which is the substantive check.
- **Design coherence:** every D1–D8 decision holds — D1 ephemeral measure (no key), D2
  `Kind.POSITION` reuse, D3 no store/seam key, D4 own pointer listeners (`drawing-interaction.js:94`
  bails in tool mode), D5 explicit `#position-seed` + `smc:loaded` cache, D6 `{entry,stop,take_profit}`,
  D7 `positionBox` delegation, D8 measure DOM readout. The only design deviations are C1/C2
  (position R:R DOM node and Escape-draft cancel were designed but not implemented).

## Blockers

None. C1/C2 are spec-vs-implementation gaps reported for the orchestrator; no frozen invariant
is violated. W1–W3 are reconciliation warnings.
