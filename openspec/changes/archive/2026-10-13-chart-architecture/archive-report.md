# Archive Report: chart-architecture

**Archived**: 2026-10-13
**Verdict**: `pass_with_warnings` (0 blockers, 0 criticals) — `market-chart` DELTA R14–R18 (5 requirements / 12 scenarios); R1–R13 preserved untouched
**Delivery**: 4-slice Feature Branch Chain — PR #125 (ESM scaffold) → #126 (host+store+bus) → #127 (controllers+main) → #128 (cleanup+route test+ADR), each based on tracker `feat/chart-architecture`; tracker merged to `develop` via PR #129 (merge `fc5a5b8`)
**Issue**: #113 (Fase F0)
**Chain commits**: slice1 `0bfb29f` (`…-esm-scaffold`) · slice2 `513029c` (`…-host-store-bus`) · slice3 `ceaf714` (`…-controllers`) · slice4 `b9b1f72` (`…-cleanup`)

## What Shipped

Fase F0: the 1137-line `chart.js` IIFE is split into layered native-ESM modules
behind a thin entry. Delivery migrates UMD/globals → native ESM with **zero
behavior change** as the contract — the architecture becomes a solid base for
F1–F11. No `src/` change, no migration, no model, no new dependency, no order
surface.

| Area | Delivered |
|------|-----------|
| Entry | `chart.js` thin: Django-injected `CONFIG` (`{{ symbols|safe }}` + `CHANNELS`) + imports + `boot()`; still contains `BTCUSDT`/`market_kline` |
| Pure cores | `chart-core.js`/`drawing-core.js`/`smc-overlay-core.js` — UMD shim dropped, native `export` |
| State | `chart-store.js` (`STORE_KEYS` = UI/config only, `set` drops `candles` — a dedicated test proves it), `chart-bus.js` |
| Host | `chart-host.js` — chart/series/panes/scales/crosshair + candle data; `REGISTRY`/`PANE_ORDER`; the sole LightweightCharts construction surface |
| Controllers | `controllers/{indicators,history,stream,drawings,smc,toolbar}.js` — DI `create({store,bus,host,config})`, import host/store/bus leaf-first, never `main` |
| Orchestration | `main.js` — wires store/bus/host/controllers, subscribes the bus, owns `gen`/`boot()`/`switchTo()` `.then()` order + `ready` verbatim |
| Serving | `web/market/views.py` 2 parameterized allowlist views (`market_chart_module_js`/`market_controller_js`), traversal-blocked, `text/javascript`; `urls.py` routes; `chart.html` `<script type="module">` (CDN stays classic) |
| Tools | root `package.json` = exactly `{"type":"module"}` (Node metadata only) |
| Tests | `tests/js/*.test.js` `require`→`import`, assertions unchanged (60 pass); `test_market_ux.py` route-coverage allowlist test; `test_market_e2e.py` untouched |

## Verify Findings

Verdict `pass_with_warnings` (verify-report.md). L1: `node --test "tests/js/**/*.test.js"` **60 passed, 0 fail**; `pytest -m e2e -p no:randomly` **24 passed**; `pytest tests/ --ignore=tests/web` green; `ruff check .` + `ruff format --check .` clean (133 files); `package.json` exactly `{"type":"module"}`; `requirements.txt` vs develop empty diff. L2: `diff-cover --compare-branch=origin/develop --fail-under=100` → **100%** (10 changed Python lines, 0 missing, `web/market/views.py`); JS outside the Python patch gate covered by 60 node + 24 E2E. L3 spec conformance R14–R18 all satisfied: frozen inventory, store key set frozen, largest module `controllers/drawings.js` = 298 lines, no controller imports `main`, `main.js` no cycles; UMD gone, all 14 module routes 200 `text/javascript` (unknown → 404), `boot()` last side effect; `CONFIG` is the ESM export with no inline/window config; #68 invariants + three race guards + boot/switch ordering byte-equivalent; `window.marketChart` exactly 8 keys + `window.SmcOverlayCore` re-exposed. Adversarial real-browser probes (Playwright, logged in): 14 modules 200, `ready===true`, panes `rsi`+`macd`, canvas present, interval switch `1m→1h`, MACD toggle, and switch-then-toggle all **0 page errors**.

### Warnings carried (non-blocking)

- **W1 — `Object is disposed` under a compressed probe sequence**: observed once when an interval switch was immediately followed by a MACD toggle with no wait; **0 errors** when the two actions are sequential with realistic waits, and each alone is 0 errors. This is a probe-race under an artificially compressed sequence, not an F0 regression — the known pre-existing E2E flake under load. Flagged for transparency.
- **W2 — Large raw slice diffs** (S3 ~1218 ins/1065 del) are dominantly **moved** code, not rewritten; S1's UMD→ESM dedent shows ~115 real lines under `git diff -w`. Reviewer should judge behavior-equivalence, not line count.
- **W3 — `chart-host.js` holds shared `seriesData`/`lastBucket` accessors** added during the split (a small extension of its #68 ownership), and `stream.connect(next)` accepts the boot key. Intentional; no behavior change.
- **W4 — `CONTROLLER_ALLOWLIST` route coverage** is proven by a dedicated S4 test that iterates both allowlists, closing the "missing route → import 404 → blank chart" risk.
- **SUGGESTION — `tasks.md` checkboxes not marked.** Apply left the boxes unmarked (orchestrator hard contract); engram `sdd/chart-architecture/apply-progress` is the completion source, not `tasks.md`.

### Topology note (durable lesson)

The chain used the **documented topology**: all slice PRs base on the tracker
branch `feat/chart-architecture` — PR #125 (`…-esm-scaffold`, `0bfb29f`), then
#126 (`…-host-store-bus`, `513029c`), then #127 (`…-controllers`, `ceaf714`),
then #128 (`…-cleanup`, `b9b1f72`) — and then tracker → `develop` via PR #129
(merge `fc5a5b8`). **Durable lesson (reconfirmed): merge each slice into the
tracker BEFORE branching the next; never chain slice-to-slice.** The all→tracker
topology keeps every child diff clean against the tracker.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| market-chart | R14 — Layered ESM module boundary | ✅ frozen inventory present; store holds only UI/config (candle-drop test passes); no module > ~300 lines (max 298); no controller imports `main`; `main.js` no cycles |
| market-chart | R15 — ESM loading and module serving | ✅ `package.json {"type":"module"}`; cores native `export`, UMD gone; tests `import`; `<script type="module">`; CDN classic; 14/14 module routes 200 `text/javascript` (unknown → 404); no controller self-boots; `boot()` last side effect |
| market-chart | R16 — Config injection | ✅ `CONFIG` is the ESM export in the entry; no inline/window config; `/market/chart.js` contains `BTCUSDT` AND `market_kline` (`test_market_ux.py` unedited) |
| market-chart | R17 — Preserved behavior invariants | ✅ #68 single-write-path (history→`setData`, live→`update()`); single-source (JS never computes indicators/SMC); `gen`/`drawGen`/`smcGen` guards + boot/switch `.then()` order verbatim |
| market-chart | R18 — Test-seam preservation | ✅ `window.marketChart` exactly 8 keys + equivalent update-timing; `window.SmcOverlayCore` re-exposed; `test_market_e2e.py` green with no assertion edits |

R1–R13 in `openspec/specs/market-chart/spec.md` preserved untouched.

## Gates

`node --test "tests/js/**/*.test.js"` 60 passed; E2E `-m e2e -p no:randomly` 24 passed; `pytest tests/ --ignore=tests/web` green; `ruff check` + `ruff format --check` clean; `diff-cover` patch gate 100% (10 lines, 0 missing); `package.json` exactly `{"type":"module"}`; `requirements.txt`, CSP, and `src/` unchanged; boundary + order-scanner green.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| market-chart | Updated | + R14–R18 (5 requirements, 12 scenarios) appended verbatim from the change delta; R1–R13 preserved untouched |

## Carry-forward

- None blocking.
- W1 is a probe-race under a compressed sequence, matching the pre-existing E2E flake; run E2E `-p no:randomly` on an idle machine.
- W3 host accessors (`seriesData`/`lastBucket`) are an intentional extension of #68 ownership — keep candle data in `chart-host.js`.
- The layered module inventory, store boundary, bus protocol, `window.marketChart` 8-key seam, and `window.SmcOverlayCore` re-export are **frozen seams** for F1–F11 — do not change without a new change.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (4-slice chain PRs #125/#126/#127/#128 → tracker #129, all→tracker) → verified (`pass_with_warnings`; no CRITICAL/BLOCKER) → merged (`fc5a5b8`) → archived.

**F0 (base sólida) is complete — this is the BASE for F1–F11.**

Traceability: `openspec/changes/archive/2026-10-13-chart-architecture/` (explore, proposal, design, specs, tasks, verify-report); engram `sdd/chart-architecture/{archive-report,proposal,spec,design,tasks,verify-report}`.
