# Tasks: positions-journal-ui (issue #58, Fase 6c)

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a (single PR)
400-line budget risk: Medium

## Guard/Edge Matrix

- [x] `/positions/` + `/journal/` anonymous → 302 login
- [x] Positions: latest `ts` per symbol only (max-ts query)
- [x] distance = `src.monitor.liq_distance_pct`; state = `src.monitor.margin_state`
- [x] Missing mark (`TickerSnapshot`) → distance "—", no error
- [x] Empty state (no rows) for both pages
- [x] A≠B: B sees empty states, none of A's symbols/data
- [x] Journal fixture → win_rate 66.67%, net 10.0, expectancy 3.333, PF 3.0, equity [10,5,10]
- [x] Journal reuses `src.journal.metrics` + `src.metrics` (no reimplementation)
- [x] No `decrypt` in views; credential scanner green
- [x] No unscoped `<OwnedModel>.objects.<verb>()` in `web/trading/` views; R14.3 guard green
- [x] Home links `/positions/` + `/journal/`
- [x] CSP unchanged
- [x] `src/` boundary green; `requirements.txt` unchanged; no migration
- [x] patch coverage 100%; ruff clean

## WU1 — Positions view + template

Branch `feat/positions-journal` (base `develop`). Depends: design-system (merged).

- [x] 1.1 **RED** `tests/web/test_positions.py`: anonymous→302; latest-per-symbol; distance/state reuse; missing mark "—"; empty state; A≠B.
- [x] 1.2 **GREEN** `web/trading/views.py::positions` (`for_user`, `Max("ts")` latest, `_position_view` reusing `src.monitor` helpers, latest global `TickerSnapshot` mark).
- [x] 1.3 **GREEN** `web/trading/templates/trading/positions.html` (shell + account header + table + empty state).
- [x] 1.4 **GREEN** `web/trading/urls.py` route `positions/`; include in `config/urls.py`.
- [x] 1.5 Rollback: delete view/template/urls; revert include + home.

## WU2 — Journal view + template

Depends: WU1 (urls/app harness).

- [x] 2.1 **RED** `tests/web/test_journal.py`: anonymous→302; empty state; known fixture values; A≠B.
- [x] 2.2 **GREEN** `web/trading/views.py::journal` (`Trade.for_user`, reuse `src.journal.metrics` + `src.metrics`, no arithmetic).
- [x] 2.3 **GREEN** `web/trading/templates/trading/journal.html` (metric cards + per-symbol table + empty state).
- [x] 2.4 **GREEN** route `journal/`.
- [x] 2.5 Rollback: delete view/template/route.

## WU3 — Navigation + wiring

Depends: WU1, WU2.

- [x] 3.1 **RED** test: home links both pages.
- [x] 3.2 **GREEN** `accounts/home.html`: in-content links to `/positions/`, `/journal/`.
- [x] 3.3 Rollback: revert home.

## Phase 4 — Verification

- [x] 4.1 `python -m pytest` green (Strict TDD); patch coverage 100%.
- [x] 4.2 ruff clean; `makemigrations --check` clean.
- [x] 4.3 Scanners (R14.3 guard + credential) green; `src/` boundary green; no new dep.
- [x] 4.4 Optional dev-only E2E smoke (pages render under shell).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | WU1 ~180, WU2 ~150, WU3 ~15, tests ~180 → ~500 total |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | single PR (one cohesive page pair sharing the read seam) |
| Delivery strategy | ask-on-risk |
| Chain strategy | n/a |
| Tracker branch | `feat/positions-journal` → `develop` |

```text
Decision needed before apply: No
Chained PRs recommended: No
400-line budget risk: Medium
```
