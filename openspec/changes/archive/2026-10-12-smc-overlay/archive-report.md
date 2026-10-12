# Archive Report: smc-overlay

**Archived**: 2026-10-12
**Verdict**: `pass_with_warnings` (0 blockers, 0 criticals) — new `smc-overlay` capability (11 requirements / 27 scenarios); `market-chart` DELTA R12
**Delivery**: 3-slice Feature Branch Chain — PR #97 (endpoint) → #98 (core+render) → #99 (E2E+audit), each based on tracker `feat/smc-overlay`; tracker merged to `develop` via PR #100 (merge `a649466`)
**Issue**: #75 (Fase C1)
**Chain commits**: slice1 `4c31166` (`…-endpoint`) · slice2 `574fe12` (`…-render`) · slice3 `bfa2425` (`…-e2e`)
**Code diff vs pre-change base `6806ea2`**: 11 files, +1684/−33 (excluding `openspec/`) — `web/market/{quotes.py,views.py,urls.py}`, `web/market/templates/market/{chart.html,chart.js,smc-overlay-core.js}`, `web/accounts/templates/registration/theme.css`, `tests/js/smc-overlay-core.test.js`, `tests/web/test_market_{api,ux,e2e}.py`

## What Shipped

Fase C1: the **read-only render layer** over the frozen B1/B2 `src/smc/` core.
One GET endpoint runs the pure chain over a candle window and returns
time-resolved records; the browser only draws them. No `src/` change, no
migration, no model, no new dependency, no order surface.

| Area | Delivered |
|------|-----------|
| Endpoint | `web/market/views.py` `api_smc` (`@login_required`, GET-only) + `web/market/urls.py` `market/api/smc`; validates `symbol`/`interval ∈ quotes.INTERVALS`, `limit` int `1..200` (default 200) before work; maps `BitunixError`→400 / `RequestException`→502 |
| Payload builder | `web/market/quotes.py`: extracted `_fetch_window(client, symbol, interval, want, before)` (DB-first + gap-fill, DB wins, keeps `opens`); `get_kline_payload` reuses it; `get_smc_payload` (`want=limit`, no warm-up) + pure `_serialize_smc` resolving `index→time` server-side |
| Pure core | `web/market/templates/market/smc-overlay-core.js` (NEW UMD, mirror `drawing-core.js`): frozen API `{FAMILIES, COLORS, fromApi, visibleFamilies, descriptors, setupMarkers, counts}` — reshape only, null-guards, never throws, no SMC math |
| Render | `chart.js`: ONE canvas primitive (swings line+labels, BOS/CHoCH rays, OB/FVG rects, premium/discount full-width bands + equilibrium line, `autoscaleInfo`, `useMediaCoordinateSpace`) + ONE `createSeriesMarkers` handle for setups; recreated after `buildChart`; `smcGen` guard in `switchTo` clears then reloads |
| UI | `chart.html`: `<fieldset class="smc">` one `.smc-toggle` checkbox per family (all `checked`); `smc_overlay_core_js` same-origin view/route (mirror `drawing_core_js`), CSP unchanged |
| Seam | `window.marketChart.smc` (fetched payload) + `.smcToggles`; deep-equal asserted in node + Playwright |
| Tests | `tests/js/smc-overlay-core.test.js` (NEW, 19 tests); `tests/web/test_market_api.py` (endpoint contract + index→time), `test_market_ux.py` (core served), `test_market_e2e.py` (boot/toggle/switch + seam equality, 4 tests) |

## Verify Findings

Verdict `pass_with_warnings` (verify-report.md). L1: `pytest tests/ --ignore=tests/web` green; `pytest -m e2e -p no:randomly` **23 passed** (baseline 19 + 4 SMC); `node --test "tests/js/**/*.test.js"` **45 passed, 0 fail** (26 baseline + 19 new); `ruff check` + `ruff format --check` clean; `requirements.txt` vs develop empty diff; `src/smc/` untouched. L2: `diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` → **100%** (75 changed Python lines, 0 missing, `web/market/{quotes,views}.py`); JS layers outside the Python patch gate are covered by `node --test` + E2E per design. L3 spec conformance: endpoint frozen payload with server-resolved `time` (probe: `"index"` absent, `anchor_time` present), `limit` clamp default 200, anon→302, empty/short→200 + `range:null`, `label:null` for first-of-kind, one primitive + one marker handle, session-only toggles, `window.marketChart.smc` parity. Adversarial browser probes: 6 toggles present, seam populated (50 swings), exactly 1 `/market/api/smc` request on boot, toggling does not refetch, 0 page errors.

### Warnings carried (non-blocking)

- **W1 — White chart canvas vs dark app chrome** (pre-existing, chart-wide): the LightweightCharts canvas renders white while the app chrome is dark. Out of C1 scope; recorded as a follow-up.
- **W2 — Slice 3 touched a pre-existing RSI-pane E2E fixture**: two RSI-pane tests failed on a stale constant-close fixture; Slice 3 fixed the fixture at its root (varied-OHLC seed helper). Not an SMC regression; flagged for reviewer awareness.
- **W3 — `SL` a11y fix**: swing connector color `#9e9e9e` (2.7:1 on white) → `#616161` (6.2:1) for WCAG 1.4.11. Applied in `chart.js`.
- **W4 — Pre-existing WS-route E2E flake** (`test_ws_stream_never_calls_setdata`) surfaces occasionally under load; passes in isolation/re-runs. Run `-m e2e -p no:randomly` on an idle machine.
- **SUGGESTION — `tasks.md` checkboxes not marked.** Apply left the boxes unmarked (orchestrator hard contract); engram `sdd/smc-overlay/apply-progress` is the completion source, not `tasks.md`.

### Process note (topology — durable lesson reconfirmed)

The chain used the **documented topology**: all slice PRs base on the tracker
branch `feat/smc-overlay`. PR #97 (`feat/smc-overlay-endpoint`, `4c31166`) →
tracker; after merge, PR #98 (`feat/smc-overlay-render`, `574fe12`) → tracker;
after merge, PR #99 (`feat/smc-overlay-e2e`, `bfa2425`) → tracker; then tracker →
`develop` (PR #100 merge `a649466`). **Durable lesson: merge each slice into the
tracker BEFORE branching the next; never chain slice-to-slice.** The all→tracker
topology keeps every child diff clean against the tracker.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| smc-overlay (new) | R1 endpoint contract | ✅ GET-only, `@login_required`, anon→302, invalid `interval`/`limit`→400 before work, `limit` `1..200` default 200 |
| smc-overlay (new) | R2 candle window (DB-first, gap-fill, keeps opens) | ✅ `_fetch_window` shared with `get_kline_payload`; DB wins on dup `time`; read-only (no `Candle` write); 52 kline tests stay green |
| smc-overlay (new) | R3 frozen payload + index→time server-side | ✅ exact shape; `time=times[index]`, `anchor_time=times[anchor]`; no `index` leaked |
| smc-overlay (new) | R4 empty/short/error degradation | ✅ `<3`→200 empty + `range:null`; upstream fail w/ DB rows→200 degraded; nothing→502; mirrors `api_kline` |
| smc-overlay (new) | R5 market-global scoping (not per-user) | ✅ no `for_user`, no owned model, no write; identical payload per key |
| smc-overlay (new) | R6 render contract per element type | ✅ one primitive + one `createSeriesMarkers`; `useMediaCoordinateSpace`, null-guard, `autoscaleInfo`; recreated after rebuild |
| smc-overlay (new) | R7 session-only per-element toggles | ✅ 6 `.smc-toggle` all ON; no refetch on toggle; no persistence/migration |
| smc-overlay (new) | R8 multi-TF reload on switch | ✅ `switchTo` clears via `smcGen`, refetches same `(symbol,interval,limit)` as history |
| smc-overlay (new) | R9 payload↔drawn equality | ✅ `window.marketChart.smc` deep-equals response (node descriptors + Playwright seam) |
| smc-overlay (new) | R10 single source (no JS recompute) | ✅ `smc-overlay-core.js` reshapes only; no `find_*`/confluence/geometry math |
| smc-overlay (new) | R11 read-only, CSP, no new dependency | ✅ no order verb, `requirements.txt`/CSP/`PURE_MODULES` unchanged; order scanner clean |
| market-chart | R12 SMC overlay endpoint and render contract | ✅ endpoint contract + render/toggle/switch + payload parity (7 scenarios); R1–R11 preserved untouched |

## Gates

`python -m pytest tests/ --ignore=tests/web` green; E2E `-m e2e -p no:randomly` 23 passed; `node --test tests/js/**/*.test.js` 45 passed; `ruff check` + `ruff format --check` clean; `diff-cover` patch gate 100% (75 lines, 0 missing); `requirements.txt`, CSP, and `src/smc/` unchanged; boundary + order-scanner green.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| smc-overlay | Created | New capability — R1–R11 (27 scenarios) copied verbatim from the change spec |
| market-chart | Updated | + R12 (7 scenarios); R1–R11 preserved untouched |

## Carry-forward

- None blocking.
- W1 (white canvas vs dark chrome) is a chart-wide pre-existing issue; a future change can address canvas theming.
- W3 a11y contrast fix is applied and durable (no requirement owed).
- W4 is a pre-existing E2E infra flake; keep `-p no:randomly` for E2E runs.
- B1/B2 output shapes (`Swing`/`StructureEvent`/`OrderBlock`/`FVG`/`DealingRange`/`Setup`) and the C1 endpoint payload shape are frozen seams for D/E — do not change without a new change.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (3-slice chain PRs #97/#98/#99 → tracker #100, all→tracker) → verified (`pass_with_warnings`; no CRITICAL/BLOCKER) → merged (`a649466`) → archived.

Traceability: `openspec/changes/archive/2026-10-12-smc-overlay/` (explore, proposal, design, specs, tasks, verify-report); engram `sdd/smc-overlay/{archive-report,proposal,spec,design,tasks,verify-report}`.
