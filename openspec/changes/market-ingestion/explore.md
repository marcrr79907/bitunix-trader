# Exploration: market-ingestion (Phase 3)

**Change**: `market-ingestion`
**Date**: 2026-10-07
**Mode**: investigation only. No code written.
**Architecture memory**: `#1291` — GLOBAL = `Candle`/`FundingSnapshot`/`TickerSnapshot` (single ingestion for all users); per-user = `ExchangeCredential`, `Watchlist`, `AlertRule`, `PositionSnapshot`, `Trade`, `AccountSnapshot`. Worker was to use "RQ + scheduler". This phase turns the **global** half and the **worker stub** real.

## Executive Summary

Phase 0 shipped `web/worker.py`/`web/scheduler.py` as boot-only stubs (`redis.ping()` then idle). Phase 3 makes the worker a real **global market ingester**: it polls the two read-only public endpoints the client already exposes (tickers + funding) on an interval and persists time-series snapshots for all users. The lazy, evidence-backed slice is **two global models** — `FundingSnapshot` + `TickerSnapshot` — living in the existing `trading` app, plus one small ingestion module and a real worker loop. **No `Candle` model**: no OHLC/kline endpoint exists in `src/client.py` (grep: zero `candle|ohlc|kline` hits). **No RQ**: a single periodic task does not justify a broker + job serialization; a plain loop with backoff covers Phase 3. `src/` stays untouched and framework-free; the worker (web/) imports the core.

---

## Current State (read, not guessed)

| Area | Fact | Source |
|---|---|---|
| Read endpoints | Public: `tickers(symbols)`, `funding_rate_batch()` (ignores symbols, returns all). No OHLC/kline/candle anywhere | `src/client.py:118-124` |
| Core schema | SQLite `funding_snapshots` (ts,symbol,funding_rate,mark_price,index_price,next_funding_time,funding_interval), `price_snapshots` (ts,symbol,last_price,high,low,quote_vol), `trades` (global, no user) | `src/db.py:11-46` |
| Core fetch/persist | `fetch_rows(client, symbols)` builds one dict/symbol (display + persistence keys), stamps `ts = int(time.time()*1000)` internally; `persist(conn, rows)` inserts both tables | `src/monitor.py:45-77,87-116` |
| Core loop | CLI loop with backoff `min(backoff*2, 300)` and `POLL_SECONDS=30`; rich Live UI; KeyboardInterrupt exit | `src/monitor.py:243-281`, `src/config.py:23` |
| Worker | Stub: `ping_redis()` then `idle_loop(iterations)` sleeping 30s; `main(iterations)` returns 0 | `web/worker.py:21-48` |
| Scheduler | Stub importing `worker.idle_loop`; `main()` logs + idle | `web/scheduler.py:11-18` |
| Worker tests | `test_stub_boots_and_idles` monkeypatches `redis.Redis.ping`, asserts `main(iterations=1)==0` | `tests/web/test_service_stubs.py:13-26` |
| Trading app | Already installed; owns `UserOwnedModel` (abstract, `user` FK + `for_user`) + `ExchangeCredential`, `Watchlist`; migration `0001_initial` | `web/trading/models.py`, `web/trading/migrations/0001_initial.py` |
| Worker never touches Django | No `django.setup()`, no ORM import; no `web/` module imports `src/` yet | `web/worker.py`, grep `from src` in `web/` → 0 |
| Timezone | `TIME_ZONE = "UTC"`, `USE_TZ = True` | `web/config/settings/base.py:124-127` |
| Runtime deps | requests, rich, Django, psycopg, dj-database-url, gunicorn, redis, cryptography — **no `rq`** | `requirements.txt` |
| CI gates | `ruff`, `makemigrations --check`, pytest + coverage, web gate ≥85%, **patch gate diff-cover 100%**; separate `core-isolation` job installs only requests+rich and imports every `src/*.py` with Django absent | `.github/workflows/ci.yml:39-106` |

---

## 1. Which global models belong in Phase 3

**Recommendation: exactly two — `FundingSnapshot` and `TickerSnapshot` — in the existing `trading` app.** They mirror the two core tables 1:1 and are fed by the two endpoints the client already has.

### `FundingSnapshot` (fed by `client.funding_rate_batch()`)
| Field | Type | Note |
|---|---|---|
| `symbol` | `CharField(max_length=32)` | e.g. `BTCUSDT`, `1000PEPEUSDT` |
| `ts` | `DateTimeField` | snapshot time, UTC (worker clock) |
| `funding_rate` | `FloatField(null=True)` | `fundingRate` |
| `mark_price` | `FloatField(null=True)` | `markPrice` |
| `index_price` | `FloatField(null=True)` | `indexPrice` |
| `next_funding_time` | `BigIntegerField(null=True)` | epoch ms (`nextFundingTime`) |
| `funding_interval` | `IntegerField(null=True)` | hours (`fundingInterval`) |

### `TickerSnapshot` (fed by `client.tickers(symbols)`)
| Field | Type | Note |
|---|---|---|
| `symbol` | `CharField(max_length=32)` | |
| `ts` | `DateTimeField` | same poll instant |
| `last_price` | `FloatField(null=True)` | `lastPrice` |
| `high` | `FloatField(null=True)` | 24h |
| `low` | `FloatField(null=True)` | 24h |
| `quote_vol` | `FloatField(null=True)` | `quoteVol` |

**Idempotency / uniqueness**: one `UniqueConstraint(fields=["symbol", "ts"], name=...)` per model. A re-run of the same poll instant (retry, double worker) inserts nothing; use `bulk_create(..., ignore_conflicts=True)`. This is the same key the core uses implicitly (`ix_*_symbol_ts`) but enforced instead of merely indexed.

**Indexes**: the unique `(symbol, ts)` covers `ix_funding_symbol_ts` / `ix_price_symbol_ts` reads. No extra index (YAGNI).

**Why NOT `Candle` now**: no OHLC/kline endpoint is used — `src/client.py` exposes only `tickers` + `funding_rate_batch` (grep confirms zero candle/ohlc/kline references). A `Candle` model would have no producer; adding it is speculative. **Defer to the phase that adds an OHLC endpoint** (or builds candles from ticks, which needs a bucketing design). YAGNI.

**Why two, not one**: they are fed by two different endpoints, have different columns, and different update cadence semantics (`TickerSnapshot` is price/volume, `FundingSnapshot` is rate/mark/index). Collapsing them would create a wide sparse table and lose the natural `(symbol, ts)` idempotency per series. Two narrow tables match the core's proven shape.

**Read endpoints feeding each**: `FundingSnapshot` ← `/market/funding_rate/batch`; `TickerSnapshot` ← `/market/tickers`. Both public, read-only, **no API key required** (`src/monitor.py:246` public-only mode).

**App placement (lazy)**: put both in `trading`. It is already installed, migrated, and scanned; no new app, no `INSTALLED_APPS` edit, no `REQUEST_PATH` (credential scanner) or `OWNED_MODELS` (guard) change — these global models are **not** `UserOwnedModel` and carry no `user` FK. Alternative: a new `market` app. Cost: another app + settings + scanner wiring; benefit: cleaner global-vs-per-user split. **Recommend `trading` now**; split only if the app grows a second concern (it already holds per-user data, so a `market` split is defensible in Phase 4 when the API/UI lands).

---

## 2. Ingestion service design

**Placement**: one small module `web/trading/ingest.py` (worker-zone, request-free). Two functions behind a narrow interface — the test seam:

```python
# web/trading/ingest.py  (illustrative)
def fetch_market(client, symbols) -> dict[str, list[dict]]:
    # calls client.tickers(symbols) + client.funding_rate_batch()
    # returns {"funding": [...], "tickers": [...]} as model kwargs

def persist_market(funding: list[dict], tickers: list[dict]) -> tuple[int, int]:
    # bulk_create(ignore_conflicts=True); returns (inserted_funding, inserted_tickers)
```

**Fetch via `src/client.py`, read-only**: reuse the existing client. Two options:
- (a) Reuse `src.monitor.fetch_rows(client, symbols)` — it already merges tickers+funding into one dict/symbol with all persistence keys (`src/monitor.py:45-77`). Laziest; the worker maps its dict to the two model shapes. Caveat: it stamps `ts` internally via `time.time()` (`:48`) and pulls `rich` (already a runtime dep).
- (b) Call `client.tickers()` / `client.funding_rate_batch()` directly in `fetch_market`, taking an injectable `now` for the clock.

**Recommend (a)** for the fetch (reuse, no new parsing, one source of truth for field names), and keep `persist_market(rows, ...)` taking the already-stamped rows so idempotency is testable **without a clock seam** (persist the same rows twice → second is a no-op). If design wants an explicit injectable clock, wrap `monitor.fetch_rows` — do not fork the parser.

**Persistence**: Django ORM, `bulk_create(ignore_conflicts=True)` inside one transaction. Insert counts returned for logging/observability.

**Clock/timestamp**: core uses epoch **ms `int`**; web uses `USE_TZ=True` **UTC** (`base.py:127`). Convert once at the boundary: `datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc)`. Keep `next_funding_time` as raw epoch ms `BigIntegerField` (no conversion — it is an API value, not a snapshot time). Do **not** reuse `src/db.py`: it is a stdlib SQLite schema for the CLI, not an ORM; the CLI keeps its own store unchanged (R10).

**Test WITHOUT network**: `persist_market` is tested directly with hand-built dicts (round-trip + duplicate → 1 row). `fetch_market` is tested with a **monkeypatched/stub client** (an object whose `tickers()`/`funding_rate_batch()` return fixtures) — one test, no socket. The worker loop test injects the stub client too.

---

## 3. Worker real loop

**Recommendation: plain loop, no RQ.** Replace the idle body with: boot (`django.setup()` + `ping_redis()`), then a poll loop calling `fetch_market`/`persist_market` on an interval, with exponential backoff on `BitunixError`/`RequestException` (copy the proven `min(backoff*2, 300)` pattern from `src/monitor.py:275-277`), structured logging, and clean SIGTERM/SIGINT shutdown.

```python
# web/worker.py  (illustrative shape)
POLL_SECONDS = int(os.environ.get("INGEST_POLL_SECONDS", "30"))

def run_once(client, symbols) -> tuple[int, int]: ...   # fetch + persist
def run_loop(client, symbols=None, iterations=None, stop=None) -> int: ...
def main(iterations=None) -> int: ...
```

**Why no RQ** (tradeoffs): RQ adds a runtime dependency, a broker job model, and serialization for what is **one periodic task with no fan-out**. A plain loop is ~30 lines, trivially testable, and deploys as the existing `worker` service. RQ becomes worth it when there are **multiple job types / concurrency / API-triggered work** (e.g. Phase 4 on-demand refreshes), or when retry/observability requirements outgrow logs. Defer until then; **add no new runtime dependency** (mirrors the Phase 1/2 "no new runtime dep" success criterion, `patch-coverage-gate` R5).

**Config**: `INGEST_POLL_SECONDS` (default 30, matches `src/config.py:23`). Symbols: reuse `src.config.SYMBOLS` / `DEFAULT_SYMBOLS` (`src/config.py:18,47-49`) — single source, no duplication. No API key needed (public endpoints).

**Observability**: log one line per cycle (`symbols=N funding=K tickers=K`), one on error with the backoff value, one on shutdown. Reuse `logging.basicConfig` already in `web/worker.py:15`.

**Clean shutdown**: install `signal` handlers for SIGTERM/SIGINT that flip a `stop` flag; loop exits between cycles (do **not** kill mid-transaction). Return 0. This is what Railway needs to redeploy without a hard kill.

**Test change**: `tests/web/test_service_stubs.py` currently asserts `worker.main(iterations=1)==0` with a mocked Redis ping. It **must change** because `main` now performs ingestion. New shape: keep the `fake_redis` ping stub, inject a fake client (monkeypatched `src.client.BitunixClient` methods returning fixtures), and assert `main(iterations=1)` returns 0 and wrote N rows (use `pytest.mark.django_db`). Add a backoff/shutdown unit test on `run_loop` with a client that raises once. The `scheduler` parametrization must be removed from this test (scheduler stays a stub) or kept in a separate stub test.

---

## 4. Scheduler

**Recommendation: the worker owns the loop; the scheduler stays a stub.** Phase 3 has a single periodic concern, and the worker service already exists and is deployed (`docker-compose.yml:47-56`, R7 requires three bootable services). A separate scheduler buys nothing until there are **multiple jobs to dispatch** — either fold the scheduler's role into the worker or have it enqueue jobs when RQ lands. Lazy now: leave `web/scheduler.py` as the boot-only stub (R7 still satisfied); do not add scheduling machinery.

Note: `scheduler.py` imports `worker.idle_loop` (`web/scheduler.py:11`). If the worker's idle loop is renamed/removed, keep a compatible `idle_loop` or update scheduler in the same change so both still boot.

---

## 5. Boundary

- `src/` **stays framework-free**: no `src/` change is required by this phase. The ingestion module lives in `web/` and calls the core as a library. The `core-isolation` CI job (`ci.yml:72-106`) installs only `requests` + `rich`, asserts `django` is absent from `sys.modules`, and imports every `src/*.py`. It stays green **as long as no `src/` file imports Django** (`tests/test_boundary.py:50-53` guards the same statically).
- **Direction**: `web/` (worker, ingest, models) MAY import `src.client` / `src.config` / `src.monitor`; the reverse MUST NOT happen. This change adds the **first `web/ → src/` import** — the intended direction, but new, so the boundary tests are the regression guard.
- Worker Django bootstrap: worker.py must `os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")` + `django.setup()` before importing `trading.models`. `docker-compose.yml:51` already sets the env var for the worker service.
- The worker is the **trusted zone** (R14.4): global models carry no `user` FK, so the per-user guard's `OWNED_MODELS` set (`tests/web/test_owned_model_guard.py:20`) needs no change.

---

## 6. Migration

- **Additive**: two new tables in `trading` → `web/trading/migrations/0002_<name>.py`. No data migration, no changes to `accounts` or the existing `trading` tables.
- **CI gate**: `makemigrations --check --dry-run` (`ci.yml:61`) MUST stay green → commit the generated migration in the same change.
- **Portable fields only** (`CharField`, `FloatField`, `BigIntegerField`, `DateTimeField`, `UniqueConstraint`) so Postgres (prod) and SQLite (dev/tests) agree.
- **Naming/global-vs-per-user**: global models MUST NOT inherit `UserOwnedModel` (`web/trading/models.py:16`) and MUST NOT have a `user` FK. Keep them clearly named (`FundingSnapshot`, `TickerSnapshot`) and, if design wants explicit separation, group them in a `MarketSnapshot` section or a `market.py` module inside `trading`. The Phase-2 `Trade` collision note is **irrelevant here** (that is a future per-user model vs `src/db.py`'s SQLite `trades`); no `Trade` is added in this phase.

---

## 7. Scope boundaries

### In
- `FundingSnapshot` + `TickerSnapshot` global models + additive migration (`trading/0002_*`).
- `web/trading/ingest.py`: `fetch_market` (reuses core/client, read-only) + `persist_market` (`bulk_create ignore_conflicts`, unique `(symbol, ts)`).
- Real `web/worker.py` loop: interval config, exponential backoff, logging, SIGTERM/SIGINT clean shutdown.
- Tests (Strict TDD): ingest round-trip + idempotency; worker loop with injected stub client + backoff/shutdown; updated `test_service_stubs.py`.
- Reuse `src.client`, `src.monitor.fetch_rows`, `src.config.SYMBOLS` unchanged.

### Out (Phase 4+)
- `Candle` model / OHLC ingestion (no endpoint).
- RQ / Celery / job queue; scheduler becomes real.
- JSON API / DRF, UI/charts, alerts/notifications.
- Per-user `PositionSnapshot`, `AccountSnapshot`, `Trade`, `AlertRule`.
- Retention/pruning job (see Risks — size it in design, prune later).
- Any order execution — **HARD invariant, never**.
- `MultiFernet` key rotation.

---

## 8. Risks & open questions

| # | Risk / question | Note |
|---|---|---|
| R1 | **Data volume / retention.** 4 symbols × 2 tables × (86400/30s) = ~11,520 snapshot rows/day/table, growing unbounded. | Decide retention in design (e.g. keep N days, or downsample). Lazy: ship without pruning, flag it; add a prune management command later. Do NOT silently accumulate forever in prod. |
| R2 | **First `web/ → src/` import.** Worker now imports core; if a `src/` module ever imports Django the `core-isolation` job fails. | Boundary tests already guard (`tests/test_boundary.py`, `ci.yml` core-isolation). No action beyond staying green. |
| R3 | **UTC correctness.** Core stamps epoch ms with `time.time()`; Django stores `DateTimeField` under `USE_TZ=True`. | Convert once at the boundary (`fromtimestamp(ms/1000, tz=utc)`); never mix naive datetimes. Keep `next_funding_time` raw ms. |
| R4 | **Idempotency key `(symbol, ts)` precision.** `DateTimeField` uses microsecond precision; worker clock is ms. Two workers started same second → same key → dedup works. | Good enough. If double-ingest is a concern, a single worker service (R7) already prevents it. |
| R5 | **`test_service_stubs.py` rewrite scope.** Existing test asserts the idle contract; the worker contract changes. | Must update the test; keep a scheduler boot test if the scheduler stays a stub. |
| R6 | **Reuse `src/monitor.fetch_rows` pulls `rich`** and stamps `ts` internally (no clock injection). | Accept (rich is already a runtime dep). If a clock seam is needed for deterministic tests, wrap it — do not fork the parser. |
| R7 | **No new runtime dep.** Adding RQ would break the "no new runtime dependency" success criterion and expand CI/CD. | Plain loop; revisit RQ only with multi-job needs. |
| R8 | **Web coverage gate (≥85%) and patch gate (100%).** Every new line needs a test — worker loop lines (sleep/backoff/shutdown) are coverage-hostile. | Structure loops with injectable `iterations`/`stop`/`sleep` so tests exercise every branch; avoid long real sleeps. |
| R9 | **App placement `trading` vs new `market` app.** `trading` already mixes credentials/watchlist (per-user); adding global models grows its concerns. | Recommend `trading` now (no wiring cost); split in Phase 4 if desired. Design decides. |
| R10 | **`scheduler.py` shares `worker.idle_loop`.** Renaming/removing it breaks scheduler boot (R7). | Keep a compatible `idle_loop` or update both files together. |

---

## Affected Areas

- `web/trading/models.py` — add `FundingSnapshot`, `TickerSnapshot` (modify)
- `web/trading/migrations/0002_*.py` — additive schema (create)
- `web/trading/ingest.py` — fetch + persist (create)
- `web/worker.py` — real loop: Django setup, backoff, signals (modify)
- `web/scheduler.py` — unchanged (stub) or minor compat if `idle_loop` changes (modify)
- `tests/web/test_service_stubs.py` — rewrite worker contract (modify)
- `tests/web/test_ingest.py` — round-trip + idempotency + loop (create)
- `src/`, `web/accounts/`, `web/credentials.py`, `web/config/`, `requirements.txt` — **unchanged**

## Recommendation

Proceed to **proposal → spec → design** with In-scope = {`FundingSnapshot`, `TickerSnapshot` in `trading`, `ingest.py`, real worker loop}, no `Candle`, no RQ, scheduler stays a stub, no new runtime dependency. Resolve in design: (a) app placement (`trading` vs new `market`), (b) retention policy (ship-without-prune vs a prune command), (c) whether to reuse `src.monitor.fetch_rows` vs a direct client call with a clock seam.

## Ready for Proposal

**Yes** — with three design decisions above. This is a well-bounded, additive phase; the main open question is retention, which is a design/policy choice, not a blocker.

---

## Evidence Index

- `src/client.py:118-124` — the only two market endpoints used; no OHLC.
- `src/db.py:11-46` — core global schema shape being mirrored.
- `src/monitor.py:45-77,87-116,243-281` — fetch/persist/backoff patterns to reuse.
- `src/config.py:18,23,47-49` — symbols + poll interval.
- `web/worker.py:21-48`, `web/scheduler.py:11-18` — stubs to make real / leave.
- `web/trading/models.py:16-30` — `UserOwnedModel` (global models must NOT inherit it).
- `web/config/settings/base.py:124-127` — UTC + `USE_TZ`.
- `tests/web/test_service_stubs.py:13-26` — worker test to rewrite.
- `tests/web/test_owned_model_guard.py:20` — owned-model set (unaffected by global models).
- `.github/workflows/ci.yml:39-106` — test, coverage/patch gates, `core-isolation`.
- `requirements.txt` — no `rq`; `requirements-dev.txt` — `diff-cover` dev-only.
- Engram `#1291` — global vs per-user model split and 9-phase plan.
