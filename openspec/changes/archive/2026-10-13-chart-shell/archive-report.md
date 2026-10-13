# Archive Report: chart-shell

**Archived**: 2026-10-13
**Verdict**: `pass_with_warnings` (0 blockers, 0 critical, 13/13 requirements, 43/47 scenarios compliant, 4 partial) — new `chart-shell` capability (R20–R25, 6 requirements) + `chart-config` additions (R8–R11: `ChartPreference` + preference endpoint) + `per-user-isolation` update (`ChartPreference` added to the owned-model contract) + `market-chart` R20 (frozen host/seam envelope)
**Delivery**: 2-slice Feature Branch Chain — PR #133 (shell: template/CSS/chips/collapse/`autoSize`) → #134 (interval persistence: model + migration `0009` + endpoint + boot read/save), all slices base on tracker `feat/chart-shell`; tracker merged to `develop` via PR #135
**Issue**: #116 (Fase F3 — Ola 1)
**Branch**: `feat/chart-shell-persistence` (HEAD `1cb54d0`); Slice 1 `bd081cf` (`feat/chart-shell-shell`, merged `47f021c`); chain all→tracker

## What Shipped

Fase F3 — the visible shell around the merged F0/F1 chart, plus last-interval
persistence. HTML/CSS + small controller JS; no `src/` change, no new dependency,
CSP unchanged, `window.marketChart` stays 8 keys, `SmcOverlayCore` untouched.

| Area | Delivered |
|------|-----------|
| Full-height chart | `chart-host.js` `build()` uses `autoSize:true` (v5 ResizeObserver); fixed `height:480` removed; `#chart` resolves via a `dvh`/flex chain (`body:has(.market-layout){height:100dvh}` + `main{flex:1;min-height:0}` + `.market-layout{height:100%}`) |
| Interval chips | `role="group"` of `button.interval-chip[data-interval][aria-pressed]` rendered from `select.options` (no 4th interval copy); `controller/toolbar.js` bidirectional chip↔select sync, each path emits exactly one `config:changed` |
| Hidden select | `<select id="interval">` retained in DOM, clipped via `.visually-hidden` (`clip:rect(0 0 0 0)` — never `display:none`/`hidden`) so the 15 E2E `select_option` calls stay actionable |
| Collapsible sidebar | `<button class="panel-toggle" aria-expanded aria-controls="panel">` toggles `.panel-collapsed` + `aria-expanded` at ≤820px; desktop keeps the panel always visible with the toggle hidden |
| Keyboard | Native `<button>` chips: Enter/Space activate; ArrowLeft/Right move focus across the group |
| Preference model | `ChartPreference(UserOwnedModel)`: `OneToOneField(user, related_name="chart_preference", CASCADE)`, `last_interval CharField(8, default="1m")`, `updated_at auto_now` |
| Migration | `web/trading/migrations/0009_chartpreference.py` — single additive `CreateModel` (depends on `0008_alertrule_telegram`); `makemigrations --check` clean |
| Endpoint | `GET`/`PUT /market/api/preference`, `@login_required` + `@require_http_methods(["GET","PUT"])`; PUT validates against `INTERVALS` before write; GET miss → `{interval:"1m", exists:false}` (never 404); route added without altering existing routes |
| Boot persistence | `main.js` `loadPreference()` before `start()` (fallback `"1m"`, non-blocking, `gen` guard intact); debounced (500ms) `savePreference` on genuine interval change, mirroring `saveLayout` |
| a11y | Global `:focus-visible{outline:2px solid}`; chips carry `aria-pressed` (state not color-only); accessible names `1m`/`Interval`/`Panel`; no inline script/handler |
| Tests | `tests/web/test_market_api.py` (+12 preference), `test_isolation.py` (+5), `test_owned_model_guard.py` (+2), `test_market_e2e.py` (7 shell + 3 preference) |

## Verify Findings

Verdict `pass_with_warnings` (verify-report.md). L1: `node --test "tests/js/**/*.test.js"`
**81 passed, 0 fail**; `pytest -m e2e -p no:randomly` **36 passed** (33 baseline + 3
new preference); `pytest tests/ --ignore=tests/web` **337 passed**; `ruff check .`
+ `ruff format --check .` clean (134 files); `makemigrations --check --dry-run`
"No changes detected"; `manage.py check` no issues; `requirements.txt`, settings
(CSP) and `src/` diffs vs develop empty. L2: `diff-cover coverage.xml
--compare-branch=feat/chart-shell --fail-under=100` → exit 0, **100%** across 26
changed Python lines (0 missing). Full change diff = 22 files, +1794/−34 (bulk =
the four planning docs + tests); Slice 2 vs tracker = 10 files, +432/−21. L3 spec
conformance: all 13 requirements / 43 of 47 scenarios have passing runtime
coverage; independent Django-client and real-browser Playwright probes reproduced
the endpoint contract, per-user isolation, full-height `autoSize`, clipped-but-
actionable select, chip↔select sync, keyboard activation, 375px no-overflow,
collapse toggle and preference restore with **0 page errors** and the frozen
8-key seam intact.

### Warnings carried (non-blocking)

- **W1 — R22 (keyboard: Enter/Space + arrow focus) has no committed regression test.** Behaviour works (verified by an independent Playwright probe), but nothing in the suite fails if a future edit drops the `keydown` handler or native button activation. Add one E2E asserting `ArrowRight` focus move + `Enter` activation.
- **W2 — R20 "resize follows the container" has no committed test.** The E2E asserts the initial fill but never resizes the viewport; the ResizeObserver path is proven only by a session probe. One `set_viewport_size` + root-tracks-`#chart` assertion closes it.
- **W3 — R23 "desktop unchanged (>820px)" and R25 "focus and names" are proven only by static evidence + session probes.** The 375px E2E asserts the small-screen branch; desktop (toggle hidden, panel visible) and computed focus outline/accessible names are uncommitted.
- **W4 — Design deviation on the market height scope (benign).** Implementation scopes the definite height with `body:has(.market-layout){height:100dvh}` (keeping `min-height:100dvh` globally) instead of the design's un-scoped `body{min-height:100dvh}`. Strictly better: non-market pages keep normal page scroll. Disclosed; breaks no scenario.
- **W5 — Workload, not correctness.** Slice 2 diff is ~432 insertions over the 400-line review budget (bulk = 4 planning docs + tests). Pre-flagged by apply; kept as a PR-size note.
- **Pre-existing live-stream `Cannot update oldest data` race — NOT introduced by this change.** `controllers/stream.js` is byte-identical to develop (`git diff` = 0 lines) and no frame touches `updateCandle`/`upsertCandle`; the 8s console capture recorded zero messages in this environment. Recorded for continuity, not a defect of F3.

### Topology note (durable lesson)

All slice PRs base on the tracker branch `feat/chart-shell`: PR #133
(`feat/chart-shell-shell`, `bd081cf`, merged `47f021c`) then #134
(`feat/chart-shell-persistence`, `1cb54d0`), then tracker → `develop` via PR #135.
**Durable lesson (reconfirmed): merge each slice into the tracker BEFORE
branching the next; never chain slice-to-slice.** The all→tracker topology keeps
every child diff clean against the tracker.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-shell | R20 — Full-height chart (autoSize + resolved container) | ✅ `autoSize:true`, no numeric height; canvas 623px > 480, tracks `#chart`; resize scenario probe-only (**W2**) |
| chart-shell | R21 — Interval chips preserve hidden select + command | ✅ 14 chips from `options`; select clipped & actionable; one `config:changed` per path; `aria-pressed` sync |
| chart-shell | R22 — Keyboard-operable chips | ⚠️ holds (Playwright probe: Arrow focus + Enter/Space activation); no committed test (**W1**) |
| chart-shell | R23 — Collapsible sidebar ≤820px | ✅ 375px toggle collapses/expands + `aria-expanded`; desktop branch probe-only (**W3**) |
| chart-shell | R24 — 375px no horizontal overflow | ✅ `scrollWidth <= clientWidth+1`; chip row `flex-wrap`; single-column grid |
| chart-shell | R25 — Accessibility, CSP, no new dependency | ✅ focus outline + accessible names (probe, **W3**); CSP + `requirements.txt` unchanged |
| chart-config | R8 — User-global interval preference model | ✅ `ChartPreference` OneToOne + additive `0009`; one row/user; round-trip |
| chart-config | R9 — Preference API | ✅ GET default on miss; PUT→GET round-trip; invalid → 400 no write; anon → 302; CSRF-protected |
| chart-config | R10 — Boot restore and save on change | ✅ persisted interval restores; fetch failure → `1m` + non-blocking; one debounced PUT on change |
| chart-config | R11 — Per-user isolation + CSP | ✅ `for_user`-scoped GET/PUT; A≠B GET/PUT isolated; CSP unchanged |
| per-user-isolation | R14.2 — Cross-user read denied (modified) | ✅ `ChartPreference` added to the delivered set; cross-user get raises `DoesNotExist` |
| per-user-isolation | R14.3 — Unscoped-query guard (modified) | ✅ `ChartPreference` added to `OWNED_MODELS`; scanner flags unscoped query |
| market-chart | R20 — Shell change inside the frozen host/seam envelope | ✅ 8 keys intact; no new bus event/module; 15 `select_option` E2E calls unchanged |

R1–R7 (chart-config), R14.1/R14.4/R14.5 (per-user-isolation) and R1–R19
(market-chart) preserved untouched.

## Gates

`node --test "tests/js/**/*.test.js"` 81 passed; E2E `-m e2e -p no:randomly` 36
passed; `pytest tests/ --ignore=tests/web` 337 passed; `ruff check` + `ruff format
--check` clean (134 files); `makemigrations --check --dry-run` "No changes
detected"; `manage.py check` no issues; `diff-cover --fail-under=100` 100% (26
changed Python lines); `requirements.txt`, settings (CSP) and `src/` diffs empty;
`window.marketChart` 8 keys; `stream.js` byte-identical to develop.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-shell | Created | New canonical spec from the change delta — R20–R25 (6 requirements, 16 scenarios) + non-applicable domains |
| chart-config | Updated | R8–R11 appended (4 requirements, 15 scenarios: `ChartPreference` model, `/market/api/preference`, boot restore/save, isolation+CSP). R1–R7 preserved untouched |
| per-user-isolation | Updated | R14.2 delivered set + R14.3 `OWNED_MODELS` gain `ChartPreference`; new `A cannot read B's ChartPreference` and `Scanner flags an unscoped ChartPreference query` scenarios. R14.1/R14.4/R14.5 preserved untouched |
| market-chart | Updated | R20 appended (frozen host/seam envelope; +1 requirement / 3 scenarios). R1–R19 preserved untouched |

## Carry-forward

- None blocking.
- **W1–W3 are cheap test-debt items** (one keyboard E2E, one resize E2E, one desktop-eval/a11y assertion) — candidates for a small F3 follow-up or a test-debt pass.
- **F3 completes Ola 1 of the chart-frontend roadmap** (F0 layered ESM base, F1 legend, F3 shell — all archived). F2/F4+ are the next chart-frontend work; the frozen seams (layered module inventory, store boundary, bus protocol, `window.marketChart` 8 keys, `window.SmcOverlayCore`, the `per_user` ownership contract) remain in force until a new change.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (2-slice chain PRs
#133/#134 → tracker #135) → verified (`pass_with_warnings`; no CRITICAL/BLOCKER)
→ merged → archived.

**F3 (chart-shell) is complete — Ola 1 of the chart-frontend roadmap is done.**

Traceability: `openspec/changes/archive/2026-10-13-chart-shell/` (explore,
proposal, design, specs, tasks, verify-report); engram
`sdd/chart-shell/{archive-report,proposal,spec,design,tasks,verify-report}` and
`sdd/chart-shell/apply-progress` (id 1524).
