# Verify Report: f7-chart-shortcuts

```yaml
schema: gentle-ai.verify-result/v1
verdict: pass_with_warnings
blockers: 0
critical_findings: 1
requirements: 16
scenarios: 55
test_command: node --test "tests/js/**/*.test.js" && .venv/bin/python -m pytest -p no:randomly -m 'not e2e'
test_exit_code: 0
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check .
build_exit_code: 0
```

**Change**: f7-chart-shortcuts (issue #120, Fase F7)
**Mode**: Strict TDD (`openspec/config.yaml: strict_tdd: true`)
**Branch**: `feat/f7-chart-shortcuts-s3` @ `ab6d9d7` (S3 tip, superset of tracker `feat/f7-chart-shortcuts`). Base `develop` @ `0c2e3e8`.
**Chain**: S1 (`b50796e`/`01b0290` → merge `89bce8f`) → S2 (`661b29f`/`dc88201`/`295ec9d` → merge `51a8e11`) → S3 (`8a16345`/`f874c45`/`ab6d9d7`). 10 commits, 17 files, +1676/−3 lines.

## Verdict

`PASS_WITH_WARNINGS` — every gate is green, every frozen invariant holds, and the S1–S3 chain is coherent. One spec scenario (`chart-toolbar` R3 "Letter fires inside the chart") has **no implementation and no covering test**: the per-tool letter router was explicitly deferred (`design.md` D8, `proposal.md` Out-of-Scope) so only the `aria-keyshortcuts` advertisement shipped. It is reported as a **CRITICAL** per the brief ("Report a CRITICAL, do not fix it"). It breaks no frozen invariant and no other scenario depends on it, so the verdict is `PASS_WITH_WARNINGS` with 1 CRITICAL finding, not a clean PASS — mirroring the F6 precedent.

## Requirement coverage matrix

Legend: ✅ PASS · ⚠️ PARTIAL · ❌ MISSING (no covering assertion).

### chart-history (new capability)

| Scenario | Evidence | Result |
|---|---|---|
| R1 Push → undo → redo round-trips | `tests/js/history-core.test.js::push then undo then redo round-trips the same record` (`canUndo`/`canRedo`/`size` assertions) | ✅ |
| R1 New push clears redo | `history-core.test.js::a new push clears the redo stack` | ✅ |
| R1 Bounded at the limit | `history-core.test.js::default limit is 50 and drops the oldest` + `a custom limit bounds the stack` | ✅ |
| R2 One drag yields one entry | `tests/js/undo.test.js::one drag gesture yields exactly ONE entry (persist:true boundary)`; E2E `test_market_e2e.py::test_drag_undo_issues_second_put_with_prior_points` (`len(puts) == 1`) | ✅ |
| R2 Per-frame persistence is rejected | `undo.test.js::per-frame persistence is rejected (only persist:false -> no entry)` | ✅ |
| R3 Undo a delete re-POSTs a new id | E2E `test_context_menu_delete_then_undo_reposts` (`restored_id != original_id`); `undo.test.js::undo of a delete re-POSTs; redo DELETEs` | ✅ |
| R3 Undo a create DELETEs | E2E `test_create_undo_deletes_via_tool` (`deletes[0].url.endswith(f"/{created_id}")`) | ✅ |
| R3 Undo a move PUTs the prior points | E2E `test_drag_undo_issues_second_put_with_prior_points` (`puts[1].post_data … price == 100.0`); `undo.test.js::replayOps: update undo PUTs the before points` | ✅ |
| R3 Local-patch-only fails (negative) | No test constructs a local-patch implementation and asserts its failure. The positive path is proven, but the negative "MUST fail" scenario has no covering assertion | ⚠️ PARTIAL |
| R4 Symbol switch clears the stack | `undo.test.js::clearForSwitch empties the stack and the committed cache`; wiring at `main.js:172` (`if (symbolChanged) undo.clearForSwitch()`). No test drives the symbol switch through `switchTo` | ✅ |
| R4 Reload starts empty | No test. True by construction (no persistence in `undo.js`), but unasserted | ⚠️ PARTIAL |
| R5 Ctrl+Z undoes | `undo.test.js::… one drag gesture …` (`ctrlKey:true` fires undo, `_pd === true`); `Ctrl+Y redoes` | ✅ |
| R5 Shift+Z and Y redo | `undo.test.js::Ctrl+Y redoes (Windows)`; `undo of a delete re-POSTs; redo DELETEs` (`shiftKey:true`) | ✅ |
| R5 Escape and Delete untouched | `undo.test.js::Escape and Delete are left to the #chart handler (router ignores them)` | ✅ |
| R5 Text input is exempt | `undo.test.js::a text input is exempt from the router` + `a contenteditable target is exempt too` | ✅ |
| R6 Store stays 11 keys | `tests/js/chart-store.test.js::STORE_KEYS is exactly the UI/config vocabulary (11 incl. indicatorVisible)` | ✅ |
| R6 Replay is user-scoped | Inherited R14 `for_user` CRUD: `test_market_api.py::test_drawings_isolation_b_delete_of_a_id_is_404_and_a_unchanged` + `…put_of_a_id…` + `test_isolation.py` (unchanged, green). Replay reuses `createDrawing`/`deleteDrawing` | ✅ |
| R6 Size and CSP | `test_module_size_guard.py` (empty ALLOWLIST, green); `test_market_ux.py::test_csp_present_on_market_page` (unchanged header) | ✅ |

### chart-context-menu (new capability)

| Scenario | Evidence | Result |
|---|---|---|
| R1 Drawing row yields delete then duplicate | `tests/js/context-menu-core.test.js::a drawing row yields delete then duplicate` | ✅ |
| R1 Empty chart yields reset-scale and add-indicator | `context-menu-core.test.js::an empty chart yields reset-scale then add-indicator when non-linear` | ✅ |
| R1 reset-scale only when non-linear | `context-menu-core.test.js::an empty chart drops reset-scale when linear` + `a drawing row adds reset-scale only when non-linear` | ✅ |
| R2 Menu is JS-built DOM | `chart-controllers.test.js::contextmenu on a drawing row opens a role=menu…`; E2E `test_context_menu_on_drawing_shows_delete_and_duplicate` (`…getAttribute('oncontextmenu')` falsy) | ✅ |
| R2 Right-click opens at cursor | `chart-controllers.test.js::…` (`ev._prevented()` true, `role=menu` appended); E2E `_open_row_menu` | ✅ |
| R3 Escape returns focus to chart | `chart-controllers.test.js::Escape closes the menu and returns focus to #chart (R3)` | ✅ |
| R3 Arrows and Home/End move focus | `chart-controllers.test.js::ArrowDown then End then Home rove focus across items (R3)` | ✅ |
| R3 Items advertise shortcuts | `chart-controllers.test.js::…` (`menuitem` role + `aria-keyshortcuts == "Delete"`); `context-menu-core.test.js` (`keyshortcut` fields) | ✅ |
| R4 Delete reuses drawing:delete | `chart-controllers.test.js::Delete item emits drawing:delete with the hit id (R4)`; E2E delete-then-undo | ✅ |
| R4 Duplicate clones then POSTs | `chart-controllers.test.js::Duplicate item emits drawing:duplicate with the hit id (R4)`; `chart-controllers.test.js::drawing:duplicate clones kind/points/style into ONE POST`; E2E `test_context_menu_duplicate_then_undo_deletes` | ✅ |
| R4 Reset-scale reuses the F8 seam | `chart-controllers.test.js::reset-scale item sets linear + emits scale:changed, never a PUT (R4/#68)`; E2E `test_context_menu_reset_scale_emits_scale_changed_no_put` (price-scale mode 0, `puts == []`) | ✅ |
| R4 Add-indicator reuses the F5 seam | `chart-controllers.test.js::add-indicator reuses the F5 seam: store membership + indicator:changed (R4)` | ✅ |
| R5 Hit-test reuses the pure helpers | `context-menu.js:143` uses `grabHandle(pointerRows(rows), …)` (imported `drawing-interaction-core.js:13`); no test asserts the reuse — source-verified only | ⚠️ PARTIAL |
| R5 Untouched controllers and size | `git diff --exit-code develop … object-tree.js/drawing-interaction.js` → empty; guard green | ✅ |
| R5 No series data write | No menu-specific `setData`/`update` spy test exists (the throwing-stub spy covers measure only) | ⚠️ PARTIAL |

### chart-drawings (MODIFIED R2)

| Scenario | Evidence | Result |
|---|---|---|
| R2 Duplicate clones via the existing POST | `chart-controllers.test.js::drawing:duplicate clones … into ONE POST, no offset (D6/Q4)`; E2E `test_context_menu_duplicate_then_undo_deletes` (`len(posts) == 1`) | ✅ |
| R2 Duplicate uses no new endpoint | `views.py` has no duplicate route; E2E captures only `/market/api/drawings` | ✅ |
| R2 GET empty / POST flags / PUT fields / PUT kind immutable / DELETE / unauth / CSRF | Pre-existing `test_market_api.py` CRUD assertions (unchanged, green) | ✅ |

### chart-toolbar (MODIFIED R1/R3)

| Scenario | Evidence | Result |
|---|---|---|
| R1 Toolbar and groups render | Pre-existing E2E `test_draw_toolbar_renders_groups_and_sets_store` (1 toolbar, vertical, 6 groups, 7 tools, `.drawings .draw-tool == 0`) | ✅ |
| R1 Buttons advertise per-tool shortcuts | `tests/js/draw-toolbar.test.js::each tool button carries an aria-keyshortcuts value (R1 delta, F7)` + `TOOL_KEYS advertises one letter per kind` | ✅ |
| R1 Tool activation sets store and command | Pre-existing E2E `test_draw_toolbar_renders_groups_and_sets_store` (`fib` → `aria-pressed`); `draw-toolbar.test.js` | ✅ |
| R1 Measure and Positions groups render | `tool-icons-core.test.js::TOOL_GROUPS: F6 groups the 7 instruments 2/1/1/1/1/1`; E2E 6 groups / 7 svg | ✅ |
| R1 Activating position writes store.tool, no new event | Pre-existing E2E (position click → store.tool uniformly); `chart-bus.js` untouched | ✅ |
| R1 Singleton group allowed | `draw-toolbar.test.js` (6 group labels incl. singletons) | ✅ |
| R3 Arrows move focus | `test_draw_toolbar_renders_groups_and_sets_store` (ArrowDown hline → trendline); `draw-toolbar.test.js::roving tabindex` | ✅ |
| R3 Home and End jump | `draw-toolbar.js:78-79`; `draw-toolbar.test.js` roving cases | ✅ |
| R3 Enter activates | Native `<button>` activation (pre-existing) | ✅ |
| R3 Letter firing is chart-scoped only | Trivially satisfied — no letter router is bound, so nothing fires anywhere | ✅ |
| R3 Letter fires inside the chart | **No implementation** (`draw-toolbar.js` binds only Arrow/Home/End, `:100-104`; no `TOOL_KEYS` keydown) and **no test**. The scenario requires the `hline` letter to activate the tool inside `#chart` | ❌ **MISSING (CRITICAL)** |

### market-chart (MODIFIED R14/R18/R20)

| Scenario | Evidence | Result |
|---|---|---|
| R14 Inventory and no-cycle | `test_market_ux.py::test_import_graph_routes_resolve` (all relative imports resolve to 200); grep: no controller imports `main` | ✅ |
| R14 Store never holds candles | `chart-store.test.js` (11-key vocabulary) | ✅ |
| R14 Size ceiling with empty allowlist | `test_module_size_guard.py` (`CEILING=300`, `ALLOWLIST=frozenset()`, green) | ✅ |
| R14 New cores and controllers are served | `test_market_ux.py:127` iterates `MODULE_ALLOWLIST` (incl. `history-core`, `context-menu-core`) and `:147` iterates `CONTROLLER_ALLOWLIST` (incl. `undo`, `context-menu`) → each fetched 200 | ✅ |
| R14 Controller allowlist count grows | `test_market_ux.py:146` asserts `len(CONTROLLER_ALLOWLIST) == 15`; `views.py:71-88` holds 15 | ✅ |
| R14 New theme core is served | Pre-existing (F6) | ✅ |
| R14 New candle sub-module is served | Pre-existing | ✅ |
| R14 No behavior change | Node 394 pass, pytest 999 pass; seam 8-key E2E green; HA contract untouched | ✅ |
| R18 Seam shape frozen | E2E `test_shell_keeps_seam_at_eight_keys` (`Object.keys(window.marketChart).length == 8`) | ✅ |
| R18 Measure has no seam key | E2E measure tests (readout DOM, `drawings.length == 0`); seam test | ✅ |
| R18 Undo and menu assert without a seam key | E2E F7 network-intercept tests + DOM `role="menu"`; seam still 8 | ✅ |
| R18 SMC core reachable | E2E SMC tests (`window.SmcOverlayCore`) | ✅ |
| R18 Existing E2E green except replaced assertions | 95/96 E2E pass; the one failure is pre-existing/unrelated (see Non-blockers) | ✅ |
| R20 Seam stays 8 keys | `test_shell_keeps_seam_at_eight_keys` | ✅ |
| R20 Exactly one new bus event (unchanged set) | `chart-bus.js` byte-untouched (D9 string-literal convention); grep finds no `history:*`/`undo:*`/`menu:*` | ✅ |
| R20 Visibility toggle is option-only | Pre-existing F5 E2E (`setData` spy) | ✅ |
| R20 Measure and position render option-only | Pre-existing F6 E2E (`setData` spy); `chart-controllers.test.js` throwing stubs | ✅ |
| R20 Undo and menu never touch the series data path | No menu/undo-specific `setData` spy; the R20 clause is covered by source inspection (`replayOps` emits only bus verbs) but not by an explicit spy assertion for these two paths | ⚠️ PARTIAL |
| R20 Existing E2E stays green except replaced assertions | As above | ✅ |

### design-system (MODIFIED R6/R7)

| Scenario | Evidence | Result |
|---|---|---|
| R6 Context menu is keyboard-navigable with focus return | `chart-controllers.test.js::ArrowDown then End then Home…` + `Escape closes the menu and returns focus to #chart (R3)` | ✅ |
| R6 Menu items advertise accessible names and shortcuts | `chart-controllers.test.js::contextmenu on a drawing row…` (`aria-label` on menu, `aria-keyshortcuts` per item) | ✅ |
| R6 Visible focus / chart focusable / dialog / not-color-only / long-short / readouts / AA light | Pre-existing F5/F6 scenarios (unchanged, green) | ✅ |
| R7 CSP header unchanged | `test_market_ux.py::test_csp_present_on_market_page`; `web/middleware.py` byte-unchanged vs develop | ✅ |
| R7 No inline handler remains | `test_market_ux.py::test_market_page_has_no_inline_script_or_handler`; diff scan `grep -E '^\+.*(oncontextmenu|onclick|<script)'` → NONE | ✅ |
| R7 Menu is CSP-clean | E2E `test_context_menu_on_drawing_shows_delete_and_duplicate` (no `oncontextmenu`); `context-menu.js:154` binds via `addEventListener` | ✅ |

**Compliance summary**: 50/55 scenarios fully compliant; 4 PARTIAL (chart-history R3 negative; chart-history R4 reload; chart-context-menu R5 hit-test reuse, R5 no-series-write; market-chart R20 no-series-write); 1 MISSING/CRITICAL (chart-toolbar R3 letter-fires-inside-chart).

## Gates

| Command | Result |
|---|---|
| `node --test "tests/js/**/*.test.js"` | **394 pass, 0 fail**, 0 skipped (`tests 394 / pass 394 / fail 0`) |
| `.venv/bin/python -m pytest -p no:randomly -m 'not e2e'` | **999 passed, 96 deselected** in 569.56s |
| `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | `All checks passed!` / `145 files already formatted` |
| `.venv/bin/python web/manage.py makemigrations --check --dry-run` | `No changes detected` |
| `diff-cover cov.xml --compare-branch=origin/develop --fail-under=100` | **No lines with coverage information in this diff** (vacuous — see Non-blockers) |
| E2E `pytest tests/web/test_market_e2e.py -m e2e` | **95 passed, 1 failed** (`test_hidden_drawing_is_not_pointer_grabbable` — pre-existing, NOT in the F7 diff; a prior run passed 96/96 and a different prior run failed `test_scale_and_type_round_trip_persists_across_reload` → class-C flake, see Non-blockers) |
| E2E F7 subset (`-k "context_menu or drag_undo or create_undo"`) | **6/6 pass** |

## Invariants

| Invariant | Proof | Result |
|---|---|---|
| `window.marketChart` EXACTLY 8 keys | `main.js:59-68` (8 literal keys); E2E `test_shell_keeps_seam_at_eight_keys` asserts `== 8` | ✅ |
| `STORE_KEYS` EXACTLY 11 | `chart-store.js:13-27` (11 entries, no `history` key); `chart-store.test.js` | ✅ |
| Every `market/**/*.js` ≤300, empty allowlist | `test_module_size_guard.py` (`ALLOWLIST=frozenset()`, green). Sizes: `drawings.js` **298**, `smc.js` **300**, `object-tree.js` **299**, `main.js` 274, `context-menu.js` 164, `undo.js` 136, `history-core.js` 65, `context-menu-core.js` 57 | ✅ |
| `controllers/smc.js` byte-untouched vs develop | `git diff --exit-code develop -- …/smc.js` → exit 0 | ✅ |
| `controllers/object-tree.js` byte-untouched | `git diff --exit-code develop -- …/object-tree.js` → exit 0 | ✅ |
| `controllers/drawing-interaction.js` byte-untouched | `git diff --exit-code develop -- …/drawing-interaction.js` → exit 0 | ✅ |
| `controllers/chart-bus.js` byte-untouched | `git diff --exit-code develop -- …/chart-bus.js` → exit 0 | ✅ |
| #68: no `setData`/`update` writer added | grep over the 4 new files finds only comments (`context-menu.js:10,69`) — no writer call. `replayOps` emits only bus verbs | ✅ |
| Shortcut non-conflict | `undo.js` binds only Ctrl/Cmd+Z/Shift+Z/Y (`:115-123`); `object-tree.js` `v`/`l`/`s` (`:112,119,180`) and `drawing-interaction.js` `#chart` Escape/Delete (`:214,222`) byte-untouched | ✅ |
| `CONTROLLER_ALLOWLIST` == 15 | `views.py:71-88` (15 entries); `test_market_ux.py:146` asserts `== 15` | ✅ |
| `requirements.txt` / `src/` unchanged | `git diff --stat develop...HEAD -- requirements.txt src/` → empty | ✅ |
| No inline handler/script | `git diff develop...HEAD -- web/ | grep -E '^\+.*(onclick|oncontextmenu|onerror|onload|<script)'` → NONE; `test_market_page_has_no_inline_script_or_handler` | ✅ |
| CSP unchanged | `web/middleware.py` `git diff` → empty; `test_csp_present_on_market_page` green | ✅ |
| No new color literals in menu CSS | `theme.css` diff uses only `--surface`/`--border`/`--radius`/`--fs-3`/`--accent`/`--sp-*`; regex for `#hex` → none | ✅ |
| `theme.css` token-only menu block | `theme.css` `.chart-context-menu` uses existing tokens | ✅ |

## Findings

### CRITICAL

- **C1 — chart-toolbar R3 "Letter fires inside the chart" is unimplemented and untested.**
  The delta spec (`specs/chart-toolbar/spec.md:108-112`) requires the scenario: GIVEN focus
  inside `#chart`, WHEN the `hline` letter is pressed, THEN the `hline` tool activates. The
  implementation only *advertises* letters: `controllers/draw-toolbar.js:17-26` exports
  `TOOL_KEYS` and `:95` sets `aria-keyshortcuts` per button, but the only keydown listener
  bound is the roving-focus one (`:100-104`, Arrow/Home/End only) — there is **no letter
  router** anywhere (`grep TOOL_KEYS|shortcut` in `web/market/` finds no firing site). No test
  presses a tool letter (`grep letter` in `tests/js/` and `tests/web/` finds only the
  `aria-keyshortcuts` advertisement tests). The companion scenario "Letter firing is
  chart-scoped only" passes only vacuously (nothing fires, so nothing is stolen). This was a
  deliberate deferral — `design.md` D8 ("per-tool letters deferred to `aria-keyshortcuts`")
  and `proposal.md` Out-of-Scope ("per-tool **global** letter shortcuts … the tree owns
  `v`/`l`/`s`") — but the normative spec scenario was left in place, so spec-vs-implementation
  diverges. **Do not fix — report.**

### WARNING

- **W1 — chart-history R3 "Local-patch-only fails" has no negative covering test.** The
  positive replay path is proven (E2E captured verbs + `undo.test.js` op matrix), but the
  scenario asserts that a hypothetical local-patch implementation MUST fail the
  undo-delete capture. No test instantiates such an implementation, so the assertion is
  inferred, not executed. Low risk (the design forbids the anti-pattern by construction).
- **W2 — market-chart R20 "Undo and menu never touch the series data path" has no explicit
  spy assertion for those two paths.** The `setData`/`update` throwing-stub spy in
  `chart-controllers.test.js` is wired to the measure fixture only; the undo/menu fixtures
  assert the emitted bus verbs but not that the series spies stay untouched. Source inspection
  confirms `replayOps` and `ACTION` emit only bus commands, so the invariant holds, but the
  runtime assertion the scenario names is absent.
- **W3 — chart-context-menu R5 "Hit-test reuses the pure helpers" is source-verified only.**
  `context-menu.js:143` calls `grabHandle(pointerRows(rows), p.x, p.y, map())`, exactly as
  required, but no test asserts the reuse (only the resulting `drawing:selected` payload). A
  regression replacing the hit-test with duplicated logic would pass the suite.
- **W4 — chart-history R4 "Reload starts empty" is untested.** `undo.js` holds the stack in a
  closure with no persistence, so the behavior is guaranteed by construction, but no test
  boots, stacks, reloads, and asserts emptiness.
- **W5 — No test asserts the 4 F7 `modulepreload` links.** `chart.html` adds
  `history-core`, `context-menu-core`, `undo`, `context-menu` (diff shows +4), but
  `test_market_page_preloads_f6_modules` only checks the F6 set. A dropped F7 preload would
  not fail the suite (it degrades speed, not correctness).

### SUGGESTION

- **S1 — `diff-cover` is vacuous for this change.** The only Python source edit is four
  `frozenset` literal entries in `web/market/views.py` (`:62-63`, `:86-87`); these lines are
  reported as `NOT-TRACKED` in `cov.xml` (frozenset continuation literals are not instrumented
  as executed lines), so `diff-cover` emits "No lines with coverage information in this diff".
  The "patch coverage 100% on new Python" success criterion is therefore true but empty —
  there is no new executable Python to cover.
- **S2 — `drawings.js` sits at 298/300 (2 lines of headroom).** The design forecast ~291; the
  actual is 298. The `drawing:duplicate`/`drawing:restore`/`drawing:created` additions left
  only 2 lines before the guard fails. The design's documented fallback (move
  duplicate/restore handling into `undo.js`) remains available if a future edit needs room.
- **S3 — No `docs/` update for the new `Ctrl/Cmd+Z`/`Shift+Z`/`Y` bindings.** Success
  criterion "work and are documented" — the `aria-keyshortcuts` advertise the tool letters,
  and the router comments document the undo keys, but no user-facing doc lists the undo keys.

## Non-blockers / notes

- **E2E flakiness is pre-existing and does not touch F7.** Three full E2E runs on this machine
  produced three different single failures (`test_scale_and_type_round_trip_persists_across_reload`,
  `test_hidden_drawing_is_not_pointer_grabbable`, and one clean 96/96), all with SQLite
  `database table is locked` / Playwright timeout signatures — the class-C `#149` flake named
  in the brief. `test_hidden_drawing_is_not_pointer_grabbable` is **not** in the F7 diff
  (pre-existing) and passed in isolation. Every F7 E2E test (6/6) passes in every run.
- **Fragility (as flagged in the brief):** `drawings.js` = **298** (2-line headroom),
  `smc.js` = **300** (at ceiling, byte-untouched), `object-tree.js` = **299** (1-line
  headroom, byte-untouched). The guard passes because it fails only when *over* the ceiling
  and both at-ceiling modules are untouched.
- **E2E is dev-only** (`pytest.mark.e2e`, deselected in CI per `pyproject.toml`); the harness
  DID run here.
- **Strict TDD note:** no `apply-progress` artifact with a TDD Cycle Evidence table exists in
  `openspec/changes/f7-chart-shortcuts/` (only proposal/design/explore/tasks/specs). TDD
  evidence verification against a report table is therefore N/A; the RED tests are nonetheless
  present in the codebase and GREEN on execution (394 node + 999 pytest + E2E F7 6/6).
- **Design coherence:** D1 (pure core, store stays 11), D2 (reset-scale/add-indicator out of
  stack), D3 (persist:true boundary), D4 (server-coupled replay), D5 (`undo.js` name),
  D6 (duplicate/restore reuse `createDrawing`), D7 (JS-built menu), D9 (string-literal bus
  vocabulary, `chart-bus.js` untouched), D10 (F5 add-indicator seam reuse) all hold as
  designed. The only deviation is D8 (letters deferred), which is C1.
- **Optimistic-delete note (design R11):** the delete op is recorded before the DELETE
  resolves; a failed DELETE is accepted as a known, documented limitation (mitigation
  deferred). Not a regression — matches `design.md:209-211`.

## Blockers

None. C1 is a spec-vs-implementation gap reported for the orchestrator; no frozen invariant is
violated. W1–W5 are reconciliation warnings.
