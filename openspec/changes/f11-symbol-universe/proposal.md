# Proposal: f11-symbol-universe

Issue #124, Fase F11 (Ola 5). Branch `feat/f11-symbol-universe` off `develop` @
`81e469b`. Read-only repo: **no order execution, ever**. Companion change
`f11-layout-templates` takes the other half of #124.

## Intent

`/market/` only knows the 4 pairs in `BITUNIX_SYMBOLS` (`config.py:47-49`):
`chart.html:14-18` renders a static nav, and `alerts._pair_error`
(`web/market/alerts.py:47`) rejects anything else. Users cannot reach the rest
of the exchange, and the existing `Watchlist` model
(`trading/models.py:130-144`) has no API.

Two of the four #124 deliverables are already shipped: per-symbol drawings
(`0012_drawing_per_symbol`) and persisted SMC toggles (`0013`). The real
coupling is **ingestion → firing**, not visualization: a new pair charts and
paginates today (`quotes._fetch_window` is DB-first with upstream gap-fill), but
its alerts can never fire until the worker persists closed candles for it
(`worker.py:145-196` reads the DB only). That is A-S3's job.

Owner decision: search covers **every** BitUnix pair; a watchlist symbol gets
full functionality (chart, history, alerts); exchange history MUST NOT be
duplicated into SQLite — it keeps coming from upstream on demand.

## Scope

### In Scope — four slices

- **A-S1 — Symbol catalog.** `web/market/catalog.py`:
  `list_symbols(client=None, *, now=None)` over `client.tickers()` (no-arg
  already returns the whole universe, `client.py:118-120`), module cache with
  `CATALOG_TTL_SECONDS = 60`, `symbol_exists()`. `GET /market/api/symbols`,
  `@login_required`, GET-only, 502 `{"error":"upstream"}` on failure.
- **A-S2 — Watchlist CRUD + alert validation.** `GET/POST
  /market/api/watchlist`, `DELETE /market/api/watchlist/<symbol>`. GET returns
  `{"symbols": [...], "default": bool}`; an empty list falls back **virtually**
  to `config.SYMBOLS` (`default: true`) — no seeding, GET must not write.
  POST is idempotent `get_or_create`, 400 for unknown/malformed symbol; cap
  `MAX_WATCHLIST_SYMBOLS = 50`, same value as the ingest cap in `config.py`.
  Every access via `Watchlist.for_user` (R14). `alerts._pair_error`
  becomes catalog-based:
  reject when the catalog is warm and the symbol is absent; when cold,
  fail-open on `^[A-Z0-9]{2,24}$` and let the worker skip it.
- **A-S3 — Watchlist ingestion.** Pure `due_intervals(now, last_poll)` in
  `web/trading/candles.py` (only intervals whose bucket rolled over). Worker
  tracks `last_poll` per symbol in memory; ingests the union of `config.SYMBOLS`
  (first, never starved) plus sorted watchlist symbols, capped at 50. The union
  read lives in `web/worker.py`, mirroring `run_alert_rules`.
- **A-S4 — Search + watchlist UI.** Pure `symbol-search-core.js`
  (`filterSymbols`, exact → prefix → substring, then alphabetical, capped 50)
  and a new leaf controller `controllers/symbol-picker.js` (combobox
  roles/keyboard, follow/unfollow, emits the existing `config:changed`).
  `chart.html`'s `<nav class="pairs">` becomes the watchlist section; the
  picker is additive. Allowlists + `docs/architecture/chart-modules.md` +
  `theme.css` using existing tokens.

### Out of Scope (explicit)

- **Layout templates** — deferred to `f11-layout-templates`.
- **Backfilling exchange history into SQLite** — owner decision; `_fetch_window`
  already serves older bars from upstream.
- **HTML alert-rule form** — `forms.py:24` `ChoiceField` over `SYMBOLS` stays.
- **Order execution** — never; the repo stays read-only.
- New dependency, client method, CSP relaxation, store key or bus event; no new
  table for the catalog or `last_poll`; no migration (none needed).

## Capabilities

### New Capabilities
- `symbol-catalog`: the exchange-wide symbol list, its 60 s cache, and the
  read-only JSON endpoint.

### Modified Capabilities
- `market-watchlist`: gains CRUD transport, the virtual default fallback, and
  the 50-symbol cap — R14.5/R14.7 entity and scoping rules unchanged.
- `alert-rules`: validation moves from `SYMBOLS` membership to the catalog,
  with the documented cold-cache fail-open.
- `market-ingestion`: ingest set becomes the union of defaults + watchlist,
  scheduled by `due_intervals` under the 50-symbol cap.
- `market-chart`: **R14** inventory +1 core +1 controller; toolbar selector
  contract (`class="pair"`, `data-symbol`) preserved.

## Approach

- **A-S1**: project only symbol strings from the ticker payload, so the response
  stays a few KB. 60 s process-local cache (single process per
  `docs/deployment.md`). `client`/`now` injectable for tests (stub pattern of
  `test_ingest.py:60`). Rejected: DB table (duplicates exchange data), no cache
  (an upstream call per keystroke).
- **A-S2**: the model and unique constraint exist, already in `OWNED_MODELS` —
  **no migration**. Virtual default keeps one source of truth and keeps env
  changes visible. Fail-open alert validation is safe because a rule is owned,
  never shared, never an order, and the worker already skips intervals it does
  not know (`worker.py:167-168`).
- **A-S3**: `due_intervals` cuts the steady-state rate from the naive
  13.3 req/s at 50 symbols to ~0.25 req/s. Restart burst (400 requests ≈ 40 s
  at the 10 req/s limit) is absorbed by the existing cycle throttle; no
  persisted `last_poll`. **No backfill.**
- **A-S4**: keep search logic in the pure core so the controller stays DOM-only
  and well under 300 lines. `toolbar.js` (187) is not rewritten →
  `toolbar.js:29-33` and the three E2E selectors (`test_market_e2e.py:1908,
  :2007, :2176`) keep passing unchanged.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/market/catalog.py` | New | universe fetch, TTL cache, `symbol_exists` |
| `web/market/urls.py` | Modified | +4 routes (symbols, watchlist GET/POST, DELETE) |
| `web/market/views.py` | Modified | allowlists + symbol/watchlist API glue |
| `web/market/alerts.py:44-55` | Modified | catalog-based `_pair_error` |
| `web/worker.py`, `web/trading/candles.py` | Modified | union ingest set, `due_intervals` |
| `src/config.py` | Modified | `MAX_INGEST_SYMBOLS = 50` shared cap |
| `market/symbol-search-core.js` | New | pure filter/rank |
| `market/controllers/symbol-picker.js` | New | combobox, follow/unfollow |
| `market/chart.html`, `registration/theme.css`, `market/main.js` | Modified | watchlist section, styles, wiring |
| `docs/architecture/chart-modules.md` | Modified | inventory |
| `tests/js/*`, `tests/web/*` | Modified | cores, APIs, ingest budget, UX, E2E |

## Rollback Plan

Per slice, independently revertible; no migration, no schema, no dependency.

- **A-S1**: delete `catalog.py`, the `/api/symbols` route and its view; the UI
  falls back to the server-rendered nav.
- **A-S2**: delete the watchlist routes/views and the `_pair_error` change
  (restore `symbol not in SYMBOLS`); existing `Watchlist` rows stay valid but
  unused — nothing to reverse.
- **A-S3**: revert the worker union line (`worker.py:204`) and
  `due_intervals`; ingestion returns to `config.SYMBOLS`. No schema touched.
- **A-S4**: revert the picker module/controller and markup; **keep
  `class="pair"` / `data-symbol`**, so `toolbar.js` and the E2E selectors keep
  working before, during and after.

Feature-branch chain → drop the tracker branch before any merge to `develop`.
Reconfiguring `BITUNIX_SYMBOLS` is never destructive.

## Risks

| Risk | L | Mitigation |
|------|---|------------|
| Upstream catalog size/latency (300+ pairs; slow first call) | Med | 60 s cache; 502 on failure; UI falls back to the server-rendered default list so the chart never blocks |
| Restart burst at 50 symbols (400 req ≈ 40 s) | Med | Accepted and documented; the cycle's error handling already backs off (`worker.py:215-220`) |
| Fail-open alert validation admits a typo symbol | Low | Harmless owned row; worker skips it; spec states this so it is not "fixed" into a per-request network call |
| E2E flake #149 (SQLite threaded) | Med | Verify by DOM + captured request, never pixels |
| Module ceiling (300 lines) | High | New controller stays DOM-only; pure core carries the search logic |
| Request-rate budget at 50 symbols | High | `due_intervals` + cap + throttle → ~0.25 req/s; negative test proves bypassing it exceeds the limit |
| Watchlist removal vs. `config.SYMBOLS` | Low | A default symbol keeps ingesting (correct: it is the operator's set) |

## Dependencies

- Existing public `client.tickers()`; existing `Watchlist` model/constraint.
- `f11-layout-templates` is independent and shares no files with the slices
  above (only the #124 issue).

## Success Criteria

- [ ] `/api/symbols` returns the full universe, cached, auth-gated, 502 on
      upstream failure.
- [ ] Watchlist CRUD is idempotent, `for_user`-scoped, capped at 50; an empty
      list reports `default: true` without writing rows.
- [ ] A watched symbol's alert fires after the worker ingests its closed candles;
      no exchange history is backfilled.
- [ ] `filterSymbols` covered by node tests; search swaps the chart; follow adds
      a watchlist row.
- [ ] `class="pair"`/`data-symbol` preserved, E2E selectors green, `toolbar.js`
      byte-untouched; `pytest` + `node --test` green, ruff clean, no migration.
