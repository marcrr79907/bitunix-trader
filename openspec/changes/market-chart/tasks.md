# Tasks: market-chart

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Guard/Edge Matrix (every row = a test in its WU)

- [ ] `kline` maps ms → unix-seconds int + floats (R1)
- [ ] Empty upstream → `[]` client-side; 200-empty payload endpoint-side (R1/R3)
- [ ] `BitunixError` surfaces (API code != 0, HTTP != 200) (R1)
- [ ] Candles sorted ascending + deduped, last wins (R3)
- [ ] Overlays gap-omitted — `{time, value}` only, no nulls (R3/R4)
- [ ] sma20 has exactly N−w+1 points (R4)
- [ ] rsi14 in [0, 100] or point omitted (R4)
- [ ] 400 invalid interval (not in `INTERVALS`) (R3)
- [ ] 400 limit outside [1, 200] or non-int (R3)
- [ ] 502 `{"error": "upstream"}` on `RequestException`; never 500 (R3)
- [ ] 302 anonymous → login (page + API) (R2/R3)
- [ ] CSP present on `/market/` (authenticated) (R6)
- [ ] CSP absent on `/admin/` (R6)
- [ ] `/healthz` still 200 (R6)
- [ ] `/market/kline` matches no order-scanner forbidden fragment (R7)
- [ ] `src/` framework-free (`tests/test_boundary.py` green) (R7)
- [ ] No new runtime dep — `requirements.txt` unchanged (R7)
- [ ] `chart.js` has NO indicator math (R4)

## WU1 (PR1) — backend: kline client + market API

Base `feat/market-chart` (tracker). Depends: none. Strict TDD (`python -m pytest`). Headless-verifiable (~300 lines).

- [ ] 1.1 **RED** `tests/test_client_kline.py`: public GET URL/params, no signing; ms→s int + float mapping; API code != 0 → `BitunixError`; HTTP != 200 → `BitunixError`; empty `data` → `[]`. Monkeypatch `requests.get`; no Django.
- [ ] 1.2 **RED** `tests/web/test_market_api.py` (payload): stub client into `quotes.get_kline_payload` — candles ascending + deduped; overlays `{time, value}` no nulls; sma20 N−w+1 points; rsi14 bounded or omitted.
- [ ] 1.3 **RED** same file (endpoint): 200 exact shape; 400 invalid interval; 400 limit outside [1,200] / non-int; 400 upstream API reject; 502 on `RequestException`; 302 anonymous. View errors via monkeypatched `market.views.BitunixClient`.
- [ ] 1.4 **GREEN** `src/client.py`: `kline(symbol, interval="1m", limit=100)` after `funding_rate_batch` — unsigned public GET, one mapping seam (ms→s int, floats), `[]` on empty, `BitunixError` via `_unwrap`. No `startTime`/`endTime`/`type`.
- [ ] 1.5 **GREEN** `web/market/` app: `__init__.py`, `apps.py`, `quotes.py` (`INTERVALS` + `get_kline_payload` sort/dedupe + `_zip` gap omission), `views.py` (`market_page`, `api_kline`, `chart_js`; `@login_required` + GET-only), `urls.py` (bare names, no `app_name`).
- [ ] 1.6 **GREEN** `web/config/urls.py`: `include("market.urls")`; `web/config/settings/base.py`: `INSTALLED_APPS += "market"`.
- [ ] 1.7 **GREEN** `tests/web/test_credentials_mechanism.py`: `REQUEST_PATH += (WEB / "market",)` — scanner completeness.
- [ ] 1.8 Full suite + `ruff check` green; endpoint usable via curl.
- [ ] 1.9 **Rollback**: delete `web/market/` + the two new test files; revert `client.py`, `urls.py`, `base.py`, `test_credentials_mechanism.py`. No migrations (A4) — nothing at the DB layer.

## WU2 (PR2) — frontend: chart page, WS client, CSP

Base WU1 branch. Depends: WU1. Strict TDD. Browser-verifiable (~350 lines).

- [ ] 2.1 **RED** `tests/web/test_market_ux.py`: `/market/` 200 + chart container; home link; anonymous 302; CSP present on `/market/` + absent on `/admin/`; `/healthz` 200. `force_login` pattern (`test_ux.py`).
- [ ] 2.2 **RED** `tests/web/test_market_e2e.py`: `@pytest.mark.e2e` DOM-only — `LightweightCharts` global defined, canvas exists, no console errors on load (WS errors tolerated).
- [ ] 2.3 **GREEN** `web/market/templates/market/chart.html`: Variant A chart-first, extends `registration/base.html`, CDN pinned `@5.2.0`, side panel (pairs buttons + interval select + RSI readout).
- [ ] 2.4 **GREEN** `web/market/templates/market/chart.js` (~120 lines): WS lifecycle per design — bucketing, unsubscribe-BEFORE-subscribe, backoff 1s·2ⁿ cap 60s ±50% jitter, REST refetch on bucket advance (debounce); v5 `addSeries`; NO indicator math.
- [ ] 2.5 **GREEN** `web/config/middleware.py`: `ContentSecurityPolicyMiddleware` (path-conditional, `CSP_EXEMPT = ("/admin/",)`), last in `MIDDLEWARE` (`base.py`).
- [ ] 2.6 **GREEN** `web/accounts/templates/accounts/home.html`: replace stub text with `/market/` link.
- [ ] 2.7 **GREEN** `pyproject.toml`: `e2e` marker + `addopts = "-q -m 'not e2e'"`; `requirements-dev.txt`: `pytest-playwright>=0.5`. CI unchanged.
- [ ] 2.8 Full suite green (e2e deselected); locally `playwright install chromium` once, then `python -m pytest -m e2e`.
- [ ] 2.9 **LIVE-VERIFY (apply time)**: WS channel-name map for intervals > 30m (`1h` → `market_kline_60min`?) — only `1min` was spike-verified; correct `chFor()` before sign-off.
- [ ] 2.10 **Rollback**: revert `home.html`, `middleware.py`, `base.py` MIDDLEWARE, `pyproject.toml`, `requirements-dev.txt`; delete `chart.html`, `chart.js`, UX/E2E suites. WU1 untouched.

## Phase 3 — Verification

- [ ] 3.1 `python -m pytest` green under Strict TDD (e2e deselected by default).
- [ ] 3.2 `ruff check . && ruff format --check .` green.
- [ ] 3.3 `tests/test_boundary.py` green; order scanner clean; `requirements.txt` unchanged.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | WU1 ~300, WU2 ~350 → ~600–650 total |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (backend, headless) → PR2 (frontend, browser); each targets prior branch |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |
| Tracker branch | `feat/market-chart` → merges to `develop` |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High
