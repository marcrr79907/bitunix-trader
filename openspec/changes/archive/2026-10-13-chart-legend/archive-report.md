# Archive Report: chart-legend

**Archived**: 2026-10-13
**Verdict**: `pass_with_warnings` (0 blockers, 0 critical, 16/18 scenarios compliant, 2 partial) — new `chart-legend` capability (LC1–LC6, 8 requirements / 16 scenarios) + `market-chart` DELTA R19 (+1 requirement / 2 scenarios) and the R14 inventory/allowlist update; R1–R18 preserved untouched
**Delivery**: 2-slice Feature Branch Chain — PR #130 (core + host seam + serving) → #131 (controller + overlay + E2E), both base on tracker `feat/chart-legend`; tracker merged to `develop` via PR #132
**Issue**: #114 (Fase F1 — Ola 1)
**Chain commits**: slice1 `a57c73f` (`feat/chart-legend-core`) · slice2 `6b3043f` (`feat/chart-legend-overlay`)

## What Shipped

Fase F1 — the **first UX feature built on the F0 layered ESM base**: a
TradingView-style floating legend + crosshair OHLC/indicator readout for the
market chart. The legend is a **pure read-through**: it formats server-shaped
values from the v5 crosshair `param.seriesData` Map (hover) or
`host.getSeriesData()`/`getCandles()` last element (leave) and recomputes
nothing. No `src/` change, no migration, no model, no new dependency, no order
surface, no new global, `window.marketChart` stays 8 keys.

| Area | Delivered |
|------|-----------|
| Pure core | `legend-core.js` — frozen `DECIMALS`, `PLACEHOLDER`, `formatValue`, `formatOhlc`, `rows`, `lastValues`; no imports; never throws |
| Controller | `controllers/legend.js` — DI `create({store,bus,host,config})`; injects `.chart-legend` overlay into `#chart`; rAF-coalesced `textContent`; re-subscribes crosshair on every `chart:built` |
| Host seam | `chart-host.js` — `subscribeCrosshairMove(fn)`, null-guarded, mirroring `subscribeClick` |
| Wiring | `main.js` gains one line (`createLegend(...)`); `buildChart` untouched |
| Serving | `views.py` `MODULE_ALLOWLIST += "legend-core"`, `CONTROLLER_ALLOWLIST += "legend"`; `chart.html` modulepreload links |
| Styling | `theme.css` — `#chart{position:relative}` + `.chart-legend` overlay (absolute, `pointer-events:none`, token-based, 375px-safe) |
| a11y | `role="status" aria-label="Chart legend"`; `aria-live` off on hover, polite idle after 300ms debounce; signed `.num` change cue |
| Tests | `tests/js/legend-core.test.js` (+13) + `chart-controllers.test.js` (+6) + `chart-host.test.js` (+2); one/two new DOM-only E2E; existing assertions unedited |

## Verify Findings

Verdict `pass_with_warnings` (verify-report.md). L1: `node --test "tests/js/**/*.test.js"` **81 passed, 0 fail**; `pytest -m e2e -p no:randomly` **26 passed** (24 F0 baseline + 2 new legend); `pytest tests/ --ignore=tests/web` **337 passed**; `ruff check .` + `ruff format --check .` clean (133 files); `requirements.txt` vs develop empty diff; `package.json` exactly `{"type":"module"}`. L2: `diff-cover coverage.xml --compare-branch=feat/chart-legend --fail-under=100` → exit 0, **vacuously 100%** ("No lines with coverage information in this diff") — the only Python change is two `frozenset` string literals in `views.py` with no executable per-line points; all JS is outside the Python patch gate, covered by 81 node + 26 E2E. L3 spec conformance: LC1–LC6 + R19 + the R14 inventory/allowlist scenarios all satisfied; adversarial real-browser Playwright probes reproduced hover readout, leave last-values, 375px fit, interval-switch stale-handler re-bind (1 overlay, 8 keys, 0 errors), and no screen-reader spam (20 moves → 1 `aria-live` mutation, 40 coalesced rAF paints).

### Warnings carried (non-blocking)

- **W1 — LC2 "no indicator math" has no committed regression test.** The invariant is verified by static grep + export/no-throw probes only; nothing in the suite would fail if a future edit added indicator math or an import to `legend-core.js`. Fix: a cheap `readFileSync`-based node test asserting "no imports / no formula tokens".
- **W2 — three lifecycle/a11y scenarios proven by session probes only, not committed tests**: LC4 re-subscribe-across-rebuilds, LC5 state-change-announces-once, LC6 all-active-series-shown. The E2E exercises a single build and asserts `rows >= 1`; add one interval-switch E2E assertion to lock re-binding permanently.
- **W3 — R14 size ceiling has no automated check.** Measured manually (legend-core 118, legend controller 219 ≤ ~300); a 3-line test would prevent silent drift.
- **W4 — Workload, not correctness**: Slice 2 diff is ~439 insertions, over the 400-line review budget (bulk = the two test files). Pre-flagged by apply; kept as a PR-size note.
- **SUGGESTION — `tasks.md` checkboxes remain unmarked** (executor contract forbids editing `openspec/**`); engram `sdd/chart-legend/apply-progress` (id 1516) is the completion source, consistent with F0 precedent.

### Topology note (durable lesson)

All slice PRs base on the tracker branch `feat/chart-legend`: PR #130
(`feat/chart-legend-core`, `a57c73f`), then #131 (`feat/chart-legend-overlay`,
`6b3043f`), then tracker → `develop` via PR #132. **Durable lesson
(reconfirmed): merge each slice into the tracker BEFORE branching the next;
never chain slice-to-slice.** The all→tracker topology keeps every child diff
clean against the tracker.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-legend | LC1 — legend-core formatter contract | ✅ exactly 6 exports; `DECIMALS` frozen + exact; placeholder/fallback; never throws; plain-data output |
| chart-legend | LC2 — Single-source, no recompute | ⚠️ holds (grep + probes); scenario PARTIAL — no committed source-inspection test (**W1**) |
| chart-legend | LC3 — Crosshair readout contract | ✅ hover/leave/off-bar null-safe; rAF + `textContent` only |
| chart-legend | LC4 — Host crosshair seam | ✅ null-guarded mirror of `subscribeClick`; re-binds on `chart:built` (probe, **W2**) |
| chart-legend | LC5 — Overlay DOM and a11y policy | ✅ `role=status`, idle-only polite debounce, signed cue; no hover spam; state-change announce proven by probe (**W2**) |
| chart-legend | LC6 — Composition, lifecycle, responsive | ✅ all active series (probe, **W2**); 375px no overflow; 8-key seam frozen |
| market-chart | R19 — Host crosshair subscription seam | ✅ method mirrors `subscribeClick`; handler re-binds after rebuild |
| market-chart | R14 — Layered ESM module boundary (modified) | ✅ inventory gains `legend-core.js`/`controllers/legend.js`; new modules served 200 JS MIME; size ceiling measured (**W3**) |

R1–R18 in `openspec/specs/market-chart/spec.md` preserved untouched.

## Gates

`node --test "tests/js/**/*.test.js"` 81 passed; E2E `-m e2e -p no:randomly` 26 passed; `pytest tests/ --ignore=tests/web` 337 passed; `ruff check` + `ruff format --check` clean; `diff-cover` patch gate vacuous 100% (no measurable changed Python lines); `package.json` exactly `{"type":"module"}`; `requirements.txt`, CSP, `src/`, and `window.marketChart` shape unchanged.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-legend | Created | New canonical spec from the change delta — LC1–LC6 (6 requirements, 16 scenarios) + edge-case matrix |
| market-chart | Updated | R14 replaced with the modified inventory/allowlist version (adds `legend-core.js`, `controllers/legend.js`, `New modules are served` scenario); R19 appended (host crosshair seam). R1–R18 preserved untouched |

## Carry-forward

- None blocking.
- **W1–W3 are cheap test-debt items** (one committed no-math source test, one interval-switch E2E, one size-ceiling test) — candidates for a small F1 follow-up or the F2 test-debt pass.
- F1 is the **first UX feature on the F0 base** — the layered module inventory, store boundary, bus protocol, `window.marketChart` 8-key seam, and `window.SmcOverlayCore` re-export remain frozen seams for F2–F11; do not change without a new change.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (2-slice chain PRs #130/#131 → tracker #132) → verified (`pass_with_warnings`; no CRITICAL/BLOCKER) → merged → archived.

**F1 (legend + crosshair readout) is complete — the first UX feature on the F0 layered ESM base.**

Traceability: `openspec/changes/archive/2026-10-13-chart-legend/` (explore, proposal, design, specs, tasks, verify-report); engram `sdd/chart-legend/{archive-report,proposal,spec,design,tasks,verify-report}`.
