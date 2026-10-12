# Tasks: chart-config (issue #71, Fase A2)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Medium

## Guard/Edge Matrix

- [ ] unique `(user,symbol,interval)` → `IntegrityError`; two intervals coexist
- [ ] GET default → 200 `exists:false`, never 404; GET after PUT → `exists:true`
- [ ] PUT twice same key → one row (upsert)
- [ ] invalid token/param/interval/symbol → 400 before write
- [ ] A≠B read `DoesNotExist`; write isolated; B GET → default
- [ ] `ChartLayout` in `OWNED_MODELS`; unscoped fixture flagged
- [ ] restore-on-boot reflects toggles+params; fetch failure → DOM defaults
- [ ] debounced PUT pins captured `symbol`+`interval`
- [ ] `sma`/`ema` default 20 == prior `sma20`/`ema20`
- [ ] single write path (#68); WS `update()` only
- [ ] CSP clean, no inline script; no new dep; `src/` framework-free
- [ ] patch 100%; ruff + `pytest` + `makemigrations --check` green

## WU1 — Model + migration + guard (PR1)

Base `develop`; branch `feat/chart-config-model`; deps none. Rollback: revert branch → drop `ChartLayout` + migration `0005` (additive).

- [ ] 1.1 **RED** guard: `OWNED_MODELS += {"ChartLayout"}` + negative-control `ChartLayout.objects.all()`; isolation A≠B `DoesNotExist`; model: duplicate `IntegrityError`, intervals coexist, JSON round-trip.
- [ ] 1.2 **GREEN** `models.py`: `ChartLayout(UserOwnedModel)` — `symbol`(32), `interval`(8), JSONField `indicators`(default=list), `updated_at` auto_now, `UniqueConstraint(["user","symbol","interval"])`.
- [ ] 1.3 **GREEN** migration `0005_chartlayout.py`, depends `0004_private_snapshots`.
- [ ] 1.4 **REFACTOR** ruff clean; `makemigrations --check` green.

## WU2 — Endpoint + validation (PR2)

Base: PR1 branch (or `develop`); deps WU1. Rollback: remove `api_layout` + route + `parse_layout_indicators`; revert endpoint tests.

- [ ] 2.1 **RED** `test_market_api.py`: anon→302; GET default `exists:false`; PUT→GET `exists:true`; upsert one row; invalid token/param/interval/symbol→400 no write; A≠B→default; CSRF.
- [ ] 2.2 **GREEN** `quotes.py`: `DEFAULT_LAYOUT=[{sma},{ema},{rsi}]`; `parse_layout_indicators(list)` raising `ValueError`, token∈`REGISTRY`, params via `_parse_params`.
- [ ] 2.3 **GREEN** `views.py`: `api_layout` GET/PUT `@login_required`; validate before write →400; else `for_user(...).update_or_create(symbol=,interval=,defaults=indicators)`; GET miss→`DEFAULT_LAYOUT`, `exists:false`.
- [ ] 2.4 **GREEN** `urls.py`: `path("market/api/layout", views.api_layout, name="market_api_layout")`.
- [ ] 2.5 **REFACTOR** endpoint tests green.

## WU3 — Adapter boot + param UI + E2E (PR3)

Base: PR2 branch (or `develop`); deps WU2. Rollback: restore `chart.js`/`chart.html`; revert E2E file.

- [ ] 3.1 **RED** `test_market_e2e.py`: seed layout→reload restores toggles/panes; toggle→one debounced PUT; fetch failure→DOM defaults; switch loads layout.
- [ ] 3.2 **GREEN** `chart.js`: async `boot()` fetch layout → sync panel+state → `buildChart(); connect(); fetchHistory()`, `.catch→readIndicators()`; `switchTo` loads layout; debounced ~500 ms PUT `{symbol,interval,indicators}`; `sma20→sma`/`ema20→ema`; params from `.indicator-param`.
- [ ] 3.3 **GREEN** `chart.html`: CSRF meta in head; native `<input type="number" class="indicator-param">` per toggle; token values; design tokens.
- [ ] 3.4 **VERIFY** E2E green; `/impeccable` audit.

## Phase 4 — Verification

- [ ] 4.1 `pytest` green; patch 100%; ruff clean; `makemigrations --check` green.
- [ ] 4.2 Boundary + order-scanner green; CSP + `requirements.txt` unchanged.
- [ ] 4.3 Playwright: restore-on-boot, toggle persists, no console errors.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ~90, PR2 ~120, PR3 ~160 → ~330–420 |
| Suggested split | PR1 → PR2 → PR3 |
| Delivery strategy | ask-on-risk |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Medium
