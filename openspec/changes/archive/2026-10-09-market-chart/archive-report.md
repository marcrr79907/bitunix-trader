# Archive Report: market-chart

**Archived**: 2026-10-09
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 criticals) — 7/7 requirements, 20/24 scenarios, 241/241 tests
**Delivery**: single PR #40 (`size:exception`, maintainer-approved) → `develop`
**Merged commit range**: `5b69260`…`2dad92a` on `develop` (merge commit `2dad92a`, PR head `b83cbaf`)

## What Shipped

Phase 4 delivers the market dashboard the home page had been stubbing
("Market dashboard coming in the next phase"): an auth-gated, real-time chart
page. OHLC history + indicator overlays are computed server-side by Django
(`src/indicators.py`, single source of truth) and served as JSON; live candles
flow browser-direct from BitUnix's public WebSocket (no Channels proxy). New
screaming-domain Django app `web/market/`, one read-only `kline()` client
method, a path-conditional CSP header, and a dev-only Playwright DOM smoke.
Personal-first, strictly read-only, candles ephemeral (no model, no migration).

| Area | Delivered |
|------|-----------|
| kline client | `src/client.py` — `kline(symbol, interval, limit)` under public endpoints (unsigned GET), one mapping seam ms→unix-seconds int + floats, `[]` on empty, `BitunixError` via `_unwrap` |
| Market app | `web/market/` — `views.py` (`market_page`, `api_kline`, `chart_js`; `@login_required` + GET-only), `urls.py`, `quotes.py` (`INTERVALS` + `get_kline_payload` sort/dedupe + `_zip` gap omission) |
| Chart UI | `web/market/templates/market/chart.html` (Variant A chart-first, CDN-pinned Lightweight Charts `@5.2.0`) + `chart.js` (WS lifecycle: bucketing, unsubscribe-before-subscribe, capped+jittered backoff, 20s ping keepalive) |
| CSP | `web/config/middleware.py` — `ContentSecurityPolicyMiddleware`, path-conditional (`CSP_EXEMPT = ("/admin/",)`), last in `MIDDLEWARE`; healthz bypassed by earlier host middleware |
| Wiring | `web/config/urls.py` include; `base.py` `INSTALLED_APPS += "market"`; `home.html` link to `/market/` |
| Startup fix | `web/manage.py::_ensure_project_paths()` — makes `src` importable without `PYTHONPATH` (closed the verify CRITICAL) |
| Tests | `tests/test_client_kline.py` (7), `tests/web/test_market_api.py` (11), `tests/web/test_market_ux.py` (8), `tests/web/test_market_e2e.py` (1), `tests/web/test_manage_boot.py` (1); `test_credentials_mechanism.py` `REQUEST_PATH += web/market` |

## Requirement Outcomes

| Req | Domain | Outcome | Notes |
|-----|--------|---------|-------|
| R1 | market-chart | ✅ Green | Public unsigned GET URL/params; ms→s int + floats; API code != 0 / HTTP != 200 → `BitunixError`; empty/null → `[]` |
| R2 | market-chart | ✅ Green | Anonymous → 302 login (page); authenticated renders chart container + pairs/intervals |
| R3 | market-chart | ✅ Green | Candles sorted + deduped (last wins); uniform `{time,value}` overlays, no nulls; 400 invalid interval/limit/symbol; 502 `{"error":"upstream"}`; 200 empty; never 500; anonymous → 302 |
| R4 | market-chart | ✅ Green | Overlays only from `src/indicators.py`; `_zip` drops `None`; sma20 exactly N−w+1; rsi14 bounded `[0,100]` or omitted; no JS math |
| R5 | market-chart | ⚠️ Partial | E2E DOM smoke passes (real chromium); 3 runtime behaviors (bucketing, unsubscribe-first, reconnect backoff) verified by static inspection only — no runtime test (W1) |
| R6 | market-chart | ✅ Green | CSP present on `/market/` with wss + CDN + self allowlist; `script-src` has no `'unsafe-inline'`; absent on `/admin/`; `/healthz` still 200 |
| R7 | market-chart | ⚠️ Partial | Boundary green (4), order scanner clean (36), `requirements.txt` diff empty; "runtime deps unchanged" verified by `git diff` only, no covering test (W2) |

**Legend**: ✅ green · ⚠️ partial (invariant holds; test-coverage gap).

## Carry-Forward Items

1. **Candle persistence and multi-user WS proxy deferred (A4/A5)** — candles are
   ephemeral by design (no `Candle` model, no migration); the Django Channels
   multi-user proxy was deferred, so the browser connects directly to the public
   WS. Revisit only if multi-user real-time demand appears; adds redis/channels
   infra.
2. **Snapshot retention is still the standing Phase 3 debt** — `market-ingestion`
   archive item #1 remains open: `FundingSnapshot`/`TickerSnapshot` accumulate
   ~11,520 rows/table/day. `market-chart` does not touch the worker or snapshots;
   unrelated tables, but the debt persists. ⚠️ **DO NOT lose this item.**
3. **WS channel names for intervals >30m — live-verified at apply (task 2.9)** —
   design flagged `1h → market_kline_60min` etc. as unverified past the `1min`
   spike. At apply (2026-10-08) official SDK enums + live socket probes confirmed
   the map as designed (60min/2h/1day/3day/1week/1month all push); no `chFor()`
   change was needed. The server additionally requires a 20s ping keepalive
   (added). **Recorded here as resolved evidence.**
4. **`chart.js` line-budget drift (SUGGESTION 1)** — shipped 192 lines vs the
   design's ~120–140 forecast; extra is the channel map, ping keepalive, and
   interval helper. No business math. Correct the design estimate if reused as a
   template.
5. **`web/manage.py` is excluded from coverage (SUGGESTION 3)** — `pyproject.toml`
   `[tool.coverage.run].omit` excludes `manage.py`, so the fix that closed the
   CRITICAL is invisible to the patch/web gates; its behavior is locked by
   `tests/web/test_manage_boot.py`. Drop it from `omit` if coverage instrumentation
   for the bootstrap is ever wanted.

## Verify Findings (non-blocking, fix before the noted trigger)

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| C1 | Critical | `python web/manage.py check` / `makemigrations` failed with `ModuleNotFoundError: No module named 'src'` (CI L1, no `PYTHONPATH`) | ✅ **Closed in-change** — `5163125` (`manage.py::_ensure_project_paths()`) + `tests/web/test_manage_boot.py`; re-verified from repo root and a foreign cwd, no CI-workflow workaround |
| W1 | Low | 3 R5 JS-runtime scenarios (forming-candle bucketing, unsubscribe-before-subscribe, reconnect backoff) have no runtime test; E2E is DOM-only | Open — add a JS unit test or an E2E that drives an interval switch and asserts frame order; else mark them inspection-verified |
| W2 | Low | R7 "runtime dependencies unchanged" has no covering test (verified by empty `git diff` only) | Open — add a runtime-import guard test mirroring market-ingestion W4 |
| S1 | Suggestion | `chart.js` is 192 lines vs the ~120–140 design forecast | Documented — modest, no business logic |
| S2 | Suggestion | E2E assertion filters all `net::`/`WebSocket` console errors, could mask a dead CDN or misrouted fetch | Consider narrowing the filter to the known WS/fetch noise; chart-global assertion still catches a dead CDN |
| S3 | Suggestion | `web/manage.py` omitted from coverage, so the patch gate does not measure the C1 fix | Note only; behavior locked by the boot subprocess test |

**Apply-era design bugs caught and fixed in-change** (recorded for the audit trail):
- **Template autoescape** — the page JS receiving symbol data was corrected to
  render JSON safely (`{{ symbols|safe }}` fix) rather than emitting escaped
  entities into the script body.
- **WS idle disconnect** — the server drops idle sockets; a 20s ping keepalive was
  added to `chart.js` (found during the apply-time live check, task 2.9).

## SDD Cycle Complete

Planned → implemented → verified (re-verified: prior FAIL with 1 CRITICAL closed)
→ merged (PR #40) → archived.
Delta spec merged into the main spec store:

- `openspec/specs/market-chart/spec.md` (new capability — full spec, R1–R7, 24 scenarios)

No existing capability was modified (`core-domain-boundary` R9 and
`security-invariants` R11/R12 were constraints to satisfy, not alter).

Archive audit trail: `openspec/changes/archive/2026-10-09-market-chart/`
(explore, proposal, design, specs, tasks, verify-report).

## Traceability — Engram Observation IDs

| Artifact | Observation ID |
|----------|----------------|
| `sdd/market-chart/explore` | 1347 |
| `sdd/market-chart/proposal` | 1348 |
| `sdd/market-chart/spec` | 1349 |
| `sdd/market-chart/design` | 1350 |
| `sdd/market-chart/tasks` | 1351 |
| `sdd/market-chart/ws-channel-live-verification` | 1352 |
| `sdd/market-chart/apply-progress` | 1353 |
| `sdd/market-chart/verify-report` | 1355 |
| `sdd/market-chart/archive-report` | 1357 |

Merged specs have no standalone Engram observations — they live in the OpenSpec
file store (`openspec/specs/market-chart/spec.md`).
