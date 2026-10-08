# Design: market-ingestion

## Technical Approach

The Phase-0 worker stub becomes a **global ingester**: boot Django, loop on an interval, calling one
narrow module that reuses the proven core (`src.monitor.fetch_rows`, `config.SYMBOLS`,
`client.BitunixClient`) and persists two new **global** models in `trading` via
`bulk_create(ignore_conflicts=True)`. The worker owns the loop; the scheduler stays a stub. Read-only.

## Data Model (`web/trading/models.py`)

Both GLOBAL — no `user` FK, NOT `UserOwnedModel`.

| Model | Fields |
|-------|--------|
| `FundingSnapshot` | `symbol` Char(32); `ts` DateTime (UTC); `funding_rate`/`mark_price`/`index_price` Float(null); `next_funding_time` BigInt(null, raw epoch ms); `funding_interval` Int(null) |
| `TickerSnapshot` | `symbol` Char(32); `ts` DateTime; `last_price`/`high`/`low`/`quote_vol` Float(null) |

Each `Meta.constraints = [UniqueConstraint(fields=["symbol","ts"], name="uniq_funding_symbol_ts" | "uniq_ticker_symbol_ts")]`.
The unique `(symbol, ts)` **covers the `ix_*_symbol_ts` reads — no extra index** (YAGNI). Migration
`web/trading/migrations/0002_market_snapshots.py` is additive (`CreateModel` ×2), no `accounts`
dependency, `makemigrations --check` green.

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|----------|--------|--------------|-----------|
| D1 | App placement | `trading` | New `market` app | Already installed/migrated/scanned, owns `UserOwnedModel` — zero wiring. `market` pays wiring for a split only needed once a second concern lands (Phase 4). |
| D2 | Retention | Ship **without** pruning; document + plan | Prune now | Deleting rows before any reader exists is speculative. Deferral explicit, not silent. |
| D3 | Fetch path | Reuse `src.monitor.fetch_rows` | Direct calls + injectable clock | One source of field names; no forked parser. It stamps `ts` via `time.time()`, so idempotency is proven at the **persist layer** (persist twice → no-op), no clock seam. |
| D4 | Execution | Plain loop | RQ/Celery | One periodic task, no fan-out, no new runtime dependency (R7). |

**Retention deferral (D2)**: 4 symbols × 2880 polls/day (30 s) = **11,520 rows/table/day**, unbounded.
Later add `prune_snapshots --older-than=<days>` scheduled by DB (`pg_cron`) or worker; add a `ts` index
then if deletes get hot. Flagged risk, not silent accumulation.

## Data Flow

    Bitunix public API ─▶ BitunixClient (read-only GETs)
      worker.run_loop ─▶ run_once ─▶ ingest.fetch_market(client, symbols)
                        │ fetch_rows → split; epoch-ms→UTC once
                        ▼
      {funding, tickers} ─▶ ingest.persist_market ─▶ bulk_create(ignore_conflicts=True), 1 tx
                        ▼
      FundingSnapshot / TickerSnapshot  (global)

## Ingestion Service (`web/trading/ingest.py`)

```python
def fetch_market(client, symbols) -> dict[str, list[dict]]:
    funding, tickers = [], []
    for r in fetch_rows(client, symbols):            # ts already stamped (ms)
        ts = datetime.fromtimestamp(r["ts"] / 1000, tz=timezone.utc)   # convert once
        funding.append({"symbol": r["symbol"], "ts": ts, "funding_rate": r["funding"],
                        "mark_price": r["mark_price"], "index_price": r["index_price"],
                        "next_funding_time": r["next_funding_time"],    # raw ms
                        "funding_interval": r["funding_interval"]})
        tickers.append({"symbol": r["symbol"], "ts": ts, "last_price": r["last_price"],
                        "high": r["high"], "low": r["low"], "quote_vol": r["quote_vol"]})
    return {"funding": funding, "tickers": tickers}

def persist_market(funding, tickers) -> tuple[int, int]:
    with transaction.atomic():
        n_f = len(FundingSnapshot.objects.bulk_create(
            [FundingSnapshot(**r) for r in funding], ignore_conflicts=True))
        n_t = len(TickerSnapshot.objects.bulk_create(
            [TickerSnapshot(**r) for r in tickers], ignore_conflicts=True))
    return n_f, n_t
```

Keys map 1:1 from `fetch_rows`' persistence block (`src/monitor.py:65-74`) except `ts`. Empty input →
`(0, 0)`, no raise. No I/O beyond the two read-only GETs.

## Worker Design (`web/worker.py`)

```python
INGEST_POLL_SECONDS = int(os.environ.get("INGEST_POLL_SECONDS", "30"))

def _bootstrap() -> None:                       # DJANGO_SETTINGS_MODULE default + django.setup()
def run_once(client, symbols) -> tuple[int, int]:
    from trading.ingest import fetch_market, persist_market          # lazy, post-setup()
    market = fetch_market(client, symbols)
    return persist_market(market["funding"], market["tickers"])

def run_loop(client, symbols=None, iterations=None, stop=None, sleep=time.sleep) -> int:
    symbols = config.SYMBOLS if symbols is None else symbols
    backoff, count = INGEST_POLL_SECONDS, 0
    while iterations is None or count < iterations:
        if stop is not None and stop(): break
        try:
            n_f, n_t = run_once(client, symbols)
            logger.info("cycle ok symbols=%d funding=%d tickers=%d", len(symbols), n_f, n_t)
            backoff = INGEST_POLL_SECONDS
        except (BitunixError, requests.RequestException) as exc:
            logger.warning("cycle failed: %s; backoff=%ds", exc, backoff)
            backoff = min(backoff * 2, 300)
        count += 1; sleep(backoff)
    return 0

def _install_signal_handlers() -> Event:        # SIGTERM/SIGINT flip Event, checked between cycles
def main(iterations=None, client=None, symbols=None, stop=None, sleep=time.sleep) -> int:
    _bootstrap()
    return run_loop(client or BitunixClient(), symbols, iterations,
                    stop or _install_signal_handlers(), sleep)
```

Every branch (cycle, backoff, stop) is reachable with injected `iterations`/`stop`/`sleep` — no real
sleeps, 100% patch-coverable. `idle_loop` stays **unchanged** so `scheduler.py` boots untouched (R5);
the lazy import keeps importing `worker` from forcing `django.setup()`.

## Testing Strategy (Strict TDD, `python -m pytest`)

| Layer | What |
|-------|------|
| Unit | persist round-trip; re-persist → `(0,0)`; UTC-aware `ts`; `next_funding_time` raw int; empty → `(0,0)` |
| Unit | `fetch_market` stub client (fixtures, **no sockets**) splits/maps keys |
| Unit | `run_loop`: one cycle ingests & returns 0; client raises once → backoff then recovery; `stop()` true → break |
| Unit | rewritten `test_service_stubs.py`: `main(iterations=1)==0` writes rows; scheduler boot kept |
| Regression | `test_boundary.py`, owned-model guard, `makemigrations --check` green |

## ADRs

**(a)** `trading` vs new `market` — D1. **(b)** Plain loop vs RQ — D4. **(c)** Ship-without-prune vs
prune now — D2, documented deferral. **(d)** Reuse `fetch_rows` vs fork the parser — D3.

## Boundary Note

First `web/ → src/` import (`ingest.py`, `worker.py`). `src/` **unchanged, framework-free**;
`core-isolation` CI and `tests/test_boundary.py` stay green. Global models carry **no `user` FK** and do
not inherit `UserOwnedModel`; `OWNED_MODELS` (`test_owned_model_guard.py:20`) unchanged. Separation is at
the DB/model level; the worker is the trusted zone (R14.4).

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/trading/models.py` | Modify | Add `FundingSnapshot`, `TickerSnapshot` (global, no FK) |
| `web/trading/migrations/0002_market_snapshots.py` | Create | Additive schema + unique constraints |
| `web/trading/ingest.py` | Create | `fetch_market` + `persist_market` |
| `web/worker.py` | Modify | Real loop: bootstrap, backoff, signals; `idle_loop` kept |
| `web/scheduler.py` | Unchanged | Stub still boots via `worker.idle_loop` |
| `tests/web/test_ingest.py` | Create | Round-trip + idempotency + UTC + loop |
| `tests/web/test_service_stubs.py` | Modify | Rewrite worker contract; keep scheduler boot |
| `src/`, `web/accounts/`, `web/config/`, `requirements.txt` | Unchanged | Boundary preserved |

## Task Breakdown Hint

~350–450 lines vs 400 budget → **2 chained PRs** (ask-on-risk → orchestrator confirms): **PR1** models +
migration + `ingest.py` + `test_ingest.py` (data path, autonomous, ~250); **PR2** real `worker.py` loop +
rewritten `test_service_stubs.py` (~150). Each PR boots and reverts cleanly.

## Open Questions

None blocking. Resolved: app = `trading`; retention = ship-without-prune (documented deferral); fetch =
reuse `fetch_rows`; execution = plain loop; scheduler unchanged.
