# Archive Report: f10-alerts-on-chart

**Archived**: 2026-10-18
**Change**: `f10-alerts-on-chart` (issue #123, Fase F10) — `chart-alerts` (NEW),
`alert-rules`, `market-chart`, `design-system` (MODIFIED)
**Verdict**: `PASS_WITH_WARNINGS` (0 blockers, **2 CRITICALs C1/C2 resolved
in-chain**, 5 warnings, 4 suggestions)
**Delivery**: Feature Branch Chain — S1a **#227** / S1b **#228** / S2 **#229** /
S3 **#230**, fix slice **#231**, polish **P1 #236** / **P2 #237**, then tracker
**#238** → `develop` @ **bdb1255**, merged.
**Base**: `develop` @ `b12c0df`. Verify ran on the tracker tip `088779d`; the fix
and polish slices landed after it.

## What Shipped

Two deliverables on `/market/`, over the frozen alert engine — no migration, no
schema change, no dependency, no CSP relaxation, no `src/` edit.

- **JSON transport** — `web/market/alerts.py` + 2 route entries:
  `GET|POST /market/api/alerts` and `PUT|DELETE /market/api/alerts/<id>`. GET keys
  on `symbol` **and** `interval`, returns `200 {"alerts": []}` for an empty pair and
  400 for a missing/bad key. POST validates in a fixed order (JSON object → symbol
  → `SYMBOLS` → interval → `CANDLE_INTERVALS` → `parse_condition` → real-bool
  `is_active` → str/≤64 `telegram_chat_id`) before any write and returns 201. PUT
  is partial, re-validates `condition` through `parse_condition`, rejects a
  changed `symbol`/`interval` with 400 and a body with no updatable field with 400;
  DELETE returns 204. Every verb resolves through `AlertRule.for_user` (A≠B → 404),
  and the owner is set explicitly on create, never taken from the body.
- **Pure cores** — `alert-markers-core.js` (`stateOf` = the frozen S4 precedence,
  `markersFor`, `summaryOf`), `alert-condition-core.js` (`conditionFrom`,
  `levelFromInput`, `opFor`), `alert-ui-core.js` (interval eligibility, price
  formatter, list URL, bell painter, edit cue, success text, nearest-rule, write
  request shape).
- **Adapters** — `alert-markers-view.js` (the single `createSeriesMarkers` handle,
  token resolution at render time, the `aria-live` summary, the confirm toast) and
  `alert-bell-view.js` (the JS-built `<button>`, its price-scale offset, hover
  plumbing). Both extracted in P2 to keep `controllers/alerts.js` under 300.
- **Controller** — `controllers/alerts.js` (278): crosshair→bell placement, dialog
  seed/apply, 10 px edit detection, marker lifecycle, one `gen` counter to kill an
  in-flight fetch after a switch. Zero `bus.emit`, zero series writes.
- **Markup/CSS** — static `<dialog id="alert-dialog">`, `#alert-status`
  (`aria-live`), `#alert-interval-reason`, `#alert-cue`, `#alert-confirm`
  (`role="status"`), and the `--alert-armed` token in both themes.

| Area | Delivered |
|------|-----------|
| `chart-alerts` | R1 bell (price-anchored, scale-aware offset, keyboard-reachable, context-menu "Add alert" keyboard path seeded from the newest close); R2 price-only dialog (seeded, edit cue, failed Apply re-opens with the error focused, success toast, focus back to `#chart`); R3 eligibility (inert `aria-disabled` + described reason, API 400, `EVALUABLE`↔`CANDLE_INTERVALS` parity test); R4 markers (armed/fired by shape+text+position, off-series dropped, same-level collapse with a count, re-anchor on `candle:closed` and `history:loaded`, token colours + repaint on flip); R5 frozen envelope. |
| `alert-rules` | R10 JSON CRUD (GET/POST/PUT/DELETE, pair-keyed, full 400/404 matrix, CSRF, epoch `last_fired_at`, verbatim `condition`); R11 `for_user` scope on every read/write. R1–R9 unchanged: the model, `parse_condition`, `matches`, edge/dedup, the worker and the HTML form transport are untouched. |
| `market-chart` | R14: 5 new modules (`alert-markers-core`, `alert-condition-core`, `alert-ui-core`, `alert-markers-view`, `alert-bell-view`) + `controllers/alerts`; `MODULE_ALLOWLIST` = **33**, `CONTROLLER_ALLOWLIST` = **17**. R18/R20: seam 8 keys, `STORE_KEYS` 11, no new bus event (reuses `chart:built`/`history:loaded`/`candle:closed`), markers option-only. |
| `design-system` | R6: focusable named bell, `:focus-visible`, inert-but-focusable ineligible state with an announced reason, native dialog focus trap + focus return, `#alert-status` live summary, separate `#alert-confirm` toast, markers not colour-only, tokenized (+`--alert-armed`) so both themes clear AA. R7: CSP-clean, static dialog, JS-built bell, header unchanged. |

| Area | Held |
|------|------|
| Size ceiling | `test_module_size_guard.py` green, EMPTY allowlist, 51 modules scanned, none over. `smc.js` = 300 (pre-existing, byte-untouched). |
| Seams held | `window.marketChart` exactly 8 keys, `STORE_KEYS` exactly 11, no new `EVENTS` member, `smc.js`/`chart-bus.js`/`chart-host.js`/`chart-store.js` byte-untouched, #68 (no `setData`/`update`), no migration, no new dependency, CSP unchanged. |
| Read-only | no order/execution path, SMC internals unchanged. |

## Premise Correction (carried into the canonical specs)

The issue asked to "reuse the existing CRUD". There was **no JSON API to reuse**:
the only alert CRUD was Django HTML form views (`web/trading/urls.py:13-17` →
`views.py:205-258`) returning `render`/`redirect`, while the chart is an ESM app
that speaks JSON (`chart.js:24-34`); navigating away destroys the page-scoped
store/bus/host (`main.js:52-68`). F10 therefore **added** the JSON transport.

What was genuinely reused: the engine `parse_condition`
(`src/alert_rules.py:108-119`), the `AlertRule` model + `for_user`
(`trading/models.py:288-304`), the S4 state precedence (`market/views.py:104-116`),
the `api_drawings` CRUD shape, the `X-CSRFToken` convention, and the existing
`chart:built`/`history:loaded`/`candle:closed` bus events. The HTML form transport
and the engine semantics are **unchanged**, so `/rules/` behaves exactly as before.

## Requirements Satisfied

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-alerts | R1–R5 (NEW) | ✅ Delivered; all five verify gaps closed in-chain (see below). |
| alert-rules | R10/R11 (ADDED) | ✅ 45 API tests: auth 302 ×4, CSRF 403 ×3, the full 400 matrix with `count()==0`, PUT immutability, 404 on miss/foreign, 204 on delete, epoch round-trip, A≠B. R1–R9 preserved. |
| market-chart | R14/R18/R20 (MODIFIED) | ✅ Inventory and allowlists reconciled to the delivered **33** / **17**; seam 8, store 11, no new event, markers option-only. R1–R13, R15–R17, R19, R21–R23 preserved. |
| design-system | R6/R7 (MODIFIED) | ✅ Bell/dialog a11y as delivered (inert ≠ `disabled`), live summary + separate toast, shape+text+position markers, tokenized colours in both themes, CSP-clean. R1–R5, R8–R10 preserved. |

**Compliance summary at verify**: 69/75 scenarios fully compliant, 4 PARTIAL, 2
MISSING/DEVIATING (C1/C2). All 6 are resolved below; the canonical specs record
the delivered state.

**Preserved untouched** (no requirement dropped):
- `alert-rules`: R1–R9.
- `market-chart`: R1–R13, R15–R17, R19, R21–R23.
- `design-system`: R1–R5, R8–R10.

## Verify Findings Carried and Remediation

- **C1 — `chart-alerts` R4 "Off-series anchor is dropped" was not implemented.** The
  core kept `last_fired_at` for any finite value and the design had explicitly
  chosen "fall back to `anchorTime`, never drop". Spec and design disagreed and the
  code followed the design. **Fixed in #231** (`0467a63`): an off-series or
  non-finite `last_fired_at` now yields no marker (never a fabricated time), with a
  non-vacuous node test; the fired state stays visible on `/signals/`. The
  canonical R4 settles the question in the spec's favour.
- **C2 — `chart-alerts` R1 / `design-system` R6 "Bell is keyboard reachable" had no
  covering test.** **Fixed in #231**: `alerts-controller.test.js::bell is a
  keyboard-reachable native button (R1)` pins `<button type="button">` and its
  Enter/Space activation path.
- **W1 — `MODULE_ALLOWLIST` was 31, not the 30 the delta stated.** The delta said
  `28→30` with two cores; S3 extracted `alert-ui-core` and P2 extracted
  `alert-markers-view`/`alert-bell-view`, so the delivered count is **33**.
  Reconciled in canonical R14 with a reconciliation note.
- **W2 — no explicit `setData`/`update` spy for an alert render.** The controller's
  series stub exposes only `coordinateToPrice`/`priceToCoordinate` (a write would
  throw) and `alerts.js` contains no writer; the canonical R20 scenario now states
  the delivered proof plus the option-only contract. **Accepted as-is** — the
  throwing stub is the stronger proof.
- **W3 — session expiry (302 → login) shows "Network error".** Diverges from the
  design flow but breaks no spec requirement; **carried as a known state**, not
  fixed here.
- **W4 — `EVALUABLE` duplicated `CANDLE_INTERVALS` with no parity test.** **Fixed in
  #231**: `alert-ui-core.test.js` asserts the eight intervals and no `1m`, so a
  server-side drift fails loudly.
- **S1 — `tasks.md` all unticked.** Closed by this archive reconciliation.
- **S2 — the non-evaluable list omitted `30m`.** Canonical R3 now enumerates
  `1m/30m/3d/6h/8h/12h` and states the rule is "every interval outside
  `CANDLE_INTERVALS`".
- **S3 — bell placement is price-anchored with a fixed horizontal offset**, not the
  design's `{x,y}`: an x that tracks the cursor cannot be clicked. Canonical R1
  records the delivered behavior (price position + price-scale-width offset).
- **S4 — less headroom than the design estimated.** `alerts.js` = 278 (not 218),
  `main.js` = 293 (not 280); both under the empty-allowlist ceiling.

## `/impeccable works-needs-polish` → P1/P2 Remediation

The `/impeccable` review returned **works-needs-polish** with four issues; all four
were fixed in two polish PRs into the tracker:

**P1 (#236)**
- **#232** `a25e61c` — marker colours were frozen literals (fired 3.49:1 on white,
  armed 3.86:1 on dark) and a theme flip is option-only, so they went stale. The
  controller now resolves `--alert-armed`/`--dn` at render time and `main`'s
  `onTheme` calls `refreshTheme()`; a new `--alert-armed` token clears 4.5:1 in both
  palettes (5.90 dark / 5.19 light) with a computed-contrast test.
- **#233** `0920580` — Apply runs in the dialog's `close` handler, so a `400` or a
  network failure wrote into an already-closed dialog. Every failure now re-opens
  it with the message visible, keeps the typed level and focuses the input.
- **#235** `ed4760d` — the bell needs a pointer-produced crosshair, so a Tab user
  could never create an alert. The empty-chart context menu (openable with
  `Shift+F10`/the `ContextMenu` key) now offers "Add alert", seeded from the newest
  close, travelling an injected callback (the `onIndicatorSettings` precedent) —
  no new bus event.

**P2 (#237)**
- **#234** `7afe370` + `ee645af` — bell offset by the measured price-scale width
  (44 px target on coarse pointers); the ineligible bell is `aria-disabled`
  (focusable, so the reason is actually announced) instead of `disabled`; a
  deferred crosshair clear hides a stale bell on pointerleave; the dialog names the
  alert a near rule would PUT; a visible `#alert-confirm` toast reports the
  armed/updated level; armed markers re-anchor on `candle:closed`; and same-level
  armed markers collapse to one counted label (`A 100×3`).

## Follow-up Issues

| Issue | Slice / PR | Fix |
|-------|-----------|-----|
| #232 | P1 · PR #236 | marker colours from tokens + repaint on theme flip |
| #233 | P1 · PR #236 | failed Apply re-opens the dialog |
| #234 | P2 · PR #237 | bell offset, inert semantics, stale-hide, edit cue, success toast, candle-close re-anchor, marker collapse |
| #235 | P1 · PR #236 | keyboard "Add alert" path from the context menu |
| C1 / C2 / W4 | verify fix · PR #231 | off-series marker dropped + test; bell keyboard contract pinned; interval parity test |

All four filed follow-up issues (#232–#235) are **closed**; the three verify fixes
landed in #231 under one commit without their own issue numbers.

## Final Invariant State (verified on develop @ bdb1255)

| Invariant | Proof | Result |
|---|---|---|
| `window.marketChart` EXACTLY 8 keys | `main.js` still exposes the same shape; E2E asserts `Object.keys(...).length === 8` twice in the F10 E2E plus `test_shell_keeps_seam_at_eight_keys` | ✅ |
| `STORE_KEYS` EXACTLY 11 | `chart-store.js` byte-untouched; `chart-store.test.js` deep-equals the 11 keys | ✅ |
| Every `market/**/*.js` ≤300, empty allowlist | `test_module_size_guard.py` 3 passed; 51 modules scanned, `over={}`, max `smc.js` 300 | ✅ |
| `MODULE_ALLOWLIST` = **33** (incl. the 5 alert modules) | `views.py:44-75`; `test_f10_alerts_are_served` asserts 33 and serves each 200 | ✅ |
| `CONTROLLER_ALLOWLIST` = **17** (incl. `alerts`) | `views.py:76-95`; `test_market_ux.py:146,195` | ✅ |
| No new `EVENTS` member | `chart-bus.js` byte-untouched; `alerts.js` has zero `bus.emit` | ✅ |
| #68: markers option-only | `alerts.js` has no `setData`/`update`; marker view uses `createSeriesMarkers`/`setMarkers`; the controller test's series stub has no writer | ✅ |
| `smc.js` byte-untouched | `git diff --exit-code` clean; two tests assert no `alert` token in it | ✅ |
| R14 `for_user` everywhere; A≠B → 404 | `alerts.py` — all query sites use `AlertRule.for_user`; A≠B PUT/DELETE 404, GET `[]` | ✅ |
| No migration / no schema change | `makemigrations --check` → `No changes detected` | ✅ |
| CSP / `requirements.txt` / `src/` unchanged | `middleware.py` untouched; `test_csp_present_on_market_page`; `git diff` empty | ✅ |

**Module sizes (delivered)**: `smc.js` **300** (pre-existing, byte-untouched),
`main.js` 293, `drawing-interaction.js` 291, `drawing-interaction-core.js` 285,
`drawing-tools-core.js` 284, `drawings.js` 282, **`controllers/alerts.js` 278**,
`chart-host.js` 267, `object-tree.js` 263, `alert-ui-core.js` 131,
`alert-markers-core.js` 118, `alert-markers-view.js` 71, `alert-bell-view.js` 49,
`alert-condition-core.js` 44. Every module is under the empty-allowlist ceiling.

**Test gates**: `node --test` **598/598** (F10 alert files 73/73); pytest suite
**1123 passed** at verify plus the P1/P2 additions; F10 API **45/45**; F10 E2E
**4/4**; market E2E **101/101**; ruff check/format clean; `diff-cover` 100% on
`web/market/alerts.py`. Re-run at archive: `node --test` 598 pass / 0 fail,
`test_module_size_guard.py` and `test_market_ux.py` + `test_market_alerts_api.py`
green.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-alerts | **Created** | Full canonical spec (no prior): R1–R5 with 17 scenarios — bell/scale offset/keyboard path, dialog seed+edit cue+failed-Apply re-open+toast, eligibility (inert `aria-disabled`, `30m` added, parity test), markers (drop off-series, collapse same-level, token repaint, candle-close re-anchor), frozen envelope. |
| alert-rules | Updated | +R10 (JSON CRUD, validation order, 11 scenarios) +R11 (`for_user` scope, 4 scenarios). R1–R9 preserved untouched. |
| market-chart | Updated | R14 (5 alert modules + `alerts` controller, `MODULE_ALLOWLIST`=33, `CONTROLLER_ALLOWLIST`=17, reconciliation note, 3 scenarios updated), R18 (alert seam clause + scenario), R20 (alert envelope clause, `alert:*` absent, `STORE_KEYS` 11, alert option-only scenario). R1–R13, R15–R17, R19, R21–R23 preserved. |
| design-system | Updated | R6 (F10 bell/dialog/toast/marker clauses + 6 scenarios), R7 (F10 CSP clause + scenario). R1–R5, R8–R10 preserved. |

Every MODIFIED requirement was matched by name and replaced in place; no
requirement was dropped.

## Rollback (per-slice, independently revertible)

- **P2 (#237)**: revert — bell loses the axis offset and inert semantics, the edit
  cue/toast/candle-close re-anchor go, same-level markers stack again; the two
  adapter modules are deleted and `alerts.js` regains its inline helpers.
- **P1 (#236)**: revert — marker colours fall back to the core literals (light-theme
  contrast regresses), a failed Apply is silent again, and the keyboard alert path
  disappears.
- **#231**: revert — off-series fired markers would be placed at `last_fired_at`
  again and the bell keyboard/interval-parity tests vanish.
- **S3 (#230)**: revert — controller, dialog, CSS, `chart.js` url, `main.js` wiring
  and the allowlist names; S1's data stays readable on `/rules/`.
- **S2 (#229)**: revert — the two pure cores are deleted; nothing imports them.
- **S1a/S1b (#227/#228)**: revert — `alerts.py` and the 2 routes go; `AlertRule`
  rows and `/rules/` are unaffected (no migration).
- **Tracker (#238)**: drop the branch; nothing reached `main`.

## Known State / Fragility

- `controllers/smc.js` = **300** — at the ceiling, PRE-EXISTING and byte-untouched;
  one edit away from tripping the empty-allowlist guard.
- `main.js` = 293 (7 lines under) and `alerts.js` = 278 (22 under) — the tightest
  F10-touched modules.
- Fired markers are a snapshot: `last_fired_at` is written only by the worker, so
  the chart does not poll; the copy says "when the candle close goes above X", never
  "crosses" or "live".
- Session expiry still surfaces as "Network error — the alert was not saved"
  (verify W3) rather than a redirect; no requirement is broken.
- The `EVALUABLE` list is a JS mirror of the Python `CANDLE_INTERVALS`; the parity
  test is the only thing keeping them aligned.
- Issue #123 is still **OPEN** on the tracker; the PR chain is merged and #232–#235
  are closed.

## Bookkeeping

`tasks.md` checkboxes were reconciled to `[x]` at archive (the apply contract
forbids editing `openspec/**` during apply), with a header note recording the fix
slice (#231), the P1/P2 polish slices (#236/#237), the two extra modules beyond
the plan, and the final `33`/`17` allowlist counts. The change directory was
UNTRACKED before this commit; the canonical spec edits, the `tasks.md` update,
this archive report, and the archive move are committed together. `cov.xml` is
gitignored and was not added.
