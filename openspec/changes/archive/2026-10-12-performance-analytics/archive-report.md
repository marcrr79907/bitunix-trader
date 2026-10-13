# Archive Report: performance-analytics

**Archived**: 2026-10-12
**Verdict**: `pass_with_warnings` (0 blockers, 0 criticals) — 2 new capabilities (`performance-analytics` 5 req / 15 scenarios, `analytics-screen` 6 req / 13 scenarios) + 3 modified capabilities (`trade-metrics` R8/R9/R10 added + R11 frozen-four preserved, `core-domain-boundary` R12 added, `per-user-isolation` R14.5 added)
**Delivery**: 3-slice Feature Branch Chain — PR #109 (`metrics` + `analytics` core) → #110 (signal extraction + `/analytics/` view) → #111 (SVG UI + E2E + `/impeccable`), each base on tracker `feat/performance-analytics`; tracker merged to `develop` via PR #112
**Issue**: #78 (Fase E1 — the LAST roadmap item)
**Verify**: `verify-report.md` — L1 full suite green (15 focused analytics web tests, 24 E2E = baseline 23 + 1); L2 patch 100% (195 changed lines, 0 missing); L3 all requirements satisfied; boundary + owned-model guard + isolation green; `requirements.txt` unchanged; no migration

## What Shipped

Fase E1: the **analytics + calibration** layer over data the project already owns.
Pure math additions in `src/metrics.py` (`max_drawdown`, `win_rate`, `net_pnl`),
a NEW pure `src/analytics.py` (grouping, per-bucket records, SMC-vs-trades
calibration join, pure inline-SVG builders), a keyword-only historical signal
seam on the frozen `market.quotes.get_smc_payload`, and a read-only
server-rendered `/analytics/` screen with inline SVG charts. The screen breaks
down net PnL / win rate / expectancy / profit factor / max drawdown by SMC-setup
kind / UTC hour / symbol, and renders the calibration block. All additive; the
system still **never orders**. No new runtime dependency; no migration; CSP
untouched; `/journal/` stays frozen.

| Area | Delivered |
|------|-----------|
| `src/metrics.py` | Additive `max_drawdown(equity)->float|None` (worst peak→trough, ≤0.0; empty→`None`; monotonic→`0.0`), `win_rate(pnls)->float|None` (wins/total*100, win = `p>0`; empty→`None`), `net_pnl(pnls)->float` (sum; empty→`0.0`). Frozen four (`expectancy`, `profit_factor`, `r_multiple`, `equity_curve`) + `journal.metrics()` untouched. |
| `src/analytics.py` (NEW) | Pure, stdlib + `src.metrics` only, never raises: `summarize(pnls)`, `group_metrics(rows, dimension)` (`setup`/`hour`/`symbol`; `None` key → `unmatched`/`unknown`; unknown dim → `{}`; sorted keys), `equity_and_drawdown(pnls)`, `calibrate(signals, trades, *, window_seconds)` (nearest same-symbol/same-direction signal within window; `matched`/`unmatched`/`by_setup`/`r_by_setup`; join-only `risk=|entry−stop|×qty`; zero risk → `None` R), `equity_svg`/`bars_svg` (deterministic, `xml.sax.saxutils.escape` labels). Registered in `PURE_MODULES`. |
| `web/market/quotes.py` | `get_smc_payload(client, symbol, interval, limit, *, before=None)` — keyword-only, backward-compatible; chain stays the sole SMC math home. |
| `web/trading/analytics.py` (NEW) | Signal-extraction seam: dedupe by `(symbol, bar=ctime//3_600_000)`, one `get_smc_payload` per distinct bar; swallows `BitunixError`/`RequestException` → empty signals, never 500. |
| `web/trading/views.py` | `analytics_view` (`@login_required`, GET-only); all trade reads via `Trade.for_user(request.user)`; all math delegated to `src/analytics.py` (single source); upstream degrade → empty signals. |
| `web/trading/urls.py` | `path("analytics/", views.analytics_view, name="analytics")`; `/journal/` untouched. |
| Template + CSS | `trading/analytics.html` (breakdown tables + calibration + inline SVG via `|safe`; empty states; no JS) + `theme.css` analytics/chart styles + `base.html` nav link. |
| Tests | `tests/test_metrics.py` (three scalars), `tests/test_analytics.py` (groups/calibration/exact SVG), `tests/test_boundary.py` (`analytics.py` in `PURE_MODULES`), `tests/web/test_analytics.py` (view/scoping/charts/E2E), `test_market_e2e.py`; `/impeccable` audit applied. |

## Verify Findings

Verdict `pass_with_warnings` (verify-report.md). L1: `python -m pytest tests/`
green; `pytest tests/web/test_analytics.py` green (15); `pytest -m e2e -p
no:randomly` **24 passed** (baseline 23 + 1); `ruff check .` + `ruff format
--check .` clean; `requirements.txt` vs develop empty diff; `src/` framework-free.
L2: `diff-cover coverage.xml --compare-branch=46b73ee --fail-under=100` → **100%**
(195 changed lines, 0 missing: `src/analytics.py`, `src/metrics.py`,
`web/trading/analytics.py`, `web/trading/views.py`, `web/market/quotes.py`).
L3: metrics, analytics, seam, view, and scoping all confirmed with independent
adversarial probes (exact drawdown/win_rate/group/calibrate outputs; A≠B; real
browser render of `/analytics/` with 2 SVGs, no inline handlers, no overflow).

### Warnings carried (non-blocking)

- **W1 — Slice 1/2 diffs > 400 lines** (tests-dominated). The pure-core and
  view slices each exceed the review budget; the `ask-on-risk` chain delivery
  accepted this in advance. Split the analytics test battery if a reviewer objects.
- **W2 — Trade-is-a-fill approximation.** Per-fill win-rate/R are approximations
  (a trade is a fill, not a round-trip); documented as the journal convention (Q3).
  Round-trip reconstruction is future work.
- **W3 — Calibration is join-only.** Trades without a matched SMC signal get no R
  (`None`), rendered "—". No stored risk / no migration by design (Q2).
- **W4 — Historical signal-extraction cost.** Bounded to `(symbol, bar)` dedupe;
  no cache in v1 (`ponytail:` keyed-by-bar memoization only if measured slow).
- **W5 — Slice 3 touched global CSS** (`theme.css` topbar wrap + panel scroll) to
  fix a pre-existing 375px overflow. Theme-file-local; verified no regression on
  `/journal/` and `/market/`.
- **SUGGESTION — `tasks.md` checkboxes unmarked.** Apply left the boxes unmarked
  (orchestrator hard contract); engram `sdd/performance-analytics/apply-progress`
  is the completion source, not `tasks.md`.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| trade-metrics | R8 Max drawdown (ADDED) | ✅ `max_drawdown`; probe `[1,2,1,3]`→`-1`, monotonic→`0.0`, empty→`None` |
| trade-metrics | R9 Win rate (ADDED) | ✅ `win_rate`; probe `[1,-1,2,-1]`→`50.0`, empty→`None` |
| trade-metrics | R10 Net PnL (ADDED) | ✅ `net_pnl`; sums; empty→`0.0` |
| trade-metrics | R11 Existing behavior preserved (ADDED) | ✅ frozen four + `journal.metrics()` unchanged |
| trade-metrics | R1–R7 (preserved) | ✅ untouched |
| performance-analytics (new) | A1 summarize | ✅ exact dict; empty → zero/`None`, never raises |
| performance-analytics (new) | A2 group_metrics | ✅ `setup`/`hour`/`symbol`; `None`→`unmatched`/`unknown`; unknown dim→`{}`; sorted |
| performance-analytics (new) | A3 equity_and_drawdown | ✅ one traversal; empty → `{[], None}` |
| performance-analytics (new) | A4 calibrate | ✅ nearest match / outside-window unmatched / direction mismatch / tie-break / zero-risk `None` R / empty no-raise |
| performance-analytics (new) | A5 Purity, determinism, boundary | ✅ in `PURE_MODULES`; stdlib + `src.metrics`; no clock; byte-identical |
| core-domain-boundary | R12 analytics module joins inventory (ADDED) | ✅ `"analytics.py"` registered; stdlib-only; `"metrics.py"` preserved |
| core-domain-boundary | R9–R11 (preserved) | ✅ untouched |
| analytics-screen (new) | AS1 Route and auth | ✅ GET-only `analytics` route; `login_required`; anonymous → 302; server-rendered |
| analytics-screen (new) | AS2 Per-user scoping | ✅ `Trade.for_user` only; A≠B; no-trades → 200 empty state |
| analytics-screen (new) | AS3 Breakdowns and calibration content | ✅ grouped tables parse `group_metrics`; calibration block; `None` R → "—"; no math in view/template |
| analytics-screen (new) | AS4 Inline SVG, no JS, no new dependency | ✅ inline `<svg role="img">` + `aria-label`; no `<script>`/`on*=`; CSP unchanged; `requirements.txt` unchanged |
| analytics-screen (new) | AS5 Historical signal seam | ✅ `before=` keyword-only; omitted backward-compatible; SMC math only in `src/smc/` |
| analytics-screen (new) | AS6 Read-only boundary | ✅ no order surface; no schema field/migration; `/journal/` frozen |
| per-user-isolation | R14.5 Analytics view is scoped (ADDED) | ✅ `Trade.for_user` only; scoped before join; R14.3 scanner green |
| per-user-isolation | R14.1–R14.4 (preserved) | ✅ untouched |

## Gates

`pytest` full suite green (15 focused analytics web tests); E2E 24 passed; `ruff
check` + `ruff format --check` clean; `diff-cover` patch gate 100% (195 changed
lines, 0 missing); `requirements.txt` unchanged; boundary (`analytics.py` in
`PURE_MODULES`) + owned-model guard + isolation green; `test_no_order_surface`
clean; `/analytics/` CSP unchanged; `/journal/` frozen.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| performance-analytics | Created | New capability — A1–A5 (15 scenarios) copied verbatim from the change spec |
| analytics-screen | Created | New capability — AS1–AS6 (13 scenarios) copied verbatim from the change spec |
| trade-metrics | Updated | R8/R9/R10 added; R11 reaffirms the frozen four; Purpose refreshed; R1–R7 preserved untouched |
| core-domain-boundary | Updated | R12 added (+5 scenarios); R9–R11 preserved untouched |
| per-user-isolation | Updated | R14.5 added (+2 scenarios); R14.1–R14.4 preserved untouched |

## Carry-forward

- None blocking.
- W1: Slice 1/2 sizes above the budget stay an accepted chain decision; split the
  analytics test battery only if a reviewer objects.
- W2: Trade = fill, not round-trip — per-fill win/R are documented approximations;
  round-trip reconstruction is future work.
- W3: R is join-only; unmatched trades have no R, rendered "—" (no migration).
- W4: signal-extraction cost O(distinct bars × chain); deduped by bar, no cache v1.
- W5: global CSS touch was theme-file-local, scoped to the pre-existing 375px
  topbar overflow; verified no `/journal/` or `/market/` regression.
- Frozen seams consumed by E1 (do not change without a new capability delta):
  `src/metrics.py` frozen four + `journal.metrics()`; the `src/smc/` chain
  (`find_setups`, `Setup`) as the sole SMC math home; `Trade.for_user`;
  `market.quotes.get_smc_payload` (extended keyword-only with `before=`).
- **Topology note**: all three slice PRs (#109/#110/#111) base on tracker
  `feat/performance-analytics`; the tracker merged to `develop` via PR #112. The
  feature chain is a Feature Branch Chain — child diffs must not show prior slices.

## Roadmap Complete

This archive closes **Fase E1 (issue #78)**, the LAST item of the A→E roadmap.
With it, every roadmap phase (A foundation, B market/indicators, C SMC, D alerts,
E analytics/calibration) is planned, implemented, verified, and archived.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (3-slice chain PRs
#109/#110/#111 → tracker #112 merged to `develop`) → verified
(`pass_with_warnings`; no CRITICAL/BLOCKER) → archived.

Traceability: `openspec/changes/archive/2026-10-12-performance-analytics/`
(explore, proposal, design, specs, tasks, verify-report, archive-report); engram
`sdd/performance-analytics/{archive-report,proposal,spec,design,tasks,verify-report}`.
