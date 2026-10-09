# Proposal: market-chart

## Intent

Phase 4 delivers the market dashboard the home page has been stubbing
("Market dashboard coming in the next phase"). The user needs a real-time,
auth-gated chart page: OHLC history + indicator overlays from Django, live
candles straight from BitUnix's public WebSocket in the browser. Personal-first
(single admin user), strictly read-only, ephemeral candles.

## Scope

### In Scope
- New Django app `web/market/`: chart page view (`/market/`, login_required,
  Variant A chart-first layout), `/market/api/kline` JSON endpoint, template.
- `src/client.py`: read-only `kline(symbol, interval, limit)` — public
  endpoint, ms → unix-seconds mapping, float normalization, no sockets in tests.
- `/market/api/kline` payload: `candles` (sorted/deduped ascending,
  `{time, open, high, low, close}`) + `overlays` (`{time, value}`, gaps
  omitted) computed server-side via `src/indicators.py`.
- Live candles: browser connects DIRECTLY to `wss://fapi.bitunix.com/public/`
  (A1) — subscribe/unsubscribe lifecycle, interval-switch ordering
  (unsubscribe first), forming-candle bucketing, capped backoff reconnect.
- Lightweight Charts v5.2.0 via CDN, pinned (A2).
- Minimal CSP header (custom middleware): script/style CDN allowlist + wss
  connect-src; `/admin/*` unaffected.
- `pytest-playwright` dev-only + DOM-assertion E2E smoke (excluded from CI L1).
- INSTALLED_APPS + root urls + home link; tests (Strict TDD).

### Out of Scope
- Django Channels / multi-user WS proxy (A5 deferred).
- `Candle` model, persistence, migrations (A4 — candles are ephemeral).
- Indicator math in JS (single-source server-side; forming candle renders
  without overlay until close).
- `startTime`/`endTime`/`type` kline params (YAGNI until needed).
- Order execution (HARD invariant, never). Alerts, RSI/ATR panes,
  multi-symbol simultaneous streams (pairs table switches the chart).

## Capabilities

### New Capabilities
- `market-chart`: auth-gated chart page + kline JSON API + read-only kline
  client method + live WS candles + minimal CSP + dev-only E2E smoke.

### Modified Capabilities
- None. (`core-domain-boundary` R9, `security-invariants` R11/R12 are
  constraints to satisfy, not alter — `web/market` imports `src`, read-only
  market GET, no secrets.)

## Approach

Reuse-first: `kline()` joins the public endpoints in `src/client.py` (one
mapping point, ms→s); the endpoint delegates to a `web/market/quotes.py`
payload builder accepting a stub-able client (`fetch_market(client, symbols)`
pattern); indicators zip server-side with omitted `None` gaps. Browser JS is
vanilla (~80 lines): REST history on load/switch, WS updates the forming
candle via interval bucketing. CSP is a ~15-line middleware, no new runtime
dependency. `src/` stays framework-free; boundary + order-surface scanners
stay green (`/market/kline` matches no forbidden path fragment).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/client.py` | Modified | add `kline()` under public market endpoints |
| `web/market/` | New | app: views, urls, `quotes.py`, template |
| `web/config/urls.py` | Modified | include `market.urls` |
| `web/config/settings/base.py` | Modified | INSTALLED_APPS += `market` |
| `web/config/middleware.py` | Modified | CSP header (path-conditional for `/admin/*`) |
| `web/accounts/templates/accounts/home.html` | Modified | link to `/market/` |
| `tests/` + `tests/web/` | New | kline mapping, payload, API, UX, CSP suites |
| `requirements-dev.txt` | Modified | `pytest-playwright` (dev-only) |
| `.github/workflows/ci.yml` | Unchanged (or optional e2e job) | L1 excludes `-m "not e2e"` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| CSP breaks Django admin (inline handlers) | Med | path-conditional header; admin + healthz regression tests |
| WS reconnect storm on blip | Med | capped exponential backoff + jitter; single user |
| v5 vs v4 CDN API drift | Low | pin `@5.2.0`; v5 `addSeries` form; E2E asserts global |
| Duplicate/unordered `time` throws in chart | Med | sort+dedupe server-side; bucket WS `ts` |
| Symbol not found | Low | 400 generic error, tested |
| Playwright flakiness in CI | Low | dev-only, separate invocation, not in coverage run |

## Rollback Plan

Revert the branch: delete `web/market/`, remove `market` from INSTALLED_APPS
and `urls.py`, remove `kline()` + CSP middleware, restore `home.html` +
`requirements-dev.txt`. No migrations exist (A4) — nothing to roll back at the
DB layer. Existing suites (`accounts`, `trading`, core) are untouched.

## Dependencies

- External service: BitUnix public REST + WS (no auth, rate limit 10 req/s/ip).
- CDN availability for `lightweight-charts@5.2.0` (browser-side only).

## Success Criteria

- [ ] `python -m pytest` green; new suites pass Strict TDD; patch gate 100%.
- [ ] `/market/` auth-gated; anonymous → login; chart renders for user.
- [ ] `/market/api/kline` returns sorted/deduped candles + gap-free overlays.
- [ ] Live WS candles update the forming candle without duplicates.
- [ ] Interval switch unsubscribes before subscribing.
- [ ] CSP header present on market pages; admin login + `/healthz` unaffected.
- [ ] Runtime `requirements.txt` unchanged; boundary + order-scan green.

## Review Workload Forecast

- Estimated diff: **~600–800 changed lines** (new app + template + JS ~300,
  client method + tests ~300, CSP ~50).
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High
