# Exploration: candle-store (issue #43)

**Change**: `candle-store`
**Date**: 2026-10-09
**Mode**: investigation only. No code written.
**Issue**: gh#43 — market-dataset: persistir velas OHLC + backfill histórico.

## Executive Summary

Today candles are EPHEMERAL: `chart.js` → `/market/api/kline` → `quotes.get_kline_payload` → `client.kline()` → BitUnix REST on every page load; nothing is persisted (market-chart A4). This change supersedes that for the data tier: a global `Candle` model in the `trading` app, an extended `kline()` with `start_time`/`end_time`, a resumable `backfill_candles` management command paginating backward via `endTime`, and continuous closed-candle ingestion in the worker's existing 30s loop. Interval set confirmed by the user: **5m, 15m, 1h, 2h, 4h, 1d, 1w, 1M** (no 1m — 1m would multiply the driver volume ×5). Backfill driver is 5m: 4 symbols × ~3y × 105,120 bars/yr ≈ 1.26M rows, ~25k requests, ~40 min at 10 req/s with throttling. Ticks 30s (`FundingSnapshot`/`TickerSnapshot`) stay as-is but are eliminated from the long-term dataset strategy — candles ARE the dataset.

## Current State (read, not guessed)

| Area | Fact | Source |
|---|---|---|
| Candles ephemeral | `api_kline` calls `get_kline_payload(BitunixClient(), ...)` per request; no persistence anywhere | `web/market/views.py:33-58`, `web/market/quotes.py:30-44` |
| `kline()` shape | `kline(symbol, interval="1m", limit=100)` — NO `start_time`/`end_time`; maps `time` ms→s + prices to float; **does NOT map `quoteVol`** although BitUnix returns it (live probe 2026-10-09 confirmed `"quoteVol": "3880565.68396"` in kline rows) | `src/client.py:126-138` |
| API contract | unsigned public GET `/api/v1/futures/market/kline`; HTTP!=200 or code!=0 → `BitunixError`; `data` null/[] → `[]` | `src/client.py:88-114`, `tests/test_client_kline.py` |
| Pagination | `endTime` paginates BACKWARD; `startTime` IGNORED (orchestrator live-probe). Max 200 rows/req, 10 req/s/ip. Depth ~3y (~2022-10 has data, ~2021-10 empty) | issue #43 + orchestrator probe |
| Worker loop | 30s global ingest loop (`fetch_market`/`persist_market`), backoff `min(backoff*2,300)`, `BitunixError`/`RequestException` handled, injectable `iterations/stop/sleep` | `web/worker.py:40-72` |
| Global-model pattern | `FundingSnapshot`/`TickerSnapshot` in `trading`: no user FK, not `UserOwnedModel`, `UniqueConstraint`, persisted via `bulk_create(ignore_conflicts=True)` + row-count delta | `web/trading/models.py:16-54`, `web/trading/ingest.py:65-83` |
| Management commands | **None exist** — no `web/trading/management/` dir; `web/manage.py` self-heals `sys.path` (repo root + web) | `ls web/trading/`, `web/manage.py:12-26` |
| Migrations | `trading` at `0002_market_snapshots`; CI runs `makemigrations --check --dry-run` | `web/trading/migrations/`, `.github/workflows/ci.yml:61` |
| Views/endpoints | `/market/api/kline` clamps limit [1,200] and rejects invalid interval/symbol before upstream | `web/market/views.py:22,33-58` |
| Coverage gates | web ≥85% floor, patch diff-cover 100% vs `origin/develop` — every new line needs a test | `.github/workflows/ci.yml:66-70` |
| Boots | `web/manage.py check` with no PYTHONPATH (regression test locks it) | `tests/web/test_manage_boot.py` |
| Snapshots consumers | Only `ingest.py` writes them; **nobody reads them today** → eliminated from long-term data strategy; loop must keep running (invariant) | issue #43, grep web/ |
| Deployment | worker = `python web/worker.py`, env `DJANGO_SETTINGS_MODULE=config.settings.prod`, Postgres via `DATABASE_URL` | `docs/deployment.md:64-71` |

## 1. Candle model

**Placement: app `trading`** — already installed, migrated, scanned; zero wiring cost (INSTALLED_APPS, settings, scanner). The `market` app is request-path/UI focused; a management command + worker module live naturally next to the snapshot models they mirror. Naming `Candle` (singular, domain term) matches `FundingSnapshot`/`TickerSnapshot` convention.

| Field | Type | Note |
|---|---|---|
| `symbol` | `CharField(max_length=32)` | e.g. `BTCUSDT`, `1000PEPEUSDT` |
| `interval` | `CharField(max_length=8)` | `5m`…`1M` (longest: `1M`=2 chars; 8 leaves headroom) |
| `time` | `BigIntegerField` | candle OPEN time, UNIX **seconds** (client already normalizes ms→s) |
| `open`/`high`/`low`/`close` | `FloatField` | BitUnix strings → float at the client seam |
| `quote_vol` | `FloatField(null=True)` | kline `quoteVol` — requires client mapping extension (see finding #1) |

- `UniqueConstraint(fields=["symbol","interval","time"], name="uniq_candle_symbol_interval_time")` — idempotency key; makes re-persist a no-op (same pattern as snapshots).
- `models.Index(fields=["symbol","interval","time"])` — explicit composite index for range pagination/queries (a unique constraint usually creates its own index on Postgres, but the explicit index documents intent and guarantees plan support for `WHERE symbol=? AND interval=? AND time BETWEEN ? AND ?`).
- No `user` FK, MUST NOT inherit `UserOwnedModel` (global shared data, R14 n/a). No `ts`/`DateTimeField` — candle time is the bucket start, seconds int is exact and portable (same choice as `next_funding_time` raw epoch in `FundingSnapshot`).

## 2. Migration

Additive: `web/trading/migrations/0003_candle.py` (auto-generated). Portable fields only (`CharField`, `BigIntegerField`, `FloatField`, `UniqueConstraint`, `Index`) — Postgres prod / SQLite dev agree. `makemigrations --check --dry-run` stays green (commit the migration in the same change). No data migration; existing snapshot tables untouched. `web/start.sh` runs `migrate --noinput` on deploy → table appears automatically.

## 3. kline() extension

```python
def kline(self, symbol, interval="1m", limit=100, start_time=None, end_time=None):
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time is not None:
        params["startTime"] = start_time  # epoch ms
    if end_time is not None:
        params["endTime"] = end_time      # epoch ms
```

- Backward compatible: default `None` → params identical to today (existing callers: `quotes.get_kline_payload`, tests, all pass).
- Raw epoch-ms values pass through unchanged (API unit); the s↔ms conversion lives where it is needed (backfill converts its stored seconds → ms).
- No signing (public endpoint, same `get()` path); `BitunixError` surfaces unchanged; empty/`null` data → `[]` unchanged.
- Extend the mapping to include `"quote_vol": float(r["quoteVol"])` — **required** by the model. Risk: rows missing `quoteVol` → use `r.get("quoteVol")` returning `None` → FloatField(null=True). Existing mapping tests assert exact dict equality — they MUST be updated (spec delta for `market-chart` R1).
- Tested without sockets: extend `tests/test_client_kline.py`'s `_capture_get` pattern (monkeypatch `requests.get`, capture `params`), plus one `KeyError`-guard test for missing `quoteVol`.

## 4. Backfill command

**Django requirements**: `web/trading/management/__init__.py`, `web/trading/management/commands/__init__.py` (both empty `__init__.py`), then `backfill_candles.py`. Coverage config omits `web/manage.py` but NOT management dirs → command needs tests (invoke `call_command("backfill_candles", ...)` with a stub client; inject `sleep`).

**Interface** (illustrative):
```
manage.py backfill_candles --symbol BTCUSDT --interval 5m --start 2022-10-01 --end <now|optional> --dry-run
```
- `--symbol` (repeatable or all-`SYMBOLS` default), `--interval` (one per run or loop the confirmed set), `--start`/`--end` optional bounds, `--dry-run` counts what would be fetched without writing.
- **Pagination loop**: `end_time = <cursor ms>`; call `kline(symbol, interval, 200, end_time=end_time)`; rows come back newest→oldest (backward). If no rows → **exhausted** (or `--start` reached) → stop. Else: persist batch (`bulk_create(ignore_conflicts=True)` — idempotent), `end_time = min(row.time)*1000 - 1`, repeat.
- **Resumability**: unique constraint makes re-run skip existing rows, but re-scanning the whole range is wasteful. Efficient resume: on start, query `Candle.objects.filter(symbol, interval).aggregate(Min("time"))`; if a row exists, begin from `min_time*1000 - 1` instead of `end` default (now). Partial backfill resumes exactly at the gap.
- **Throttling**: `time.sleep` between requests, default e.g. 0.15s (≈6-7 req/s < 10/s limit), injectable for tests. ~25k requests ≈ 40 min for the 5m driver.
- **Logging**: one line per page (`symbol=X interval=Y page_rows=200 cursor=...`), one per series completion (`inserted=N skipped(depth)`), one on exhaustion.
- **Errors**: `BitunixError`/`RequestException` → log + abort series (re-run resumes) — or bounded retry; keep it simple: abort with clear log, resumability covers it.

## 5. Continuous ingestion (worker)

Rate-limit arithmetic per 30s cycle: 4 symbols × 8 intervals = 32 kline requests/cycle ≈ 1.07 req/s average — **within** the 10 req/s budget, but a naive burst loop would hit the limit; space requests (small sleep between them) or interleave per symbol.

Options:
- **(a) Fetch every interval each cycle** (32 req/cycle): simple, faithful to BitUnix, but 31/32 of fetched rows are duplicates of already-stored buckets (only the last closed candle per interval is new each cycle, and coarse intervals only close every 2h/4h/1d...). Wasteful yet affordable.
- **(b) Persist only 5m, derive larger**: single fetch source, ~4 req/cycle, but requires aggregation math (bucketing, volume summation) — a new correctness surface and a fork from "what BitUnix actually says". The user's confirmed interval list is stored as candles regardless.
- **(c) Derive "closed" from candle `time`** — not an alternative to (a)/(b) but the closing rule: a candle whose bucket window has fully passed (bucket_start + interval ≤ now) is closed and safe to persist. **Recommend (a) + (c)**: each cycle, for each symbol×interval, fetch `limit=2` (candle in formation + last closed) and persist only candles whose `time + interval_seconds ≤ now` — cheap filter, no clock injection needed (testable with fixed fixtures).

**(a)+(c) recommendation**: direct persistence (matches the issue's "Se recomienda directo"), tiny request count with `limit=2`, bucket-boundary closure is a pure function (easy TDD), and BitUnix remains the single source of truth for all intervals (no aggregation bugs). Tick ingestion (funding/tickers) MUST keep running in the same loop — the change appends candle persistence to `run_once`/`ingest`, never replaces it. Worker stays the trusted zone; new code is read-only GETs + writes.

## 6. Storage sizing (per symbol/year, ×4 symbols)

| Interval | Bars/symbol/yr | ×4 symbols/yr |
|---|---|---|
| 5m | 105,120 | 420,480 |
| 15m | 35,040 | 140,160 |
| 1h | 8,760 | 35,040 |
| 2h | 4,380 | 17,520 |
| 4h | 2,190 | 8,760 |
| 1d | 365 | 1,460 |
| 1w | 52 | 208 |
| 1M | 12 | 48 |
| **Total** | **155,919** | **623,676 rows/yr** |

- **Backfill** (~3y depth × 4 symbols): ≈ **1.87M rows** total, of which 5m alone ≈ 1.26M (67%). ~25k requests for 5m; all intervals ≈ 9.4k pages of 200... recompute: 1.87M/200 ≈ 9.4k requests total (5m ≈ 6.3k), well under 40 min at 10 req/s with 0.15s sleeps (~23 min).
- **Continuous growth**: 623,676 rows/yr ≈ 1,709 rows/day across all intervals. Postgres row ~120-160 bytes with index → ~100 MB/yr order of magnitude. No retention/prune in this change (issue #45).

## 7. Scope boundaries

### In
- Global `Candle` model + additive migration `trading/0003_*`.
- `kline()` `start_time`/`end_time` params + `quote_vol` mapping.
- `backfill_candles` management command (idempotent, resumable, throttled, `--dry-run`).
- Worker closed-candle ingestion per confirmed interval set (5m…1M), appended to the existing loop.
- Tests (Strict TDD, no sockets): model constraints, kline params/mapping, backfill pagination/resume/idempotency via `call_command` + stub client, worker candle cycle, updated `test_client_kline.py` exact-dict assertions.

### Out
- Chart pagination / UI changes (issue #44) — `/market/api/kline` behavior unchanged.
- Retention/prune (issue #45).
- Pattern detection, backtesting, precomputed indicators.
- Per-user candles (R14 n/a — global data).
- Order execution (HARD invariant). New runtime dependencies (none).

## 8. Risks & open questions

| # | Risk / question | Note |
|---|---|---|
| R1 | kline mapping change breaks exact-dict tests + downstream consumers (`quotes.py` shape gains a key) | `quotes.get_kline_payload` builds candles dicts for the chart payload — extra `quote_vol` key would leak into the API payload. Decide in design: strip in quotes.py, or filter keys explicitly. Update `tests/test_client_kline.py` + `test_market_api.py` exact assertions. |
| R2 | Backfill duration/failure mid-run | ~23-40 min single run; abort-on-error + resumable via min(time) resume. Dry-run first. |
| R3 | Rate limit (10 req/s/ip) shared with live chart WS/REST and worker cycle | Throttle sleep default conservative (0.15s); worker cycle amortizes 32 req over 30s. |
| R4 | Patch coverage 100% — management command + pagination loop are coverage-hostile | Inject `sleep`; stub client; `call_command` tests; exhaustive-branch loop design. |
| R5 | `1M` monthly bucket boundary math | interval_seconds approximation (30d) only matters for closure heuristic; design should confirm closure rule for 1w/1M (e.g. persist when API's newer candle appears instead of wall-clock math). |
| R6 | Postgres prod / SQLite dev parity for big backfill (1.87M inserts) | `bulk_create` batching (~1-2k/batch); SQLite dev likely only partial backfill; document. |
| R7 | Snapshot tables (ticks) left growing with no consumer | Out of scope here (dataset = candles); flag for issue #45 retention. |
| Q1 | Should `--start` bound the backfill or run to full depth? | Default full depth; `--start` as optional cap. |
| Q2 | Worker candle fetch cadence — every cycle with `limit=2` (recommended) vs per-interval scheduling | Design decides; (a)+(c) recommended. |

## Affected Areas

- `web/trading/models.py` — add `Candle` (modify)
- `web/trading/migrations/0003_*.py` — additive schema (create)
- `web/trading/management/{__init__.py,commands/__init__.py,commands/backfill_candles.py}` — new command (create)
- `web/trading/ingest.py` or new `web/trading/candles.py` — closed-candle persistence helper (modify/create)
- `web/worker.py` — append candle cycle to `run_once`/loop (modify)
- `src/client.py` — `kline()` params + `quote_vol` mapping (modify)
- `web/market/quotes.py` — possibly strip new key from chart payload (modify, pending R1)
- `tests/test_client_kline.py`, `tests/web/test_ingest.py` (or new `test_candles.py`), `tests/web/test_worker_candles.py` — new/updated (modify/create)
- `docs/` volumetry note — create/modify
- `web/market/views.py`, `requirements.txt`, `web/scheduler.py` — **unchanged**

## Recommendation

Proceed to proposal with: `Candle` in `trading`, kline extension + `quote_vol`, backfill command (backward `endTime`, resumable, throttled), worker closed-candle ingestion via (a)+(c). Design resolves: payload-shape handling of `quote_vol` in `/market/api/kline` (R1), closure rule for 1w/1M (R5), batching strategy for the 1.87M-row backfill (R6).

## Ready for Proposal

**Yes** — no blockers. Open questions are design-level, none block scope.
