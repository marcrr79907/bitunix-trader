# Tasks: f10-alerts-on-chart (issue #123, Fase F10)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

> **Normative-id note.** Where `design.md` names `#alert-summary` and "focus returns
> to the bell", the specs win: `#alert-status[aria-live="polite"]`
> (`specs/design-system/spec.md:77-81`, `specs/market-chart/spec.md:149-153`) and
> focus returns to `#chart` on Cancel/`Escape`
> (`specs/design-system/spec.md:71-75`, `specs/chart-alerts/spec.md:67-71`).

> **Archive reconciliation (2026-10-18).** All boxes are `[x]` against the
> DELIVERED chain, not the plan. Beyond the three planned slices the delivery
> carried a fix slice and two polish slices: **#231** (verify C1/C2 — off-series
> fired markers now dropped, bell keyboard contract pinned, `EVALUABLE` ↔
> `CANDLE_INTERVALS` parity test), **P1 #236** (#232 theme-token marker colours +
> repaint on flip, #233 failed Apply re-opens the dialog, #235 keyboard "Add
> alert" path from the context menu) and **P2 #237** (#234 bell offset/inert
> semantics/stale-hide/edit cue/success toast/candle-close re-anchor, same-level
> armed markers collapsed with a count). Two consequences for the plan: the
> delivered `MODULE_ALLOWLIST` is **33** (not 30) because S3's ceiling extraction
> added `alert-ui-core` and P2 added `alert-markers-view`/`alert-bell-view`; and
> `CONTROLLER_ALLOWLIST` is **17** as planned. `alerts.js` ends at 278 lines.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | S1 ~560, S2 ~310, S3 ~375 → **~1245** |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (JSON API `alerts.py` + 2 routes + API/parity tests) → PR2 (2 pure cores + node tests) → PR3 (`controllers/alerts.js` + dialog/CSS + `chart.js`/`main.js` wiring + allowlists + UX/E2E) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base / boundary |
|------|------|-----------|-----------------|
| S1 | JSON CRUD `/market/api/alerts` (+`/<id>`) over frozen `parse_condition`/`AlertRule`, `for_user` scoped, full 400/404 matrix | PR 1 | base = tracker `feat/f10-alerts-on-chart` |
| S2 | `alert-markers-core.js` (~62) + `alert-condition-core.js` (~46) + node tests; pure, unimported, zero app impact | PR 2 | base = tracker `feat/f10-alerts-on-chart`; merge S1→tracker first |
| S3 | `controllers/alerts.js` (~218) → bell, dialog, markers; `<dialog>`, bell CSS, `chart.js` url, `main.js` +6, allowlists, UX/E2E | PR 3 | base = tracker; merge S2→tracker first; S3 needs S1+S2 |

All PRs base on the tracker; merge each slice to the tracker before branching the
next. Only the tracker merges to `develop`; `main` untouched. S1 alone ≈560 > 400 →
if `test_market_alerts_api.py` exceeds ~350 lines, split S1 into **S1a** (GET + route
+ auth/CSRF) and **S1b** (POST/PUT/DELETE matrix). S3 ≈375 stays one PR.

## Guard / Edge Matrix

- [x] **300-line ceiling, `smc.js`=300 BYTE-UNTOUCHED**: `git diff --exit-code -- web/market/templates/market/controllers/smc.js` per slice; `tests/web/test_module_size_guard.py` (CEILING=300, empty ALLOWLIST) green; `tests/web/test_market_ux.py` asserts `b"alert"` absent from the served `smc.js`. Markers live in `alerts.js` only.
- [x] **`window.marketChart` 8-key freeze**: no 9th key; asserted by `test_shell_keeps_seam_at_eight_keys` + `len(keys)==8` (`main.js:59-68`).
- [x] **`STORE_KEYS` 11 freeze**: no new key; bell/dialog/marker state in the controller closure (`chart-store.js:13-27`, `tests/js/chart-store.test.js`).
- [x] **#68 single write path**: markers via `createSeriesMarkers`/`setMarkers` only (`smc.js:235-238,270` precedent); no `setData`/`update`; spies green in `chart-host.test.js` + E2E.
- [x] **R14 `for_user`**: GET/PUT/DELETE scoped via `AlertRule.for_user` (`models.py:300-303`); A≠B → 404 (PUT/DELETE) and `[]` (GET); `user=request.user` on create. Asserted in `test_market_alerts_api.py`.
- [x] **API 400/404 matrix**: missing symbol, missing `interval`, `interval ∉ CANDLE_INTERVALS`, bad `condition` via `parse_condition`, non-bool `is_active` (real-bool check, `quotes.py:445-453` discipline), non-str/over-64 `telegram_chat_id`; PUT differing `symbol`/`interval` → 400 row untouched; miss/foreign id → 404. One test per row of `design.md:361-378`.
- [x] **Interval eligibility**: bell `disabled` + `aria-describedby="alert-interval-reason"` on `1m/3d/6h/8h/12h`; API 400 on the same set (both derive from `CANDLE_INTERVALS`, `candles.py:30`).
- [x] **Marker anchors**: fired → `rule.last_fired_at` (epoch seconds); armed → newest `host.getCandles()` time; off-series → dropped, never synthetic; bad `anchorTime` → `[]`. Asserted in `alert-markers-core.test.js`.
- [x] **CSP**: static `<dialog>` markup + JS-built bell (`createElement`/`setAttribute`, `context-menu.js:113-139` precedent); no inline `<script>`/`on*`; header unchanged (`middleware.py:29-33`); `test_market_ux.py` scan green.
- [x] **E2E readiness gate**: `_wait_ready`/`window.marketChart.ready`; DOM + captured requests only, no pixels (#149).
- [x] **Patch coverage 100%** on new Python (`alerts.py`): `diff-cover` vs `origin/develop`.
- [x] **Allowlists**: `MODULE_ALLOWLIST` 28→**30** (`views.py:44`), `CONTROLLER_ALLOWLIST` 16→**17** (`views.py:76`); `test_market_ux.py:146,195` `== 16`→`== 17` in the same commit; `test_f10_alerts_are_served` covers 2 cores + `alerts`.

## Phase 1 — S1: JSON API + routes + API tests (PR1)

Base tracker; branch `feat/f10-alerts-on-chart-s1`; deps none. Rollback: revert branch → delete `alerts.py` + 2 routes; `AlertRule` rows and `/rules/` unaffected (no migration).

- [x] 1.1 **RED** NEW `tests/web/test_market_alerts_api.py` (mirror `test_market_api.py:1243-1640`): auth 302 ×4, CSRF 403 ×3, GET matrix (missing symbol/interval, bad interval, `[]` never 404, A≠B → `[]`), POST 400 matrix + `count()==0`, POST valid → 201 + round-trip, PUT partial, PUT immutable symbol/interval, PUT/DELETE 404, DELETE 204, `last_fired_at` null/int. Acceptance: red before 1.2.
- [x] 1.2 **GREEN** NEW `web/market/alerts.py` (~150): `_row`, `_read_body` (+`_BadBody`), `_parse_pair`, `_parse_optional`, `api_alerts` (GET/POST), `api_alert_detail` (PUT/DELETE) — validation order exactly `design.md:165-177`, steps 1-5 before any write. Acceptance: 1.1 green.
- [x] 1.3 **GREEN** `web/market/urls.py:9-37` +2 `path(...)` entries (`market_api_alerts`, `market_api_alert_detail`), import from `market import alerts`. Acceptance: routes resolve; 1.1 green.
- [x] 1.4 **GREEN-parity** `tests/test_alert_rules.py`: a bell-shaped `{type:"price",op:"above",level:X}` is accepted by `parse_condition` and yields an edge (`edge_fired`) — expected green, it pins parity (`alert_rules.py:108-119,159-165`).
- [x] 1.5 **REFACTOR** `.venv/bin/python -m pytest -p no:randomly` green; `diff-cover` vs `origin/develop` → 100% on `alerts.py`; `ruff` clean. Acceptance: chain green.

## Phase 2 — S2: pure cores + node tests (PR2)

Base tracker (S1 merged); branch `feat/f10-alerts-on-chart-s2`; deps none. Rollback: delete 2 files; unimported, no allowlist yet.

- [x] 2.1 **RED** NEW `tests/js/alert-markers-core.test.js`: `stateOf` precedence fired>armed>inactive (+ non-object → inactive); fired anchor = `last_fired_at`, armed = `anchorTime`; inactive omitted; off-series/non-finite fallback; `rules` non-array → `[]`; deep-equal marker arrays incl. distinct `shape` + `text` "A"/"F" (mirror `smc-overlay-core.test.js:243-282`). Acceptance: red before 2.2.
- [x] 2.2 **GREEN** NEW `web/market/templates/market/alert-markers-core.js` (~62, zero imports): `COLORS`, `stateOf`, `markersFor` per `design.md:271-309`. Acceptance: 2.1 green; `wc -l` ≤300; no mutation.
- [x] 2.3 **RED** NEW `tests/js/alert-condition-core.test.js`: `levelFromInput` rejects `""`/`"abc"`/`0`/`-1`/`Infinity`, accepts `"50000,5"`; `conditionFrom` op whitelist + fresh object + null on bad level; `opFor` above/below boundary + unknown close → above. Acceptance: red before 2.4.
- [x] 2.4 **GREEN** NEW `web/market/templates/market/alert-condition-core.js` (~46, zero imports): `conditionFrom`, `levelFromInput`, `opFor` per `design.md:311-328`. Acceptance: 2.3 green; ≤300.
- [x] 2.5 **REFACTOR** `node --test "tests/js/**/*.test.js"` green; size guard green (empty allowlist). Acceptance: chain green.

## Phase 3 — S3: controller + dialog + wiring + allowlists + E2E (PR3)

Base tracker (S2 merged); branch `feat/f10-alerts-on-chart-s3`; deps S1+S2. Rollback: revert branch; delete controller, `<dialog>`, CSS, wiring, allowlist names; S1 data still readable on `/rules/`.

- [x] 3.1 **RED** `tests/web/test_market_ux.py`: allowlist `== 16`→`== 17` (`:146,:195`), `test_f10_alerts_are_served` (2 cores + controller 200 JS), 2 new `modulepreload`s, `#alert-dialog` present, no inline handler, served `smc.js` has no `alert` token. Acceptance: red before 3.2-3.5.
- [x] 3.2 **RED** NEW `tests/web/test_market_alert_e2e.py` (`_wait_ready` gated): bell visible with price name; bell click → dialog → captured POST body `{type:"price",op,level}`; PUT when near an existing rule (no duplicate); Cancel/Escape → no request + focus `#chart`; `#alert-status` summary; interval switch → one GET for the new pair + old markers cleared; bell disabled on `1m`; 8-key seam. Acceptance: red before 3.3-3.7.
- [x] 3.3 **GREEN** NEW `web/market/templates/market/controllers/alerts.js` (~218): `createAlerts({store,bus,host,config})` → `{attach,refresh,clearForSwitch}`; bell built with `createElement`, crosshair subscription inside `bus.on("chart:built")`; dialog seed + `conditionFrom`/`levelFromInput`/`opFor`; own `createSeriesMarkers` handle; 10 px edit detection; `#alert-status` announcement. Acceptance: 3.1/3.2 green.
- [x] 3.4 **GREEN** `web/market/templates/market/chart.html` +~14: static `<dialog id="alert-dialog">` with `<form method="dialog">`, `#alert-status` live node, `#alert-interval-reason` visually-hidden, 2 `modulepreload` lines (chart-alerts R2/R4, design-system R6/R7).
- [x] 3.5 **GREEN** `web/market/views.py:44,76`: `MODULE_ALLOWLIST` +`alert-markers-core`,`alert-condition-core` (28→30); `CONTROLLER_ALLOWLIST` +`alerts` (16→17). Acceptance: served 200; no 404.
- [x] 3.6 **GREEN** `web/market/templates/market/chart.js:28-34` +`alerts: "/market/api/alerts"`; `web/market/templates/market/main.js` +6 (import, `createAlerts`, `attach()` in `buildChart:120-142`, `clearForSwitch()` + `refresh()` in `switchTo:162-199`, `refresh()` in `start():229-274`) — ends ≤280.
- [x] 3.7 **GREEN** `web/accounts/templates/registration/theme.css` +~12: `.chart-alert-bell` absolute in `#chart`, clamped, `:focus-visible`; dialog rows.
- [x] 3.8 **REFACTOR** `node --test`/`pytest`/`ruff` green; guard green; seam 8 + store 11; `smc.js` `git diff --exit-code`; E2E DOM+network only. Acceptance: chain green.

## Verification

- [x] V.1 `node --test "tests/js/**/*.test.js"` green.
- [x] V.2 `.venv/bin/python -m pytest -p no:randomly` green; `diff-cover` vs `origin/develop` → 100% patch on `alerts.py`.
- [x] V.3 `.venv/bin/ruff check . && .venv/bin/ruff format --check .` clean.
- [x] V.4 `.venv/bin/python web/manage.py makemigrations --check --dry-run` clean (no model change expected).
- [x] V.5 `wc -l` each new module ≤300; `git diff --exit-code -- web/market/templates/market/controllers/smc.js`; `test_module_size_guard.py` green.
- [x] V.6 Seam 8 keys, `STORE_KEYS` 11, no new `EVENTS` member, CSP + `requirements.txt` + `src/` unchanged.
- [x] V.7 E2E readiness-gated, DOM + captured requests only (no pixels); `test_alert_rule_crud.py` unedited and green.

## Rollback

- **S1**: revert the S1 commits → `alerts.py` gone, 2 routes gone; no migration, `AlertRule` rows stay valid on `/rules/`.
- **S2**: revert the S2 commits → 2 core files deleted; nothing imported them yet.
- **S3**: revert the S3 commits → controller/`<dialog>`/CSS/`chart.js`/`main.js` wiring and the 3 allowlist names reverted; S1 data remains readable.
- **Tracker**: drop `feat/f10-alerts-on-chart` and every slice; nothing reaches `develop`, `main` untouched.
