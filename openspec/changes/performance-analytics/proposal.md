# Proposal: performance-analytics (Fase E1, issue #78 — roadmap close)

## Intent

E1 is the **analytics + calibration** layer over data the project already owns:
per-user `Trade` fill rows and the frozen `src/smc/` core. It answers "what
works?" — R-multiple, expectancy, profit factor, win rate, net PnL, equity
curve and max drawdown — **broken down by SMC-setup kind / UTC hour / symbol**,
plus a **calibration** view crossing historical SMC signals against real trades.
Read-only: it **never orders**.

## Why Now

E1 is the LAST roadmap item (issue #78). The math layer (`src/metrics.py`), the
SMC chain, `get_smc_payload`, and the per-user `Trade` seam all exist and are
frozen; the journal already receives `equity_curve` but never draws it. Every
dependency is in place — E1 is purely additive analysis + a new screen.

## Scope

### In Scope
- Pure additives in `src/metrics.py`: `max_drawdown`, `win_rate`, `net_pnl`.
- NEW pure `src/analytics.py`: `summarize`, `group_metrics`, `equity_and_drawdown`, `calibrate`.
- Historical SMC signal extraction (web seam) + pure calibration join.
- NEW read-only `/analytics/` screen in `trading`; server-rendered inline SVG charts.
- Tests: metrics/analytics batteries, boundary, view/scoping, E2E; `/impeccable` audit.

### Out of Scope
- **ML / prediction — explicitly out** (future).
- **Order execution — forbidden, ever** (R11).
- Round-trip reconstruction from fills; persisting `setup_kind`/risk on `Trade` (no migration).
- New runtime dep, npm/build, CSP relaxation, second chart lib, caching/precompute (v1 on-request).
- Changing the frozen `src/metrics.py` four functions or `journal.metrics()`; `/journal/` stays frozen.

## Capabilities

### New Capabilities
- `performance-analytics`: pure analytics/calibration module + `/analytics/` read-only screen with SVG charts.

### Modified Capabilities
- `trade-metrics`: additive `max_drawdown` / `win_rate` / `net_pnl` (frozen four untouched).
- `core-domain-boundary`: register `src/analytics.py` in `PURE_MODULES`.

## Approach

- **Vocabulary (Q1)**: `setup_kind := f"{direction}:score{score}"`; `direction`/`event_kind` secondary.
- **R-multiple (Q2)**: join-only vs matched SMC setup (`risk=|entry−stop|×qty`); unmatched → `None`; **no migration**.
- **Granularity (Q3)**: each fill = one trade (journal status quo).
- **Hour (Q4)**: UTC, **caller-supplied** (pure fns stay deterministic/tz-free).
- **Charts (Q6)**: pure Python inline-SVG builder; no new dep; unpkg/LightweightCharts stays `/market/`-only.
- **Metrics home (Q10)**: scalars in `src/metrics.py`; groups+calibration in NEW `src/analytics.py` (both `PURE_MODULES`).
- **Signal seam (Q12)**: extend `get_smc_payload(..., before=None)` keyword-only; pure chain stays sole SMC math home.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/metrics.py` | Modified | +`max_drawdown`/`win_rate`/`net_pnl` |
| `src/analytics.py` | New | pure groups + calibration |
| `tests/test_metrics.py`, `tests/test_analytics.py`, `tests/test_boundary.py` | New/Modified | batteries; `analytics.py` in `PURE_MODULES` |
| `web/market/quotes.py` | Modified | `get_smc_payload(before=…)` |
| `web/trading/analytics.py`, `svg.py` | New | signal extraction seam; pure SVG builder |
| `web/trading/views.py`, `urls.py`, `templates/trading/analytics.html` | Modified/New | `/analytics/` route + screen |
| `web/accounts/.../base.html`, `theme.css` | Modified | nav link + chart styles |
| `tests/web/test_analytics.py`, `test_market_e2e.py` | New/Modified | view/scoping/E2E |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Trade = fill, not round-trip | High | Document Q3; calibrate per-fill; round-trips future |
| No stored risk → R join-only | Med | Explicit `None`, never raise; UI shows "—" |
| Signal-extraction cost O(trades×chain) | Med | Dedupe by `(symbol,bar)`; no cache v1 |
| `src/` framework-free break | Med | `analytics.py` in `PURE_MODULES`; no sqlite3/rich/Django |
| R14 scoping miss | Med | View reads `Trade.for_user(user)` only; guard green |
| Charts without deps/CSP | Med | Inline SVG (pure, patch-covered); CSP unchanged |
| Patch 100% | Med | Pure math unit-tested; SVG asserted on fixture |
| Determinism | Low | Sorted keys, `fmean`, no `datetime.now` |

## Rollback Plan

Pure additive. Revert reverse: delete `src/analytics.py` + its tests and remove
it from `PURE_MODULES`; drop the three new `src/metrics.py` fns; revert
`get_smc_payload(before=…)` to the frozen signature; delete the `/analytics/`
view + template + route + nav link + SVG builder + CSS. No migration, no data
mutation — a plain `git revert` of each slice suffices.

## Dependencies

- Frozen `src/metrics.py` (four fns) and `journal.metrics()` — reused unchanged.
- Frozen `src/smc/` chain (`find_setups`, `Setup`) — sole SMC math.
- `Trade` shape (per-user, `for_user`); `market.quotes.get_smc_payload` (frozen).

## Read-Only Boundary

The system MUST NOT place, modify, or cancel orders. E1 adds no execution path,
no exchange-client import, no new runtime dependency; R11/R14 scanners stay
clean; CSP untouched (analytics loads no JS).

## Delivery (Chained PRs — Feature Branch Chain)

Base = `feat/performance-analytics` tracker; each child targets the previous slice.

1. **Slice 1 — pure metrics + analytics core** (~410): `metrics.py` additives; NEW `src/analytics.py`; boundary + metrics/analytics tests. No web, no JS.
2. **Slice 2 — signal extraction + `/analytics/` view** (~380): `get_smc_payload(before=…)`; web seam + view + route + nav + scoping tests.
3. **Slice 3 — SVG UI + E2E + `/impeccable`** (~360): pure SVG builder + template + CSS; E2E; audit.

- Decision needed before apply: Yes · Chained PRs recommended: Yes · budget risk: High

## Success Criteria

- [ ] `max_drawdown`/`win_rate`/`net_pnl` added; frozen four + `journal.metrics()` unchanged.
- [ ] `src/analytics.py` pure, stdlib+`src.metrics` only; in `PURE_MODULES`.
- [ ] `/analytics/` renders breakdowns + calibration + inline SVG; anonymous → 302; no JS; CSP unchanged.
- [ ] All trade reads via `Trade.for_user(user)`; R14 guard green.
- [ ] No new dependency, no migration, no order surface; `pytest` green; patch 100%; `ruff` clean.
