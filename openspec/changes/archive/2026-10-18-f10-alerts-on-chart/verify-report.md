# Verify Report: f10-alerts-on-chart

```yaml
schema: gentle-ai.verify-result/v1
verdict: pass_with_warnings
blockers: 0
critical_findings: 2
requirements: 12
scenarios: 75
test_command: node --test "tests/js/**/*.test.js" && .venv/bin/python -m pytest -p no:randomly
test_exit_code: 0
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
```

**Change**: f10-alerts-on-chart (issue #123, Fase F10)
**Mode**: Strict TDD (`openspec/config.yaml: strict_tdd: true`)
**Branch**: `feat/f10-alerts-on-chart` @ `088779d` (tracker, S1a+S1b+S2+S3 merged). Base `develop` @ `b12c0df`.
**Chain**: S1a (`a220ad3`/`af5894a` → merge `7964d77`) → S1b (`f364e22`/`eafad4f` → merge `7f5e0a2`) → S2 (`ba887d0`/`81e9f67` → merge `441c30b`) → S3 (`8eeacc5`/`f7e4084`/`3b5ae62` → merge `088779d`). 20 files, +2163/−39.

## Verdict

`PASS_WITH_WARNINGS` — every gate is green (node 562/562, pytest 1123/1123, E2E 101/101, F10 E2E 4/4, ruff, migrations, diff-cover 100%), all frozen invariants hold (`marketChart` 8 keys, `STORE_KEYS` 11, `smc.js`/`chart-bus.js`/`chart-host.js`/`chart-store.js`/`src/`/`requirements.txt` byte-untouched, 49 modules ≤300 with an empty allowlist, `MODULE_ALLOWLIST` 31 / `CONTROLLER_ALLOWLIST` 17 all serving 200), and the API 400/404/A≠B matrix is exhaustively tested (45 tests). Two spec scenarios are not satisfied as written: `chart-alerts` R4 "Off-series anchor is dropped" (the core emits a fired marker at `last_fired_at` even when that time is not on the series — verified by execution) and `chart-alerts` R1 "Bell is keyboard reachable" (no test drives Tab/Enter/Space). Both are reported as CRITICAL, not fixed, per the brief.

## Requirement coverage matrix

Legend: ✅ PASS · ⚠️ PARTIAL · ❌ MISSING (no covering assertion) / deviating.

### chart-alerts (NEW: R1–R5, 15 scenarios)

| # | Scenario | Evidence | Result |
|---|---|---|---|
| 1 | Bell follows the crosshair | `alerts-controller.test.js::bell follows the crosshair and hides without a point` (y=100, aria-label `/100/`); E2E `test_bell_apply_posts_one_price_alert:128` (`aria-label` prefix "Create price alert at ") | ✅ |
| 2 | Bell hides without a point | `alerts-controller.test.js:163-164` (`move({})` → `hidden === true`) | ✅ |
| 3 | Bell is keyboard reachable | **no test** — no `Tab`/`Enter`/`Space` press in `test_market_alert_e2e.py` or `alerts-controller.test.js`; `<button type="button">` is set in `alerts.js:57-58` but unasserted | ❌ UNTESTED |
| 4 | Create from the bell | `alerts-controller.test.js::Apply creates one price alert through the cores:188-210` (one POST, exact body); E2E `test_bell_apply_posts_one_price_alert:145-155` (captured POST + `#alert-status`) | ✅ |
| 5 | Edit a nearby rule | `alerts-controller.test.js::a nearby price rule is edited with PUT instead of a duplicate POST:212-230` (0 POST, 1 PUT `/market/api/alerts/7`) | ✅ |
| 6 | Cancel writes nothing | `alerts-controller.test.js::Cancel writes nothing and returns focus to #chart:247-258`; E2E `test_cancel_writes_nothing_and_returns_focus:160-182` (`Escape`, `activeElement.id === "chart"`) | ✅ |
| 7 | Invalid level is rejected client-side | `alerts-controller.test.js::an invalid level writes nothing and keeps the dialog open:232-245`; `alert-condition-core.test.js` (`levelFromInput` rejects `""`/`"abc"`/`0`/`-1`/`Infinity`) | ✅ |
| 8 | Bell disabled on 1m | `alert-ui-core.test.js::EVALUABLE mirrors CANDLE_INTERVALS…:9` (`1m`/`3d`/`6h`/`8h`/`12h` false, `reasonText("1m")`); DOM-level disabled+`aria-describedby` asserted with `3d` in `alerts-controller.test.js:168-175` and E2E `test_bell_is_disabled_on_a_non_evaluable_interval:209-223` | ✅ |
| 9 | API rejects a non-evaluable interval | `test_market_alerts_api.py::test_alerts_post_bad_pair_is_400_and_writes_nothing[1m]` + `test_alerts_get_invalid_interval_is_400` | ✅ |
| 10 | Enabled on an evaluable interval | `alerts-controller.test.js:177-183` (`1h` → `disabled === false`, no `aria-describedby`) | ✅ |
| 11 | Markers on build | `alerts-controller.test.js::markers are created from the armed/fired rules…:262-276` (2 rules → handle list len 2, `"F 100"`, armed `time === anchor`); E2E `test_markers_summary_and_get_for_the_active_pair:199-205` asserts the summary `"3 alerts: 1 fired, 2 armed"`, not 3 markers at their anchors | ⚠️ PARTIAL |
| 12 | Switch clears and refetches | `alerts-controller.test.js::clearForSwitch detaches the marker handle and clears the bell:278-288`; E2E `_begin` + `test_markers_summary…:204` shows the GET for the new pair. No assertion of "exactly one GET" nor that the previous marker set is empty before the refetch | ⚠️ PARTIAL |
| 13 | Markers are not color-only | `alert-markers-core.test.js::markersFor: armed and fired differ by shape AND text AND position:77-84` (plus deep-equal payloads at `:51-75`) | ✅ |
| 14 | Off-series anchor is dropped | **No covering test, and the delivered core does the opposite.** `node -e` against `alert-markers-core.js` with `last_fired_at: 999`, `anchorTime: 100` returns `[{time:999,…}]` (`alert-markers-core.js:47-51`); `design.md:295-297` explicitly mandates "still render, never drop a rule silently". Spec says "produces no marker" | ❌ DEVIATING + UNTESTED |
| 15 | Envelope unchanged | E2E `Object.keys(window.marketChart).length === 8` (`test_market_alert_e2e.py:156,205`); `git diff --exit-code develop -- controllers/smc.js` clean; `chart-store.test.js` `STORE_KEYS` 11 | ✅ |

### alert-rules (ADDED R10/R11, 14 scenarios)

| # | Scenario | Evidence | Result |
|---|---|---|---|
| 1 | List is pair-scoped | `test_market_alerts_api.py::test_alerts_get_lists_only_the_requested_pair:85-97` (1h/5m/ETH isolation) + `::test_alerts_get_row_shape_and_epoch_last_fired_at:114-132` (exact 7-key row, `last_fired_at == 1729220400`) | ✅ |
| 2 | Missing pair key is 400 | `::test_alerts_get_missing_symbol_is_400`, `::test_alerts_get_missing_interval_is_400` | ✅ |
| 3 | Create normalizes the condition | `::test_alerts_post_valid_creates_row_owned_by_caller:168` (`50000.0`), `::test_alerts_post_normalizes_integer_level_to_float:186` | ✅ |
| 4 | Invalid condition is 400 | `::test_alerts_post_bad_condition_is_400_and_writes_nothing` (6 params) + `count()==0` | ✅ |
| 5 | Non-evaluable interval is 400 | `::test_alerts_post_bad_pair_is_400_and_writes_nothing[1m]`, `[unknown]`, `[empty-symbol]`, `[unknown-symbol]` + `count()==0` | ✅ |
| 6 | Partial PUT keeps absent fields | `::test_alert_put_is_active_updates_only_that_field:381`, `::test_alert_put_condition_updates_only_that_field:360`, `…telegram_chat_id…:393` | ✅ |
| 7 | Symbol is immutable on PUT | `::test_alert_put_immutable_pair_is_400_and_writes_nothing` (symbol + interval) + row unchanged; also `::test_alert_put_equal_symbol_and_interval_are_accepted_and_ignored:405` | ✅ |
| 8 | Unknown id is 404 | `::test_alert_put_miss_is_404:514`, `::test_alert_delete_miss_is_404:577` | ✅ |
| 9 | CSRF is enforced | `::test_alerts_post_requires_csrf:159`, `::test_alert_put_requires_csrf:526`, `::test_alert_delete_requires_csrf:589` (all 403 + no row) | ✅ |
| 10 | Delete returns 204 | `::test_alert_delete_own_removes_the_row:564` (204, empty body, gone) | ✅ |
| 11 | A ≠ B on list | `::test_alerts_get_never_leaks_another_users_rows:99`, `::test_alerts_post_b_is_invisible_to_a:314` | ✅ |
| 12 | A ≠ B on PUT and DELETE | `::test_alert_put_b_of_a_id_is_404_and_a_unchanged:542`, `::test_alert_delete_b_of_a_id_is_404_and_a_row_survives:600` | ✅ |
| 13 | Owner set on create | `::test_alerts_post_valid_creates_row_owned_by_caller` (`stored.user == AUTH_USER`), `::test_alerts_post_owner_is_never_taken_from_the_body:206` | ✅ |
| 14 | Anonymous is redirected | `::test_alerts_anonymous_get_redirects_to_login:53`, `…post…:153`, `::test_alert_put_anonymous_redirects_to_login:520`, `::test_alert_delete_anonymous_redirects_to_login:583` (4 × 302 `/login/`) | ✅ |

### design-system (MODIFIED R6/R7, 24 scenarios)

| # | Scenario | Evidence | Result |
|---|---|---|---|
| 1 | Alert bell is focusable and named | `alerts.js:57-61` (`<button type=button>`, `aria-label`); E2E `:128` asserts the name. **No assertion of `type="button"`, Tab reachability, or `:focus-visible`** | ⚠️ PARTIAL |
| 2 | Alert dialog returns focus | E2E `test_cancel_writes_nothing_and_returns_focus:176-182` (`activeElement.id === "chart"`, zero writes); node `:247-258` | ✅ |
| 3 | Alert state is live in the DOM | E2E `test_markers_summary_and_get_for_the_active_pair:199-203` asserts `#alert-status` === `"3 alerts: 1 fired, 2 armed"`; `chart.html:111` `aria-live="polite"`; also `test_f10_alert_ui_is_markup_only` | ✅ |
| 4 | Alert markers are not color-only | `alert-markers-core.test.js:77-84` | ✅ |
| 5 | Alert dialog is CSP-clean | `test_market_ux.py::test_f10_alert_ui_is_markup_only:217` + `::test_market_page_has_no_inline_script_or_handler:304` (regex scan for `<script>` w/o `src` and `\son[a-z]+=`); `chart.html:95-109` is static | ✅ |
| 6 | CSP header unchanged | `middleware.py` untouched (`git diff --exit-code` clean); `test_csp_present_on_market_page:421` | ✅ |
| 7 | No inline handler remains | `test_market_page_has_no_inline_script_or_handler` (whole page incl. the new dialog) | ✅ |
| 8 | Menu is CSP-clean | Pre-existing F7 (`context-menu.js` `addEventListener`), unchanged by F10 | ✅ |
| 9–24 | Visible focus, chart focusable/labelled, dialog traps focus, toolbar/tree not color-only, LONG/SHORT, readouts live, coalescing, Escape draft, menu keyboard, menu names, undo announce, tool letters, F9 kinds, F9 labels, draft preview, AA light theme | Pre-existing F6/F7/F9 suites, unchanged by F10; `theme.css` only appends `.chart-alert-bell` + `#alert-dialog` rules with a `:focus-visible` outline (`theme.css:161-182`) | ✅ |

### market-chart (MODIFIED R14/R18/R20, 22 scenarios)

| # | Scenario | Evidence | Result |
|---|---|---|---|
| 1 | Inventory and no-cycle | `test_market_ux.py::test_import_graph_routes_resolve:266` green (derives every relative import → 200); `alerts.js:16-18` imports only the three cores; no controller imports `main` | ✅ |
| 2 | Store never holds candles | `chart-store.js:13-27` untouched; `chart-store.test.js::STORE_KEYS is exactly the UI/config vocabulary (11 …)` | ✅ |
| 3 | Size ceiling with empty allowlist | `test_module_size_guard.py` 3 passed; measured: 49 modules, `CEILING=300`, `ALLOWLIST=frozenset()`, `over={}`, max `smc.js 300` | ✅ |
| 4 | New cores are served | `test_market_ux.py::test_f10_alerts_are_served:198` (3 cores + controller, all 200 `text/javascript`) | ✅ |
| 5 | Controller allowlist count is 16 | `::test_controller_allowlist_routes_serve_javascript:146` and `::test_f9_cores_are_served:195` both assert `== 17`; measured `CONTROLLER_ALLOWLIST` = 17 | ✅ |
| 6 | No behavior change | node 562/562, pytest 1123/1123, market E2E 101/101; only the F10 additions and the fixture move | ✅ |
| 7 | Seam shape frozen | `test_market_e2e.py::test_shell_keeps_seam_at_eight_keys:2542-2551` (`== 8`, `SmcOverlayCore` intact) | ✅ |
| 8–11 | Measure / undo+menu / F9 kinds / alerts assert without a seam key | Pre-existing E2E; alerts: `#chart-alert-bell`, `#alert-dialog`, `#alert-status`, captured POST (E2E `:113-156`) | ✅ |
| 12 | SMC core reachable | Pre-existing E2E (`SmcOverlayCore.setupMarkers`), `smc.js` untouched | ✅ |
| 13 | Existing E2E green except replaced assertions | market E2E 101 passed; the only deletion is the fixture move to `conftest.py` (no assertion lost) | ✅ |
| 14 | Seam stays 8 keys | As #7 (asserted 2× in the F10 E2E, plus the pre-existing test) | ✅ |
| 15 | Exactly one new bus event (unchanged set) | `chart-bus.js` byte-untouched (`git diff` clean); `EVENTS` = the 13 pre-existing members; `alerts.js` has **zero** `bus.emit` | ✅ |
| 16 | STORE_KEYS stays 11 | `chart-store.js` untouched; `chart-store.test.js` deep-equals the 11 keys | ✅ |
| 17–20 | Visibility / measure+position / undo+menu / F9 option-only | Pre-existing node suites (`chart-host.test.js`, `chart-controllers.test.js`, `drawing-primitive.test.js`) | ✅ |
| 21 | Alert markers never touch the series data path | `alerts.js` has no `setData`/`update` (grep: only the header comment); `alerts-controller.test.js`'s series stub exposes only `coordinateToPrice`/`priceToCoordinate`, so a series write would throw. **No explicit `setData`/`update` spy installed for an alert render** | ⚠️ PARTIAL |
| 22 | Existing E2E stays green except replaced assertions | market E2E 101 passed, default type still candles (pre-existing assertion) | ✅ |

**Compliance summary**: 69/75 fully compliant, 4 PARTIAL, 2 MISSING/DEVIATING.

## Gates

| Gate | Command | Result |
|---|---|---|
| Node unit | `node --test "tests/js/**/*.test.js"` | ✅ `tests 562 / pass 562 / fail 0` (F10 files alone: 40/40) |
| Python suite | `.venv/bin/python -m pytest -p no:randomly` | ✅ `1123 passed, 105 deselected in 271.26s` |
| F10 API suite | `.venv/bin/python -m pytest tests/web/test_market_alerts_api.py` | ✅ 45 tests passed |
| F10 E2E | `.venv/bin/python -m pytest tests/web/test_market_alert_e2e.py -m e2e` | ✅ `4 passed in 16.46s` |
| Existing E2E | `.venv/bin/python -m pytest tests/web/test_market_e2e.py -m e2e` | ✅ `101 passed in 377.79s` (no class-C flake this run) |
| Ruff lint | `.venv/bin/ruff check .` | ✅ `All checks passed!` |
| Ruff format | `.venv/bin/ruff format --check .` | ✅ `150 files already formatted` |
| Migrations | `.venv/bin/python web/manage.py makemigrations --check --dry-run` | ✅ `No changes detected` |
| Patch coverage | `.venv/bin/diff-cover /tmp/opencode/cov-f10.xml --compare-branch=origin/develop` | ✅ `web/market/alerts.py (100%)` — Total 102 lines, Missing 0, Coverage 100% |

### TDD compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence table in apply artifact | ⚠️ | The Engram apply-progress (#1667) carries per-slice commits and gate results but **no "TDD Cycle Evidence" table** |
| RED before GREEN (commit level) | ✅ | `a220ad3` (test) → `af5894a` (feat); `f364e22` → `eafad4f`; `8eeacc5` (test) → `f7e4084` (feat) |
| RED before GREEN, S2 | ⚠️ | `ba887d0` and `81e9f67` each add the test **and** the core in one commit, so the red state is not observable in history |
| GREEN confirmed on execution | ✅ | All F10 node/API/E2E tests pass now |
| Triangulation | ✅ | Multiple parametrized cases per branch (`test_market_alerts_api.py` 45 tests; 40 node tests) |
| Assertion quality | ✅ | No tautologies, no ghost loops, no mock-only assertions; deep-equals on payloads and captured request bodies |

## Invariants

| Invariant | Command / evidence | Result |
|---|---|---|
| `window.marketChart` exactly 8 keys | `main.js:60-69` untouched shape; E2E `Object.keys(...).length == 8` (F10 E2E `:156,205`; `test_market_e2e.py:2550`) | ✅ |
| `STORE_KEYS` exactly 11 | `chart-store.js:13-27`; `chart-store.test.js` deep-equal | ✅ |
| Every `templates/market/**/*.js` ≤300, empty allowlist | `test_module_size_guard.py` 3 passed; measured 49 modules, 0 over, max `smc.js` 300 | ✅ |
| Module sizes | `alert-markers-core` **62**, `alert-condition-core` **44**, `alert-ui-core` **25**, `controllers/alerts` **291**, `main` **282**, `smc` **300**, `chart-host` **267**, `chart-store` **61**, `chart-bus` **54** | ✅ |
| `smc.js`, `chart-bus.js`, `chart-host.js`, `chart-store.js` byte-untouched | `git diff --exit-code develop...HEAD -- …` → exit 0 for all four | ✅ |
| #68 markers only via `createSeriesMarkers`; no `setData`/`update` added | `alerts.js:207` `LightweightCharts.createSeriesMarkers`, `:208`/`:219`/`:236` `setMarkers`; no writer in the file; diff has no added `.setData(`/`.update(` | ✅ |
| R14 every alert query `for_user`; A≠B → 404 | `alerts.py:85,109,131` — all three query sites use `AlertRule.for_user`; `test_alert_put_b_of_a_id_is_404…`, `test_alert_delete_b_of_a_id_is_404…` | ✅ |
| `requirements.txt` / `src/` unchanged | `git diff --exit-code develop...HEAD` → clean | ✅ |
| No inline handler / script | `test_market_page_has_no_inline_script_or_handler`; dialog is static markup, bell JS-built | ✅ |
| CSP unchanged | `web/market/middleware.py` untouched; `test_csp_present_on_market_page` | ✅ |
| `MODULE_ALLOWLIST`==31, `CONTROLLER_ALLOWLIST`==17, all served 200 | measured 31 / 17; `test_f10_alerts_are_served` + `test_controller_allowlist_routes_serve_javascript` | ✅ |
| No migration / no schema change | `makemigrations --check` → `No changes detected` | ✅ |

## Findings

### CRITICAL

- **C1 — `chart-alerts` R4 "Off-series anchor is dropped" is not implemented, and no test covers it.** The spec (`specs/chart-alerts/spec.md:134-138`) requires: *"GIVEN a fired rule whose `last_fired_at` is not a loaded candle time / WHEN the marker list is computed / THEN that rule produces no marker (never a synthetic data point, #68)."* `alert-markers-core.js:47-51` instead keeps `last_fired_at` as the marker time for any finite value, with no comparison against the loaded candle times; executed directly (`markersFor([{condition:{level:10},is_active:true,last_fired_at:999}], 100)`) it returns `[{time:999,…,text:"F 10"}]`. `design.md:295-297` explicitly chooses the opposite ("fall back to `anchorTime` (still render, never drop a rule silently)"), so **spec and design disagree** and the code follows the design. No test asserts either branch for an off-series fired anchor. Reported, not fixed. Fix is one line (pass the loaded times / compare `last_fired_at` to `anchorTime`) **plus** a spec or design decision about which side wins.
- **C2 — `chart-alerts` R1 "Bell is keyboard reachable" and `design-system` R6 "Alert bell is focusable and named" have no covering test.** No test in `tests/web/test_market_alert_e2e.py` or `tests/js/alerts-controller.test.js` presses `Tab`, `Enter` or `Space` on `#chart-alert-bell`, and nothing asserts `type="button"` or a visible `:focus-visible` state (`tests/web/test_market_ux.py` only checks the dialog markup and the served JS). The implementation is a real `<button type="button">` (`alerts.js:57-58`) with a `:focus-visible` outline (`theme.css:174`), so the behaviour is very likely correct — the *proof* is missing. Reported, not fixed.

### WARNING

- **W1 — `MODULE_ALLOWLIST` is 31, not the 30 the spec and design state.** `specs/market-chart/spec.md:5,41` and `tasks.md:81` say `28→30` with exactly two new cores; the delivery also extracted `alert-ui-core.js` (25 lines, `3b5ae62`) and `web/market/views.py:69` lists it, so the count is 31 (asserted at `tests/web/test_market_ux.py:204`). The third core is not in the R14 inventory list, the design's module table, or the `chart.html` preload budget described in the spec. Functionally harmless; the spec text must be reconciled at archive.
- **W2 — Alert markers have no explicit `setData`/`update` spy assertion.** `market-chart` R20 "Alert markers never touch the series data path" is asserted only implicitly: the controller test's fake series exposes neither method (a call would throw) and `alerts.js` contains no writer. Every other F6/F7/F9 layer has an explicit spy test (`chart-host.test.js:343`, `drawing-primitive.test.js:297`); F10 does not, so a future edit that reaches for a writer would fail nothing until it fails at runtime.
- **W3 — Session-expiry (302 → login) is not handled as the design specifies.** `design.md:239` requires `on 302 → window.location.assign("/login/")`. `alerts.js:161-167` instead inspects `r.ok`; a redirected login page returns 200 HTML, so `r.json()` rejects and the user sees `"Network error — the alert was not saved"` (`:167`) instead of being redirected. No spec requirement is broken (the spec is silent), but the shipped behaviour diverges from the design flow.
- **W4 — `EVALUABLE` duplicates `CANDLE_INTERVALS` with no parity test.** `alert-ui-core.js:11` hardcodes the eight intervals; `alert-ui-core.test.js:7-13` re-hardcodes the same list. Nothing derives one from the other (the front end cannot import Python), so a server-side interval change silently desynchronises the guard. A generated value in `CONFIG` (or a pytest that greps the JS) would close it.
- **W5 — TDD evidence table missing from the apply artifact.** Engram #1667 reports commits and gates but no "TDD Cycle Evidence" table, and the S2 commits (`ba887d0`, `81e9f67`) add test + implementation together, so their red state is unobservable. Rated WARNING (not CRITICAL) because the git history does show test-first commits for S1a/S1b/S3 and all F10 tests pass on execution.

### SUGGESTION

- **S1 — `tasks.md` checkboxes are all unticked (37 `- [ ]`, 0 `- [x]`).** Consistent with the apply contract forbidding `openspec/**` edits; needs an archive-reconciliation note like the F7/F9 `tasks.md` files.
- **S2 — The spec's non-evaluable list omits `30m`.** `specs/chart-alerts/spec.md:83` names `1m/3d/6h/8h/12h`, but `<select id="interval">` also offers `30m` (`chart.html:24`), which is not in `CANDLE_INTERVALS` and is correctly rejected by `eligible()`/the API. The list should be "every interval not in `CANDLE_INTERVALS`" rather than an enumeration.
- **S3 — Bell placement deviates from the design's `{x, y}`.** `design.md:218-223` positions the bell at `{x,y}`; `alerts.js:82-86` pins the vertical to the crosshair price but anchors horizontally (`right: var(--sp-2)`), because an x that tracks the cursor is unclickable. The spec only mandates "positioned at the crosshair point's price", so this is compliant; the design text should record the change.
- **S4 — `alerts.js` (291) and `main.js` (282) have less headroom than the design estimated** (218/280). Both remain under the empty-allowlist ceiling, but `main.js` has 18 lines and `alerts.js` 9 before the guard trips.

## Non-blockers / notes

- **E2E class-C flake (#149) not observed this run.** Market E2E 101/101 and F10 E2E 4/4 passed in single full runs; the apply-progress recorded one flake of `test_position_three_click_persists_and_drag_one_put` which passed in isolation, consistent with the known pre-existing flake.
- **`smc.js` = 300 pre-existing**, byte-untouched here (`git diff --exit-code` clean) and the layering guard is pinned by two tests: `alerts-controller.test.js::controllers/smc.js carries no alert token` and `test_market_ux.py::test_f10_alert_ui_is_markup_only` (`b"alert" not in smc.lower()`).
- **Retroactive refactor is legitimate TDD after the fact**: `3b5ae62` extracted `alert-ui-core.js` mid-S3 to keep `alerts.js` under the ceiling; it carries its own 5-case node test and the module is served (allowlist + preload).
- **Fixtures moved, not deleted.** `e2e_user`/`browser_page` moved from `test_market_e2e.py` to `tests/web/conftest.py` (`8eeacc5`) so a second E2E module can share them without ruff F811. No assertion was lost (market E2E still 101 tests).
- **HTTP verbs and CSRF verified end to end**: 4 anonymous 302s, 3 CSRF 403s (POST/PUT/DELETE), 8 evaluable intervals accepted, and every 400/404 leaves `AlertRule.objects.count()` unchanged.
- **`last_fired_at` serialization round-trips**: stored `datetime.fromtimestamp(1729220400)` → row `1729220400` (`test_alerts_get_row_shape_and_epoch_last_fired_at`), and `null` for never-fired (`test_alerts_post_valid_creates_row_owned_by_caller`).
- **`condition` is echoed verbatim** from the stored row (`_row`, `alerts.py:36`) and normalized server-side through the frozen `parse_condition` (`alerts.py:71,162`), so the client cannot mint a shape the evaluator rejects.
- **No order-execution path, no `src/` change, no dependency, no CSP relaxation** — the read-only boundary holds.
