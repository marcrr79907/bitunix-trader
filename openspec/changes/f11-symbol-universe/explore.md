# Exploration: f11-symbol-universe

Issue #124 (F11, Ola 5), first of two changes. Branch `feat/f11-symbol-universe`
off `develop` @ `81e469b`. Read-only exploration: no app code changed.
Companion change `f11-layout-templates` covers the layout-template half of #124.

## 1. Problem framing

Issue #124 lists four deliverables. Two are already shipped by Ola 3:

| Deliverable | State | Evidence |
|---|---|---|
| Drawings per symbol (not per interval) | DONE | migration `0012_drawing_per_symbol.py`; `Drawing` keyed `(user, symbol)` with `ix_drawing_user_symbol` |
| SMC toggles persisted | DONE | `ChartPreference.smc` JSONField, migration `0013` |
| Symbol search over the exchange universe | **MISSING** | `chart.html:14-18` is a static `<nav class="pairs">` of `config.SYMBOLS` |
| Layout templates | **MISSING** | no template model, no endpoint (deferred to `f11-layout-templates`) |

Owner decision (2026-10-18): the search must cover **every pair BitUnix offers**,
and any symbol the user adds to their watchlist must get **full functionality**
(chart, history, alerts) — but exchange history MUST NOT be duplicated into
SQLite. History keeps coming from upstream on demand.

## 2. Current state (cited)

### Symbol universe plumbing

| Concern | Where | Behavior |
|---|---|---|
| Configured symbols | `src/config.py:47-49` | `SYMBOLS` = `BITUNIX_SYMBOLS` env or `DEFAULT_SYMBOLS` (4 pairs) |
| Injected to the browser | `web/market/views.py:107`, `:567` → `chart.js:14` | `CONFIG.symbols` literal array |
| Pair nav | `chart.html:14-18` | one `<button class="pair" data-symbol>` per configured symbol |
| Pair wiring | `controllers/toolbar.js:29-33` | `querySelectorAll(".pair")` → `bus.emit("config:changed")` |
| All-pairs upstream call | `src/client.py:118-120` | `tickers(symbols=None)` omits the param → every pair |
| Precedent for "all pairs" | `src/monitor.py:230-233` | already calls `client.tickers(extra)` for unconfigured position symbols |

**Finding 2.1.** `client.tickers()` with no argument already returns the whole
universe. No new client method, no new dependency, no auth needed (public GET,
`client.py:88-95`).

### What actually blocks a new symbol today

| Capability | Blocked by | Evidence |
|---|---|---|
| Chart + history | **Nothing.** Works today for any pair. | `quotes._fetch_window` (`quotes.py:559-587`) is DB-first with upstream gap-fill; `_db_rows` returns `[]` for unpersisted intervals and the upstream fills the window |
| Alert rules | `alerts._pair_error` rejects any symbol outside `SYMBOLS` | `web/market/alerts.py:47` (`if symbol not in SYMBOLS: return "invalid symbol"`) |
| Alert **firing** | Worker reads candles from the DB only | `worker.run_alert_rules` (`worker.py:145-196`) → `market.quotes._db_rows` — no upstream fallback |
| Candle persistence | Worker ingests `config.SYMBOLS` only | `worker.py:204` → `run_once(client, symbols)` → `candles.fetch_closed_candles` |

**Finding 2.2 (key).** The real coupling is **ingestion → firing**, not
visualization. A watchlist symbol can render its chart and history immediately,
but cannot fire an alert until the worker persists its candles. That is A-S3's
whole job. Confirms the owner's instinct: the heavy, unnecessary thing would be
storing full history; the necessary thing is persisting only *closed* candles so
alert evaluation has a deterministic window.

### Ingestion cost model

`candles.fetch_closed_candles` (`candles.py:48-75`) issues one `kline` request per
symbol × interval per cycle, `CANDLE_INTERVALS` = 8 (`5m,15m,1h,2h,4h,1d,1w,1M`).
Poll is `INGEST_POLL_SECONDS = 30` (`worker.py:14`).

| Symbols | Requests / 30s cycle | Rate | vs 10 req/s limit |
|---|---|---|---|
| 4 (today) | 32 | 1.07 req/s | OK |
| 10 | 80 | 2.67 req/s | OK |
| 25 | 200 | 6.67 req/s | OK |
| **50** | **400** | **13.3 req/s** | **OVER** |

Naive scaling breaks at ~37 symbols. This is the measured ceiling the plan must
respect.

### Derived artifact inventory

`Candle` is written **once per closed bucket per symbol×interval**, not a full
history: `limit=2` is requested and only elapsed buckets are kept
(`candles.py:62-72`). Steady state for one symbol is bounded by
`sum(1/interval)` rows per second ≈ `0.0049 rows/s` ≈ 424 rows/day. Four symbols
≈ 1.7k rows/day. Fifty symbols ≈ 21k rows/day — the same order as the existing
tick snapshots (`FundingSnapshot`/`TickerSnapshot`, every 30s × symbols). So a
50-symbol watchlist costs **comparable** storage to what the worker already
writes today; the risk is request rate, not disk.

## 3. Slice feasibility

### A-S1 — Symbol catalog (`web/market/catalog.py`)

- `list_symbols(client=None, *, now=None) -> list[str]`: `sorted({t["symbol"] for t in client.tickers()})`.
- Module-level cache `(fetched_at, symbols)` with `CATALOG_TTL_SECONDS = 60`;
  `now` injectable so tests never sleep. `client` injectable so tests never hit
  the network (the project's established stub pattern: `tests/web/test_ingest.py:60`).
- `symbol_exists(symbol, *, client=None) -> bool` over the cached set.
- `GET /market/api/symbols` → `{"symbols": [...]}`; `@login_required`,
  GET-only. Upstream failure → 502 `{"error": "upstream"}`, mirroring
  `api_kline` (`views.py:207-212`).
- **Payload size risk:** the full ticker payload is large but only the symbol
  strings are cached and returned, so the response is a few KB. Cache is
  process-local (single-process dev/prod per `docs/deployment.md`), so no
  cross-worker invalidation concern.

Alternatives rejected: caching in the DB (adds a table for data the exchange
already serves, contradicts the owner's "don't duplicate" stance); no cache
(one upstream call per keystroke is unacceptable).

### A-S2 — Watchlist CRUD

- Model exists (`trading/models.py:130-144`), unique `(user, symbol)`, already in
  `OWNED_MODELS` (`tests/web/test_owned_model_guard.py:25`). **No migration.**
- `GET /market/api/watchlist` → `{"symbols": [...], "default": bool}`.
  - Empty list → return `config.SYMBOLS` virtually with `"default": true`.
  - **Decision: return virtually, do not seed rows.** Seeding would (a) require
    a write on a GET, violating the project's GET-is-read contract, and (b) make
    a later `BITUNIX_SYMBOLS` change invisible to existing users. Virtual
    fallback keeps one source of truth and needs no data migration.
- `POST /market/api/watchlist` `{symbol}` → 201, idempotent (`get_or_create`),
  400 for a symbol absent from the catalog, 400 for a malformed symbol.
- `DELETE /market/api/watchlist/<symbol>` → 204, idempotent.
- Cap: `MAX_WATCHLIST_SYMBOLS = 50` → 400 with a clear error when exceeded.
  This is the same number as the ingest cap so the two cannot disagree
  (single constant source: reuse `MAX_INGEST_SYMBOLS`).
- Every access through `Watchlist.for_user(request.user)` (R14).

#### Alerts validation change (`alerts._pair_error`, `alerts.py:44-55`)

Current rule `symbol not in SYMBOLS → 400` must become catalog-based. Design:

1. If the catalog is **warm** and the symbol is absent → 400 `invalid symbol`.
2. If the catalog is **cold/unavailable** → accept any symbol matching
   `^[A-Z0-9]{2,24}$`, write the rule, and let the worker skip it until
   ingestion covers it.

Why fail-open here is safe: an `AlertRule` is per-user owned data, never shared,
never executed as an order, and the worker already skips rules whose interval is
not in `CANDLE_INTERVALS` (`worker.py:167-168`). Worst case is a dead rule, not a
leak or a write outside the caller's scope. The rule is documented in the spec so
nobody "fixes" it into a per-request network call later.

Blast radius elsewhere: `forms.py:24` (HTML rule form) is a `ChoiceField` over
`SYMBOLS`; it stays as-is (a Django form cannot enumerate 300+ pairs sensibly) and
is out of scope. `backfill_candles.py:175` stays operator-driven.

### A-S3 — Watchlist ingestion (worker)

- Pure helper in `candles.py`: `due_intervals(now, last_poll) -> tuple[str, ...]`
  returning only intervals where `now // span != last_poll // span`. No sleeping,
  no clock read inside (injected).
- Worker keeps a `last_poll` per symbol (in-memory dict, reset on restart).
  On restart every interval is "due" once → an 8-request burst per symbol.
  With a 50-symbol cap that is 400 requests; the existing 30s cycle plus a
  throttle keeps it under the limit but takes several cycles to settle.
  **Decision: on startup, persist nothing special and let the throttle absorb
  the burst.** Documented cost: up to ~40 s of catch-up at 10 req/s.
- `MAX_INGEST_SYMBOLS = 50`, deterministic ordering: `config.SYMBOLS` first
  (never starved), then watchlist symbols sorted alphabetically until the cap.
- Union read happens in `web/worker.py` (trust zone, unscoped allowed per R14.4),
  mirroring `run_alert_rules` (`worker.py:162`).
- Request-rate arithmetic after `due_intervals` at 50 symbols:
  `50 × 0.1483 closed-intervals-per-30s-cycle ≈ 7.4 requests / 30s ≈ 0.25 req/s`
  — a ~53× reduction vs the naive 13.3 req/s, comfortably under 10 req/s.
- **No backfill.** Unchanged: the chart's older bars come from upstream via
  `_fetch_window`. The owner's constraint is encoded here explicitly.

### A-S4 — Search + watchlist UI

- `symbol-search-core.js` (pure, imports nothing):
  `filterSymbols(query, symbols, limit=50) -> string[]`.
  Ranking: exact match → prefix match → substring match, then alphabetical.
  Case-insensitive; empty/whitespace query → all (capped).
- `controllers/symbol-picker.js` (new, leaf, `create({store, bus, config})`):
  - `<input role="combobox" aria-expanded aria-controls aria-activedescendant>`
    + `<ul role="listbox">` of up to 50 options, `aria-live` result count.
  - Keyboard: `ArrowDown/ArrowUp` move the active option, `Enter` selects,
    `Escape` closes. Focus stays in the input (combobox pattern, not roving).
  - Follow/unfollow toggles per row → POST/DELETE watchlist.
  - Selection emits the **existing** `config:changed` bus command — no new
    event, no new store key, no new write path.
- `chart.html`: `<nav class="pairs">` becomes the watchlist section, still
  rendered server-side from `config.SYMBOLS` as the initial (default) list.
  **Keep `class="pair"` and `data-symbol` on the watchlist buttons** so the three
  existing E2E selectors (`test_market_e2e.py:1908, :2007, :2176`) keep working
  and `toolbar.js:29-33` needs no change. The picker is additive.
- Size: `toolbar.js` is 187 lines — the picker goes in a NEW controller rather
  than growing it toward the 300 ceiling.
- `MODULE_ALLOWLIST` += `symbol-search-core`; `CONTROLLER_ALLOWLIST` +=
  `symbol-picker`; `docs/architecture/chart-modules.md` inventory updated.
- CSS in `web/accounts/templates/registration/theme.css` using existing tokens
  (`--surface`, `--border`, `--text`, `--sp-2`), matching `.pairs .pair`
  (`theme.css:139-140`).

## 4. Decisions and alternatives

| Decision | Choice | Alternative rejected | Why |
|---|---|---|---|
| Universe source | `client.tickers()` no-arg, cached 60s | New exchange-metadata endpoint | Already exists and is public (`client.py:118`) |
| Empty watchlist | Virtual fallback to `config.SYMBOLS`, `default:true` | Seed rows on first read | GET must not write; env changes must stay visible |
| Watchlist cap | 50, shared by ingest and API | Unlimited | Keeps request rate bounded and the two limits consistent |
| Alert validation when cold | Fail-open on a format regex | Block the rule | A dead per-user rule is harmless; a per-request network call is not |
| Ingestion scheduling | `due_intervals` + cap + throttle | Poll all intervals every cycle | 13.3 req/s breaks the 10 req/s budget at 50 symbols |
| History for new symbols | Upstream on demand | Backfill into SQLite | Owner's explicit constraint; `_fetch_window` already does it |
| UI integration | New controller + additive picker | Rewrite `toolbar.js` | `toolbar.js` is 187/300 lines; a rewrite risks 3 E2E selectors |
| Restart burst | Absorb via throttle | Persist `last_poll` | A new table/column for a ~40 s transient |

## 5. Risks

1. **Upstream catalog size/latency.** If `tickers()` returns 300+ pairs the
   response is still small after projection, but the *first* request may be
   slow. Mitigation: 60 s cache + 502 on failure; the UI falls back to the
   server-rendered default list so the chart never blocks.
2. **Restart burst at 50 symbols** (400 requests ≈ 40 s at 10 req/s). Accepted
   and documented; the cycle's own error handling already backs off
   (`worker.py:215-220`).
3. **`api_alerts` fail-open could admit a typo symbol.** Harmless (owned row,
   worker skips it), but the spec must say so explicitly.
4. **E2E flake #149** (SQLite threaded). Verify by DOM + captured request, never
   pixels.
5. **Module ceiling.** A new controller must stay well under 300 lines; the pure
   core carries the search logic so the controller stays DOM-only.
6. **Watchlist changes vs. worker**: a symbol removed from the watchlist but
   still in `config.SYMBOLS` keeps being ingested (correct — it is the operator's
   default set).

## 6. Test strategy

| Layer | What | Where |
|---|---|---|
| Node (pure) | `filterSymbols` ranking/caps/case/empty | `tests/js/symbol-search-core.test.js` |
| Django | catalog cache TTL + failure, `/api/symbols` auth + 502 | `tests/web/test_market_catalog.py` |
| Django | watchlist CRUD matrix, isolation A≠B, cap, default fallback | `tests/web/test_market_watchlist.py` |
| Django | alerts accept a catalog symbol, reject unknown-when-warm, fail-open when cold | extend `tests/web/test_market_alerts_api.py` |
| Python | `due_intervals` table-driven; ingest union + cap ordering; request-count budget | `tests/web/test_candles.py`, `tests/web/test_worker_ingest.py` |
| Django | markup: combobox roles, no inline script, module/controller routes resolve | extend `tests/web/test_market_ux.py` |
| E2E (dev-only) | search → select swaps the chart; follow adds a watchlist row | `tests/web/test_market_e2e.py` |

Negative controls: a test proving `filterSymbols` can return fewer results than
input (so the filter is not a pass-through), and a test proving the ingest budget
exceeds the limit if `due_intervals` is bypassed (so the guard is real).

## 7. Estimated size

| Slice | Prod lines | Test lines | Total |
|---|---|---|---|
| A-S1 catalog + route | ~70 | ~90 | ~160 |
| A-S2 watchlist API + alerts change | ~110 | ~160 | ~270 |
| A-S3 ingest scheduling | ~90 | ~130 | ~220 |
| A-S4 search + watchlist UI | ~200 | ~170 | ~370 |
| **Total** | **~470** | **~550** | **~1020** |

Over the 400-line review budget → chained PRs, `feature-branch-chain`, tracker
`feat/f11-symbol-universe`. S1+S2 ≈ 430 (split if the API test file grows);
S3 and S4 are standalone.

## 8. Open questions

None blocking. Two defaults are recorded above and can be revisited in the
proposal if the owner disagrees: (a) the 50-symbol cap, (b) fail-open alert
validation when the catalog is cold.
