# Proposal: positions-journal-ui

## Intent

Fase 6b (#57, merged) persists per-user positions, account, and trades, but the
web exposes **no view** for them: the dashboard shows only global `/market/` data.
Fase 6c (#58) delivers the product promise — "tus posiciones, tu journal" — as
two auth-gated pages that read the logged-in user's own persisted rows. Strictly
read-only: no secrets in the request path (R13), no cross-user reads (R14), no
order surface (R11).

## Scope

### In Scope
- `/positions/` (auth-gated, GET-only): latest per-symbol `PositionSnapshot` for
  the user + `AccountSnapshot` header (available/cross uPnL); table with liq
  distance, margin rate/state, uPnL — mirroring the CLI panel.
- `/journal/` (auth-gated, GET-only): win rate + net PnL per pair reusing the
  pure `src/` math (`metrics.py` / `journal.metrics`) as the single source.
- New `web/trading/{views,urls}.py` + two templates; links from `home.html`.
- HTMX (unpkg, CSP already allows it) for a single `every 30s` auto-refresh.
- Tests: auth gate, render-user-data, empty state, A≠B isolation, journal math.

### Out of Scope
- Alerts (Fase 7). Editing positions/orders — **HARD invariant (R11)**.
- Snapshot retention/decimation; advanced multi-user admin.
- Any change to `src/` (reused unchanged) or `requirements.txt` (no new runtime dep).

## Capabilities

### New Capabilities
- `positions-journal-ui`: auth-gated personal pages for the user's open positions
  and performance journal, read only through the ownership seam.

### Modified Capabilities
- `per-user-isolation`: request-path reads stay `for_user`-scoped (view-level A≠B).
- `security-invariants`: R13/R14 proven on the new request-path views.

## Approach

Place the views in the existing `web/trading/` app (owns the models, already
inside both scanners' request path → zero scanner/new-app changes; mirrors
`market/`). Read every row via `for_user(request.user)`. Positions: `Max("ts")`
then `filter(ts=...)` (one shared ts per sync cycle) — portable, no
`distinct("symbol")`; reuse `src.monitor.liq_distance_pct`/`margin_state`; mark
price from the latest global `TickerSnapshot`. Journal: build a plain row list
from `Trade.for_user(...)` and delegate to the pure `src/` functions; the view
computes nothing itself. Templates server-rendered; HTMX refreshes the table via
one `hx-get` (no fragment view needed).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/views.py` | New | `positions_page`, `journal_page` (GET, login_required) |
| `web/trading/urls.py` | New | `/positions/`, `/journal/` (bare names) |
| `web/trading/templates/trading/{positions,journal}.html` | New | server-rendered tables |
| `web/config/urls.py` | Modified | include `trading.urls` |
| `web/accounts/templates/accounts/home.html` | Modified | nav links next to Market |
| `tests/web/test_positions_ui.py`, `test_journal_ui.py` | New | gate, data, empty, A≠B, math |
| `tests/web/test_ux.py` | Modified | home links to the two pages |
| `src/`, `requirements.txt` | Unchanged | reused only; no new dependency |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Journal math source ambiguous (`metrics.py` vs `journal.metrics`) | Med | spec names one source; no view-side reimplementation |
| Distance needs a mark not in snapshots | Low | latest global `TickerSnapshot`; `None` → "—" |
| HTMX CDN/refresh regressions | Low | unpkg already CSP-allowed; server-rendered fallback |
| Patch coverage 100% strict | Med | one test per branch (empty/rows/A≠B/metrics) |

## Rollback Plan

Revert the branch: delete `web/trading/views.py`, `urls.py`, and the two
templates; restore `web/config/urls.py` and `home.html`; drop the two new test
files. `src/`, models, migrations, and both scanners are untouched, so `main`
still ships the working global dashboard and the CLI with R11/R13/R14 intact.

## Dependencies

- Phase 6b rows exist and are populated by the worker (merged).
- Existing patterns only: Django templates, `src/` pure math, CSP already allows
  the HTMX CDN. No new runtime dependency.

## Open Questions

- Single metrics source: reuse `metrics.expectancy`/`profit_factor` **and**
  `journal.metrics`, or extend `metrics.py` with win_rate/per_symbol? (recommend
  reuse both pure functions, default in spec).
- Auto-refresh mechanism: HTMX `every 30s` vs `<meta http-equiv="refresh">`?
  (recommend HTMX, issue asks for it).
- Equity curve on `/journal/` now or later? (recommend now — free from
  `metrics.equity_curve`).

## Success Criteria

- [ ] `/positions/` and `/journal/` are auth-gated; each shows ONLY the logged-in
      user's data (A≠B proven).
- [ ] Journal math reuses `src/` (single source; zero reimplementation in view/JS).
- [ ] Empty state renders friendly "no data yet" (no error, no foreign rows).
- [ ] No secrets/`decrypt` in the request path; both scanners green.
- [ ] `python -m pytest` green (Strict TDD); patch coverage 100%; ruff clean.
- [ ] `/impeccable audit` clean; no new runtime dependency; no order surface.

## Review Workload Forecast

- Estimated diff: **~350–500 changed lines** (2 views + urls + 2 templates, URL/
  home wiring, 2–3 test files, optional base-shell CSS).
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: Medium
