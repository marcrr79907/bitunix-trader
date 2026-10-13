```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:b4f820da213c58f68eb82c4a132178233d35e6fb1cc42d547f26cd5c590a3b71
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 13/13
scenarios: 43/47
test_command: .venv/bin/python -m pytest -m e2e -p no:randomly -q
test_exit_code: 0
test_output_hash: sha256:12a9a4a8915fb8d2bb5b4227220247cde267c1a0620203589fe47280d5be4a7f
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check .
build_exit_code: 0
build_output_hash: sha256:8442954ccab1cb1c3623d52b95620ca485276ee1e43e499fb987774457ffddf6
```

# Verify Report — chart-shell (issue #116, Fase F3)

**Verdict**: `pass_with_warnings`
**Verified by**: fresh adversarial verifier (independent replication + throwaway Django-client and Playwright probes; apply reports NOT trusted)
**Branch**: `feat/chart-shell-persistence` (HEAD `1cb54d0`), chain: tracker `feat/chart-shell` + S1 `feat/chart-shell-shell` (`bd081cf`, merged `47f021c`) + S2 `feat/chart-shell-persistence` (`1cb54d0`). All slice PRs base on the tracker.
**Mode**: Strict TDD (node --test + pytest + E2E). Artifact store: openspec.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 13 (1.1–1.6, 2.1–2.7) |
| Tasks complete | 13 |
| Tasks incomplete | 0 |

`tasks.md` checkboxes are unmarked, but the apply-progress artifact (`sdd/chart-shell/apply-progress`, id 1524) records all 13 complete, and every acceptance artifact exists and passes at runtime. `tasks.md` is under `openspec/**`, which the executor contract forbids editing — not a finding.

## Gates (L1)

| Gate | Command | Result |
| --- | --- | --- |
| JS unit | `node --test "tests/js/**/*.test.js"` | **81 passed, 0 fail** (exit 0) — SHA256 `05f1157e…` |
| E2E | `.venv/bin/python -m pytest -m e2e -p no:randomly -q` | **36 passed** (exit 0) — 33 baseline + 3 new preference tests |
| Python unit | `.venv/bin/python -m pytest tests/ --ignore=tests/web -q` | **337 passed** (exit 0) |
| Lint/format | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | **clean** (134 files, exit 0) |
| Migration drift | `python web/manage.py makemigrations --check --dry-run` | **"No changes detected"** (exit 0) |
| Django check | `python web/manage.py check` | **no issues** (exit 0) |
| Dependency | `git diff origin/develop -- requirements.txt` | **empty** (exit 0, no new dep) |
| `src/` boundary | `git diff origin/develop...HEAD --stat -- src/` | **empty** (0 lines, no core change) |
| CSP / settings | `git diff origin/develop...HEAD --stat` grep settings/middleware | **empty** (CSP unchanged) |

`git diff --stat origin/develop...HEAD` = 22 files, +1794/−34 (bulk = the four planning docs + tests). Slice 2 diff vs the tracker = 10 files, +432/−21.

## Gates (L2) — Patch coverage

Generated the real CI artifact (`python -m pytest --cov --cov-report=xml`, config `[tool.coverage.run] source=["web","src"]`), then:

`diff-cover coverage.xml --compare-branch=feat/chart-shell --fail-under=100` →

```
web/market/views.py (100%)
web/trading/models.py (100%)
Total:   26 lines
Missing: 0 lines
Coverage: 100%
```

**exit 0**. Both changed Python files (the `api_preference`/`_put_preference` handlers and `ChartPreference`) are fully covered by the new endpoint + model tests. All JS is outside the Python patch gate → covered by 81 node + 36 E2E tests.

> Note: my first run passed `--cov=web/market --cov=web/trading`, which overrode `[tool.coverage.run].source` and emitted *relative* XML filenames (`views.py`, `models.py`) that diff-cover could not map to the repo diff (it then reported only models.py, 4 lines). Re-running exactly as CI does (`--cov` with no args) produced repo-relative paths and the correct 26-line result. No gate defect — a reproduction detail worth recording.

## TDD Compliance (Strict TDD)

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | "TDD Cycle Evidence" table found in apply-progress |
| All tasks have tests | ✅ | 13/13 tasks map to a node/E2E/route/model test |
| RED confirmed (tests exist) | ✅ | `test_market_api.py` (+12), `test_isolation.py` (+5), `test_owned_model_guard.py` (+2), `test_market_e2e.py` (7 shell + 3 preference) all exist |
| GREEN confirmed (tests pass) | ✅ | 81 node + 36 E2E + 337 py pass on my fresh execution |
| Triangulation adequate | ✅ | preference GET-miss / PUT-round-trip / invalid-400 / non-object-400 / anon-302 / CSRF-403 / A≠B-GET / A≠B-PUT / upsert / one-row-per-user / owner-required — different expected values, not all-empty |
| Safety Net for modified files | ✅ | Existing suites run before extension; **0 removed lines** in `test_market_e2e.py` vs develop, and the 15 pre-existing `select_option("#interval")` calls are unchanged (18 now = 15 + 3 added) |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (py HTTP/model/guard) | 12 preference API + 5 model + 1 guard param | `tests/web/test_market_api.py`, `test_isolation.py`, `test_owned_model_guard.py` | pytest + Django client |
| Unit (JS) | 81 | `tests/js/*` | node --test |
| E2E | 36 | `tests/web/test_market_e2e.py` | Playwright (chromium) |
| **Total** | **81 node + 337 py + 36 E2E** | | |

### Changed File Coverage

| File | Line % | Rating |
|------|--------|--------|
| `web/market/views.py` (+41) | 100% diff-cover | ✅ Excellent |
| `web/trading/models.py` (+18) | 100% diff-cover | ✅ Excellent |
| `web/trading/migrations/0009_chartpreference.py` | n/a (omitted from coverage config) | ➖ |
| `theme.css`, `chart.html`, `chart-host.js`, `toolbar.js`, `main.js`, `chart.js` | n/a (JS/CSS; outside Python gate) | ✅ covered by 81 node + 36 E2E |
| `web/market/urls.py` (+5) | no measurable lines (route constant) | ✅ route served |

**Average changed Python file coverage**: 100% (26 changed lines, 0 missing).

### Assertion Quality

**Assertion quality**: ✅ All assertions verify real behavior.
- No tautologies, no type-only-alone assertions, no ghost loops, no smoke-test-only.
- `test_preference_*` asserts exact JSON bodies (`{"interval":"1h","exists":true}`), counts (`count()==0` after 400), and row identity; `test_isolation.py` asserts `DoesNotExist` + `for_user(user_b).count()==0`.
- E2E asserts concrete geometry (`chartH > 480`, `abs(rootH-chartH) <= 2`), exact counts (14 chips, 8 keys), `aria-pressed` transitions, `input_value()=="5m"`, `overscroll <= 1`, and the debounced PUT body (`json.loads(...) == {"interval":"5m"}`).
- No banned `innerHTML`/CSS-class-only implementation coupling in the new assertions (chip styling is asserted via `aria-pressed`, not class names).

### Quality Metrics
**Linter**: ✅ No errors (ruff, 134 files)
**Type Checker**: ➖ Not applicable (JS/Django project)

## Spec Compliance Matrix

### chart-shell (R20–R25)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R20 | Chart fills the viewport height | E2E `test_chart_fills_height_and_canvas_tracks_container` (`chartH>480`, `canvasH>480`) | ✅ COMPLIANT |
| R20 | Resize follows the container | adversarial probe: resize 900→640, root tracks `#chart` (`abs<=2`), still `ready`, no re-boot | ⚠️ PARTIAL — proven by session probe; no committed test |
| R20 | No fixed height option remains | E2E `test_chart_host_has_no_fixed_height_and_autosize` (`autoSize: true`, no `height:\d`) | ✅ COMPLIANT |
| R21 | Chip click switches the interval | E2E `test_interval_chips_switch_and_reflect_store` (1m→5m, pressed moves, select `5m`) | ✅ COMPLIANT |
| R21 | Hidden select stays action-able | E2E `test_hidden_select_stays_selectable_and_syncs_chips` (display≠none, `select_option("1h")` works) | ✅ COMPLIANT |
| R21 | Both paths emit one command | E2E `test_interval_change_debounce_saves_preference` + `...selectable...` (one PUT; one `config:changed` per path; source has exactly one emit per listener) | ✅ COMPLIANT |
| R21 | Active chip reflects store | E2E `test_boot_restores_saved_interval_preference` (5m chip true) | ✅ COMPLIANT |
| R22 | Enter/Space activates | adversarial probe: ArrowRight 1m→5m, Enter→5m, Space→15m, select syncs | ⚠️ PARTIAL — proven by session probe; no committed test |
| R22 | Arrows move focus | adversarial probe: `ArrowRight` moves `document.activeElement` 1m→5m | ⚠️ PARTIAL — proven by session probe; no committed test |
| R23 | Toggle collapses ≤820px | E2E `test_panel_toggle_collapses_and_expands_at_375` (aria-expanded false, panel hidden) | ✅ COMPLIANT |
| R23 | Toggle expands again | E2E same test (second click → shown, true) | ✅ COMPLIANT |
| R23 | Desktop unchanged (>820px) | adversarial probe: 821px → toggle hidden, panel visible | ⚠️ PARTIAL — proven by session probe; no committed test |
| R24 | No overflow at 375px | E2E `test_no_horizontal_overflow_at_375` (`overflow<=1`, `flex-wrap` = wrap) | ✅ COMPLIANT |
| R25 | Focus and names | static: global `:focus-visible{outline:2px solid}` + `aria-label` group/select; adversarial probe: outline≠none, names `1m`/`Interval`/`Panel` | ⚠️ PARTIAL — static + session probe; no committed test |
| R25 | CSP and manifest unchanged | `test_market_ux.py::test_market_page_has_no_inline_script_or_handler` + `test_csp_present_on_market_page` (`https://unpkg.com` present); settings diff empty; requirements diff empty | ✅ COMPLIANT |

### chart-config (R8–R11)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R8 | One row per user | `test_isolation.py::test_chart_preference_one_row_per_user` (IntegrityError on 2nd create) + API `test_preference_put_upserts_one_row_for_the_user` | ✅ COMPLIANT |
| R8 | Additive migration | `makemigrations --check --dry-run` → "No changes detected"; migration is a single `CreateModel` | ✅ COMPLIANT |
| R8 | JSON/field round-trip | `test_chart_preference_default_interval_and_round_trip` (`"1m"` default, `"4h"` re-read) + `test_chart_preference_owner_is_required` (no owner-less row) | ✅ COMPLIANT |
| R9 | GET default when no preference | `test_preference_get_default_when_absent` (200 `{interval:"1m",exists:False}`, count 0) | ✅ COMPLIANT |
| R9 | PUT then GET returns the saved interval | `test_preference_put_then_get_round_trip` (`{interval:"1h",exists:true}`) | ✅ COMPLIANT |
| R9 | Invalid interval → 400 | `test_preference_put_invalid_interval_is_400_and_writes_nothing` + non-object/invalid-JSON 400 tests | ✅ COMPLIANT |
| R9 | Unauthenticated → redirect | `test_preference_anonymous_get_redirects_to_login` + `..._put_...` (302→`/login/`) | ✅ COMPLIANT |
| R9 | CSRF-protected PUT | `test_preference_put_requires_csrf` (enforce_csrf_checks → 403) | ✅ COMPLIANT |
| R10 | Persisted interval restores on reload | E2E `test_boot_restores_saved_interval_preference` (seeded 5m → 5m chip + select) | ✅ COMPLIANT |
| R10 | Fetch failure defaults to 1m | E2E `test_boot_preference_fetch_failure_defaults_to_1m` (abort route → 1m chip + select + candleSeries exists) | ✅ COMPLIANT |
| R10 | Change persists | E2E `test_interval_change_debounce_saves_preference` (exactly one PUT `{interval:"5m"}` after 500ms debounce) | ✅ COMPLIANT |
| R11 | B never sees A's preference | `test_preference_isolation_b_get_never_sees_a` + probe | ✅ COMPLIANT |
| R11 | B's PUT does not touch A's row | `test_preference_isolation_b_put_does_not_touch_a_row` (A refreshed unchanged) | ✅ COMPLIANT |
| R11 | CSP unchanged | `test_csp_present_on_market_page` + settings diff empty | ✅ COMPLIANT |

### market-chart (R20 shell envelope)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R20 | Seam stays 8 keys | E2E `test_shell_keeps_seam_at_eight_keys` (8 keys, `SmcOverlayCore` object) | ✅ COMPLIANT |
| R20 | No new bus event or module | grep: `main.js`/`toolbar.js` emit/on only `{chart:built, config:changed, indicator:changed, ready}`; serve allowlists unchanged vs develop | ✅ COMPLIANT |
| R20 | Existing E2E stays green unedited | 15 original `select_option` calls unchanged (0 removed lines in the whole file); 36 E2E pass | ✅ COMPLIANT |

### per-user-isolation (R14.2, R14.3)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R14.2 | A cannot read B's ChartPreference | `test_isolation.py::test_chart_preference_cross_user_get_denied` | ✅ COMPLIANT |
| R14.2 | A cannot read B's ExchangeCredential/Watchlist/PositionSnapshot/AccountSnapshot/Trade/ChartLayout/Drawing/AlertRule | `test_cross_user_get_denied` + `test_cross_user_get_denied_for_private_models` + `test_chart_layout_*`/`test_drawing_*`/`test_alert_rule_*` | ✅ COMPLIANT |
| R14.3 | Scanner flags an unscoped query / the new models / Drawing / AlertRule / ChartPreference | `test_scanner_flags_an_unscoped_owned_query`, `test_scanner_flags_the_private_models` (incl. `ChartPreference.objects.all()` param), `test_scanner_flags_unscoped_verbs` | ✅ COMPLIANT |
| R14.3 | Scoped query passes the guard | `test_scanner_allows_for_user` + `test_scanner_allows_for_user_on_the_private_models` | ✅ COMPLIANT |
| R14.3 | bulk_create and count are sanctioned | `test_request_path_has_no_unscoped_owned_query` (real tree clean; `.count()` not in UNSCOPED_VERBS); worker-zone test `test_worker_zone_reads_across_users` | ✅ COMPLIANT |
| R14.3 | Worker reads/persists across users legitimately | pre-existing `test_worker_*` (337 py suite) | ✅ COMPLIANT |

**Compliance summary**: 43/47 scenarios COMPLIANT, 4 PARTIAL (covered by this session's adversarial probes, not committed tests), 0 FAILING, 0 UNTESTED.

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R20 `autoSize:true`, no numeric height | ✅ | `chart-host.js:123-126` = `{autoSize:true, timeScale:{timeVisible:true}}`; grep `height:\d` in the file/theme.css → none |
| R20 resolved container height | ✅ | `body:has(.market-layout){height:100dvh}` + `main{flex:1 1 auto;min-height:0}` + `.market-layout{height:100%}` chain resolves |
| R21 select retained + clipped | ✅ | `<select id="interval">` in DOM; JS adds `.visually-hidden` (`clip:rect(0 0 0 0)`, `position:absolute` — never `display:none`/`hidden`) |
| R21 chips derived from options | ✅ | `toolbar.js` iterates `select.options` → no 4th interval copy; `role="group" aria-label="Interval"` |
| R21 bidirectional sync | ✅ | chip `activate()` sets `select.value` + `setPressed` + one emit; `select.change` calls `setPressed` + one emit |
| R22 keyboard | ✅ | native `<button>` (Enter/Space) + ArrowLeft/Right wrap focus across chips |
| R23 toggle | ✅ | `<button class="panel-toggle" aria-expanded aria-controls="panel">`; `classList.toggle("panel-collapsed")` + `aria-expanded` |
| R24 375px | ✅ | `.interval-chips{flex-wrap:wrap}`; `@media(max-width:820px)` single-column |
| R25 a11y/CSP/dep | ✅ | global `:focus-visible` outline; chips carry `aria-pressed` (state not color-only); no inline script/handler; CSP + requirements unchanged |
| R8 model | ✅ | `ChartPreference(UserOwnedModel)`: `OneToOneField(user, related_name="chart_preference", CASCADE)`, `last_interval CharField(8, default="1m")`, `updated_at auto_now` |
| R8 migration | ✅ | `0009_chartpreference.py` = single `migrations.CreateModel` (additive; dependency on `0008_alertrule_telegram`) |
| R9 endpoint | ✅ | both `@login_required` + `@require_http_methods(["GET","PUT"])`; PUT validated against `INTERVALS` BEFORE write; miss → `{interval:"1m",exists:false}` (never 404); route `market_api_preference` without altering existing routes |
| R10 boot | ✅ | `loadPreference()` before `start()`; `.catch → "1m"`; `toolbar.setInterval` applied before first build; debounced `savePreference` (500ms) on genuine interval change only |
| R11 isolation | ✅ | all access via `ChartPreference.for_user(request.user)`, owner passed explicitly; 0 unscoped `ChartPreference.objects` in `web/` request path (grep) |
| Frozen 8-key seam | ✅ | `main.js` seam object literal has exactly 8 keys; no new `window` global; `SmcOverlayCore` still assigned |
| No new dep / CSP / `src/` | ✅ | requirements diff empty; settings diff empty; `src/` diff empty |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Q3 `ChartPreference` + `0009` + `/market/api/preference` | ✅ Yes | Exactly as designed |
| Q2 keep `<select>`, `.visually-hidden` via clip | ✅ Yes | `clip:rect(0 0 0 0)`, never display:none |
| Q1 chips from `select.options` | ✅ Yes | `Array.prototype.forEach.call(select.options, …)` |
| Q5 `autoSize:true`, remove `height:480` | ✅ Yes | No numeric height remains |
| Q4 `<button aria-expanded aria-controls>` + `.panel-collapsed` | ✅ Yes | Native button, class toggle |
| Boot pref owner = `main.js`, debounced PUT | ✅ Yes | `loadPreference`/`savePreference` mirror `saveLayout` |
| **Deviation: `body{min-height:100dvh}` + flex** | ⚠️ Partial | Implementation scopes the definite height with `body:has(.market-layout){height:100dvh}` (and keeps `min-height:100dvh` globally) instead of the design's un-scoped `body{min-height:100dvh}`. Strictly better: non-market pages keep normal page scroll. Does not break any scenario. |
| **Deviation: `start()` gen guard** | ⚠️ Partial | apply changed the guard to `if (gen !== 0) return` before `++gen` so a switch racing the async pref fetch still wins. Behaviour-preserving and disclosed; `mine` guards unchanged. |
| **Deviation: fallback E2E assertion** | ⚠️ Partial | "fetch failure defaults to 1m" asserts `candleSeries` exists + select/chip say 1m (rather than candle count > 0 — 1m is unseeded, so a count would be 0 for unrelated reasons). Reasonable; disclosed. |

## Adversarial Probes (independent)

- **Grep**: `#interval` still in `chart.html`; `.visually-hidden` uses `clip` (not display:none); `autoSize: true` present; no `480`/`height:\d` in host or theme.css; exactly 8 seam keys; `window.marketChart` writes only `smcToggles`/`ready` (seam object literal has the 8 keys); **0** unscoped `ChartPreference.objects` in `web/{market,trading,accounts,config}`; `stream.js` diff vs develop = **0 lines**.
- **Endpoint probe** (throwaway Django client, all on one test, exit 0): GET miss default; PUT→GET round-trip; invalid interval → 400 **no write**; non-object body → 400 no write; anon GET **and** PUT → 302; A≠B GET (B sees default) and A≠B PUT (A's row untouched, 2 rows total); upsert (2 PUTs → 1 row); model round-trip; no owner-less row.
- **Real browser** (Playwright, logged in, `/market/`, throwaway probes, exit 0):
  - **14 chips**; select clipped (display≠none, `is_visible()` true/actionable); chart height **623px > 480** (canvas pane 395px > 0); root ≈ `#chart` (`abs<=2`) — autoSize works, no zero-height.
  - Chip click → select syncs to `15m`, `aria-pressed` moves; **375px overflow = 0**; collapse toggle flips `aria-expanded`; set `2h`, reload → restored (chip + select).
  - **Keyboard**: `ArrowRight` moves focus 1m→5m, `Enter` activates 5m, `Space` activates 15m; accessible names `1m`/`Interval`/`Panel`; focus outline ≠ none; at 821px toggle hidden + panel visible, at 820px toggle visible.
  - **Resize**: viewport 900→640, root tracks `#chart` and shrinks, still `ready` (no re-boot).
  - **0 page errors** across all probes; 8 seam keys; `SmcOverlayCore` is an object.
- **Live-stream note**: an 8s console/pageerror capture on a booted chart recorded **zero** messages — the `Cannot update oldest data` warning did **not** reproduce in this environment (the E2E live server pushes no real WS data). The pre-existing live-path race is nonetheless confirmed **not introduced by this change**: `controllers/stream.js` is byte-identical to develop (`git diff` = 0 lines), and no frame in the change touches `updateCandle`/`upsertCandle`.

## Issues Found

**CRITICAL**: None.

**WARNING**:
- **W1 — R22 (keyboard: Enter/Space + arrow focus) has no committed regression test.** The behaviour works (verified by an independent Playwright probe), but nothing in the suite fails if a future edit drops the `keydown` handler or the native button activation. Add one E2E asserting `ArrowRight` focus move + `Enter` activation.
- **W2 — R20 "resize follows the container" has no committed test.** The E2E asserts the initial fill but never resizes the viewport; the ResizeObserver path is proven only by this session's probe. One `set_viewport_size` + root-tracks-`#chart` assertion closes it.
- **W3 — R23 "desktop unchanged (>820px)" and R25 "focus and names" are proven only by static evidence + session probes.** The 375px E2E asserts the *small-screen* branch; desktop (toggle hidden, panel visible) and computed focus outline/accessible names are uncommitted.
- **W4 — Design deviation on the market height scope** (`body:has(.market-layout)` instead of an un-scoped `body{min-height:100dvh}`): strictly better (keeps other pages scrolling), disclosed, breaks no scenario. Recorded for coherence, not a defect.
- **W5 — Workload, not correctness**: Slice 2 diff is ~432 insertions over the 400-line review budget (bulk = 4 planning docs + tests). Pre-flagged by apply; keep as a PR-size note.

**SUGGESTION**:
- `tasks.md` checkboxes remain unmarked (executor contract forbids editing `openspec/**`); the apply-progress artifact is the completion source, consistent with the F0/F1 precedent.
- Reproduce the L2 gate with bare `--cov` (as CI does); passing scoped `--cov=web/market --cov=web/trading` emits relative XML filenames that silently hide changed lines from diff-cover.

## Verdict

**PASS WITH WARNINGS** — every L1 gate is green with fresh exit-0 evidence (81 node / 337 py / 36 E2E / ruff clean / `makemigrations --check` clean / empty requirements, settings and `src/` diffs), the L2 patch gate is a genuine 100% across 26 changed Python lines, all 13 requirements and 43/47 scenarios have passing runtime coverage, and independent Django-client + real-browser probes reproduce the endpoint contract, per-user isolation, full-height `autoSize`, clipped-but-actionable select, chip↔select sync, keyboard activation, 375px no-overflow, collapse toggle and preference restore with **0 page errors** and the frozen 8-key seam intact. Warnings are missing *committed* regression tests for four scenarios proven here by probes, plus a benign height-scoping deviation — no implementation defects.
