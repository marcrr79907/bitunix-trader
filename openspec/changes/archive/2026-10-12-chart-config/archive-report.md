# Archive Report: chart-config

**Archived**: 2026-10-12
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 criticals) — 10/10 requirements, 34/36 scenarios
**Delivery**: tracker PR #84; feature-branch chain #85 → #86 → #87
**Chain commits**: tracker `feat/chart-config` → PR1 `f9dd867` → PR2 `425eb60` → PR3 `8e25b55`
**Merged commit**: PR #84 merge `a5133ab` on `develop`
**Consolidated range**: `develop` tip `a5133ab`; chain diff vs previous base — 12 files, +887/−32

## What Shipped

Per-user persisted chart layout (issue #71, Fase A2): the indicator set and its
parameters are saved server-side and restored when the chart opens, so a user's
`/market/` view survives reloads and symbol switches. TradingView-style: one
layout per `(user, symbol, interval)`.

| Area | Delivered |
|------|-----------|
| Model | `web/trading/models.py`: `ChartLayout(UserOwnedModel)` — `symbol`, `interval`, JSON `indicators`, `updated_at`; `UniqueConstraint(user,symbol,interval)`; additive migration `web/trading/migrations/0005_chartlayout.py` |
| Endpoint | `web/market/views.py` + `urls.py`: `api_layout` GET/PUT `@login_required`; GET miss → 200 default `exists:false` (never 404); PUT validates before write (unknown token/bad param → 400) then `for_user(...).update_or_create` |
| Validation | `web/market/quotes.py`: `DEFAULT_LAYOUT=[{sma},{ema},{rsi}]`; `parse_layout_indicators` token ∈ `REGISTRY`, params via `_parse_params` |
| Isolation | `ChartLayout` in `OWNED_MODELS`; guard fixture + A≠B tests |
| Adapter | `chart.js`: async `boot()` fetch layout → sync panel + state → `buildChart()`/`connect()`/`fetchHistory()`, `.catch` → DOM defaults; `switchTo` loads target layout; debounced (~500 ms) PUT with captured `symbol`/`interval`; `sma20`→`sma`/`ema20`→`ema` |
| UI | `chart.html`: CSRF meta; native `<input type="number" class="indicator-param">` per param-capable overlay; token values; design tokens |
| Tests | `tests/web/test_isolation.py`, `test_owned_model_guard.py`, `test_market_api.py`, `test_market_e2e.py` |

## Verify Findings

Verdict `pass_with_warnings`; 0 blockers, 0 criticals. Full chain present
(`f9dd867` → `425eb60` → `8e25b55`, all ancestors of HEAD). Every L1/L2 gate green:
468 passed + 14 E2E, ruff + format clean, `makemigrations --check` clean, patch
gate 100% (77 lines), web coverage 97.86%, `requirements.txt`/CSP/`chart-core.js`
unchanged. Independent probes confirmed model/endpoint/isolation/guard, JS
inspection confirmed no indicator math, an `update()`-only live stream, and an
async boot with DOM-default fallback.

### Warnings carried (non-blocking)

- **W1 — R5 "Payload pins the active chart" is not race-tested (PARTIAL).**
  The capture-at-change-time logic is correct by inspection (`chart.js` snapshots
  `state.symbol`/`state.interval` before `setTimeout`; the `gen` counter guards the
  reverse race), but no test schedules a debounce, then `switchTo`, and asserts the
  pending PUT still carries the captured key.
- **W2 — R6 "Default matches prior rendering" has no suite regression test (PARTIAL).**
  The independent probe confirms exact equality (`sma` == `sma20`, `ema` == `ema20`;
  `sma_len=50` differs), but no test guards it — a future default change would
  regress silently.
- **W3 — Cross-token param accepted by `parse_layout_indicators`.**
  `_validate_layout_params` validates each key against the global `_INT_PARAMS`/
  `_FLOAT_PARAMS` sets, not against the token's relevant params, so a
  valid-but-mismatched key (`sma_len` on the `ema` token) is stored. Rendering is
  unaffected; no UI path emits it.
- **W4 — API accepts legacy tokens the JS adapter cannot render.**
  `sma20`/`ema20`/`rsi14` remain in the server `REGISTRY` for kline back-compat, but
  the adapter's `REGISTRY`/toggles only know `sma`/`ema`/`rsi`. A hand-crafted PUT
  storing a legacy token returns 200 on GET but renders no indicator series
  (candles still render, degraded). No current UI path stores legacy tokens.
- **SUGGESTION 1** — `tasks.md` WU1/WU2 checkboxes remain `[ ]` although their
  commits are in the chain (cosmetic; same pattern as `chart-indicators`).
- **SUGGESTION 2** — No node unit test for the `chart.js` adapter; debounce/capture
  logic is exercised solely by E2E.

### Process note (topology)

Unlike the previous `chart-indicators` chain (all child PRs targeted the tracker),
this chain's PRs (#85/#86/#87) were opened **chained to each other** (PR2 → PR1
branch, PR3 → PR2 branch) rather than all → tracker #84. The tracker was
**re-consolidated via an explicit merge**, so `develop` now carries the full
PR1+PR2+PR3 content (`a5133ab`, diagnostics clean). No verification or code impact;
recorded so future chains use the documented all→tracker topology.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-config (new) | R1 per-user layout persistence | ✅ model + additive migration + unique key |
| chart-config (new) | R2 layout API | ✅ GET default / PUT upsert / CSRF / 400 / 302 |
| chart-config (new) | R3 per-user isolation (R14) | ✅ `for_user` everywhere; `OWNED_MODELS` + guard |
| chart-config (new) | R4 restore on boot | ✅ async boot + DOM-default fallback; switch loads target |
| chart-config (new) | R5 save on change | ✅ debounced PUT with captured key |
| chart-config (new) | R6 param editing & token vocabulary | ✅ `sma`/`ema` param-driven; default 20 == prior |
| chart-config (new) | R7 CSP, design system, no new dependency | ✅ CSP/`requirements.txt`/`src/` unchanged |
| per-user-isolation | R14.2 cross-user read denied | ✅ + `ChartLayout` in delivered set |
| per-user-isolation | R14.3 unscoped-query guard | ✅ `OWNED_MODELS` + `ChartLayout`; guard fixture |
| market-chart | R10 layout endpoint & restore contract | ✅ endpoint contract + CSP-clean |

## Gates

`python -m pytest` 468 passed / 14 deselected (exit 0); E2E `-m e2e` 14 passed;
`node --test tests/js` 9 passed; `ruff check` + `ruff format --check` clean;
`makemigrations --check` clean; patch gate 100% (77 lines, 0 missing); web
coverage 97.86%; `requirements.txt`, CSP, and `chart-core.js` unchanged; boundary
+ order-scanner green.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-config | Created | New capability — R1–R7 (21 scenarios) copied verbatim from the change spec |
| per-user-isolation | Updated | R14.2 delivered set + `ChartLayout` & +1 scenario; R14.3 `OWNED_MODELS` + `ChartLayout` & scenario extended; R14.1/R14.4 preserved |
| market-chart | Updated | + R10 (5 scenarios); R1–R9 preserved untouched |

## Carry-forward

- None blocking. W1/W2 are warning-level coverage gaps (racing ordering and
  default-equivalence lack regression tests; both correct by inspection/probe).
- W3/W4 are non-blocking API holes reachable only via a hand-crafted PUT
  (cross-token param; legacy tokens storable but unrenderable). If a future change
  tightens the layout validator, restrict tokens to the adapter vocabulary and/or
  map legacy tokens on read.

## SDD Cycle Complete

Planned → implemented (3-PR feature-branch chain, #85/#86/#87) → verified
(pass_with_warnings; no CRITICAL/BLOCKER) → merged (tracker PR #84, `a5133ab`) →
archived.

Traceability: `openspec/changes/archive/2026-10-12-chart-config/`
(explore, proposal, design, specs, tasks, verify-report); engram
`sdd/chart-config/{proposal,spec,design,tasks,apply-progress,verify-report}`.
