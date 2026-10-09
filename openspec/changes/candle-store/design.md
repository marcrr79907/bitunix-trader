# Design: candle-store (issue #43)

## Technical Approach

Persist OHLC candles directly from BitUnix — no aggregation. A global `Candle` in `trading`
(mirrors `FundingSnapshot`), an extended `kline()` (range params + `quote_vol`), a resumable
`backfill_candles` command paginating backward via `endTime`, and a closed-candle cycle appended
to `worker.run_once`. Ticks keep running; `src/` stays framework-free.

## Data Model (`web/trading/models.py`)

| Field | Type | Note |
|---|---|---|
| `symbol` | `CharField(32)` | |
| `interval` | `CharField(8)` | `5m,15m,1h,2h,4h,1d,1w,1M` |
| `time` | `BigIntegerField` | candle OPEN, UNIX **seconds** |
| `open/high/low/close` | `FloatField` | |
| `quote_vol` | `FloatField(null=True)` | from `quoteVol` |

`Meta`: `UniqueConstraint(["symbol","interval","time"], name="uniq_candle_symbol_interval_time")`
**and** `Index(["symbol","interval","time"], name="ix_candle_symbol_interval_time")` (spec R1 mandates
both; the index is redundant with the unique on Postgres — `ponytail:` kept because the spec pins it).
Migration `trading/0003_candle.py`, additive, depends `0002_market_snapshots`, no data migration.

## Architecture Decisions

| # | Decision | Choice | Rejected | Rationale |
|---|---|---|---|---|
| a | Storage | **Persist each interval direct** from BitUnix | Derive larger from 5m | BitUnix is the truth; user asked for all its intervals; no bucketing/volume-sum correctness surface |
| b | Closure rule | `now >= time + INTERVAL_SECONDS[interval]`, pure `is_closed(time, interval, now)` | Approximation mixing clock + "newer candle appeared" | Fixed intervals exact; spec R4 pins the wall-clock rule |
| c | Helper seam | New `web/trading/candles.py` | Extend `ingest.py` | `ingest.py` is snapshot-focused (deep module); closure/loop is a real second concern |
| d | `quote_vol` strip | Inside `quotes.get_kline_payload` | At view / client | One seam every chart response passes through; client `kline()` must keep `quote_vol` for candles |

**Closure seconds (D-b)**: `5m=300, 15m=900, 1h=3600, 2h=7200, 4h=14400, 1d=86400, 1w=604800,
1M=2678400`. 1w is exactly 7d (UTC epoch, DST-free). 1M is calendar-irregular: 2678400 (31d, the
longest month) GUARANTEES the bucket ended for every month, never persisting a partial candle; cost
is a ≤3-day delay on shorter months — harmless, and backfill covers history. Literal 30d would risk a
premature partial monthly candle.

## Backfill Command (`web/trading/management/commands/backfill_candles.py`)

CLI: `--symbol` (append, default `config.SYMBOLS`), `--interval` (append, default all 8), `--start`
`YYYY-MM-DD` (optional cap), `--end` (optional, default now), `--sleep` float (default `0.15`),
`--dry-run`. Requires `management/__init__.py` + `commands/__init__.py`.

Module-level `run(client, symbols, intervals, start, end, dry_run, sleep, out) -> int` holds the loop
(the `worker.run_loop` seam); `Command.handle` parses args and delegates with `BitunixClient()`.

Per `(symbol, interval)`: **resume** cursor = `Min(Candle.time)` for that series → `min*1000 - 1`,
else `end or now_ms`. **Loop**: `rows = client.kline(sym, iv, 200, end_time=cursor)`; empty → stop;
below `--start` filter + stop; persist `bulk_create(ignore_conflicts=True)` (skip on `--dry-run`);
`cursor = min(row.time)*1000 - 1`; `sleep(sleep)`. Idempotent by unique key, resumable from oldest
stored. Log one line/page + one/series. `BitunixError`/`RequestException` → log + abort series
(re-run resumes). ~25k req for 5m, ~23–40 min at 10 req/s. SQLite dev: run partial (feature/RANGE
arg); full 1.87M targets Postgres prod.

## Continuous Ingestion (`web/trading/candles.py` + `web/worker.py`)

`INTERVAL_SECONDS` map above; `CANDLE_INTERVALS = tuple(INTERVAL_SECONDS)`. Deep interface:
`fetch_closed_candles(client, symbols, now=None) -> list[dict]` iterates symbol×interval,
`kline(sym, iv, limit=2)`, keeps rows where `is_closed(...)`; `persist_candles(rows) -> int` via
`bulk_create(ignore_conflicts=True)`. `limit=2` = forming + just-closed.

`run_once` appends AFTER funding/ticker persist, isolated:

```python
counts = persist_market(funding, tickers)
try:
    persist_candles(fetch_closed_candles(client, symbols))
except Exception as exc:   # ponytail: broad by spec — candle failure must never kill ticks
    logger.warning("candle cycle failed: %s", exc)
return counts
```

Cadence: **all 8 intervals every cycle** (32 req/cycle ≈ 1.07 req/s, within 10/s). Stagger adds state
for a budget that is not tight; sequential blocking GETs self-space. `ponytail:` revisit pacing only
if bursts are measured.

## `quotes.py` strip

In `get_kline_payload`, project each deduped candle to exactly the five chart keys:
`{k: c[k] for k in ("time","open","high","low","close")}`. `kline()` keeps `quote_vol`;
`/market/api/kline` never sees it. Delta spec R1/R3 satisfied.

## Volumetry

| Interval | bars/sym/yr | ×4 sym/yr | | Interval | bars/sym/yr | ×4 sym/yr |
|---|---|---|---|---|---|---|
| 5m | 105,120 | 420,480 | | 1d | 365 | 1,460 |
| 15m | 35,040 | 140,160 | | 1w | 52 | 208 |
| 1h | 8,760 | 35,040 | | 1M | 12 | 48 |
| 2h | 4,380 | 17,520 | | **Total** | **155,919** | **623,676** |
| 4h | 2,190 | 8,760 | | | | |

Backfill ≈ **1.87M rows** (~3y × 4 symbols); growth ≈ **1,709 rows/day**. No prune (issue #45).

## Testing Strategy (Strict TDD, `python -m pytest`, no sockets)

| Layer | What | Seam |
|---|---|---|
| Unit `test_client_kline.py` | range params pass/omitted; `quote_vol` map + missing→`None` | monkeypatch `requests.get` |
| Unit `test_candles.py` | `is_closed` per interval (incl. 1M boundary); `fetch_closed_candles` drops forming; `persist_candles` idempotent | stub client, fixed `now` |
| Integration `test_backfill_candles.py` | page advance, empty stop, `--start` bound, resume from `Min(time)`, idempotent re-run, `--dry-run` writes nothing, throttle called | `call_command` + monkeypatched `backfill_candles.BitunixClient`; direct `run()` with recorder `sleep` |
| Integration `test_worker_candles.py` | closed persisted, forming dropped; candle raise → ticks still persist | stub with `kline`; reuse `SleepRecorder` |
| Regression `test_market_api.py` | candle exactly 5 fields when upstream carries `quoteVol` | stub client |

Patch gate 100%: every new line reachable via injected `client`/`sleep`/`now`; `--sleep 0` in
`call_command` tests. `test_boundary.py`, owned-model guard, `makemigrations --check` stay green.

## ADRs

**ADR-a direct vs derive**: store what BitUnix returns, per interval. Deriving needs bucketing + volume
summation (new correctness surface) and forks from the source. Revisit only if request budget hurts.
**ADR-b closure**: `now >= time + INTERVAL_SECONDS`, 1M=31d conservative. Rejected calendar math
(complex, still approximate) and "newer candle appeared" (spec pins wall-clock; loses edge coverage).
**ADR-c candles.py**: `ingest.py` stays snapshot-focused; candles get their own deep module.
**ADR-d strip**: at `get_kline_payload`, the sole chart-payload seam.

## Boundary Note

`src/client.py` uses only `requests` — `core-isolation` + `test_boundary.py` green. Models global, no
`user` FK, not `UserOwnedModel` (R14 n/a). Management command + worker are the trusted zone. `kline()`
is a public read-only GET — no `FORBIDDEN_PATHS`/`ORDER_VERBS` match; scanner clean.

## File Changes

| File | Action | Description |
|---|---|---|
| `web/trading/models.py` | Modify | Add `Candle` |
| `web/trading/migrations/0003_candle.py` | Create | Additive table |
| `web/trading/management/{__init__,commands/__init__}.py` | Create | Package markers |
| `web/trading/management/commands/backfill_candles.py` | Create | Resumable throttled backfill + `run()` |
| `web/trading/candles.py` | Create | `INTERVAL_SECONDS`, `is_closed`, fetch/persist |
| `web/worker.py` | Modify | Append isolated candle cycle in `run_once` |
| `src/client.py` | Modify | `kline()` range params + `quote_vol` |
| `web/market/quotes.py` | Modify | Strip candles to five keys |
| `tests/test_client_kline.py` | Modify | Range + `quote_vol` |
| `tests/web/test_candles.py` | Create | Closure + fetch/persist |
| `tests/web/test_backfill_candles.py` | Create | Command contract |
| `tests/web/test_worker_candles.py` | Create | Worker candle cycle + isolation |
| `tests/web/test_market_api.py` | Modify | Five-field candle assertion |
| `docs/deployment.md` (or changelog) | Modify | Volumetry note |
| `requirements.txt`, `web/scheduler.py`, `web/market/views.py` | Unchanged | No dep/endpoint change |

## Task Breakdown Hint

~500–650 changed lines vs 400 budget → **Decision needed before apply: Yes**, **Chained PRs
recommended: Yes**, **400-line budget risk: Medium**. Orchestrator confirms with user (ask-on-risk):

- **PR1 — data tier (autonomous)**: `Candle` + `0003` + `kline()` mapping + `test_client_kline.py`
  updates (~200). Boots, migration check green.
- **PR2 — backfill (targets PR1)**: management package + command + `test_backfill_candles.py` (~250).
- **PR3 — continuous (targets PR2)**: `candles.py` + `worker.run_once` + `quotes.py` strip +
  candle/worker/market-api tests (~200).

## Open Questions

None blocking. Resolved: direct persist; closure map incl. 1M=31d; cadence every cycle; isolation in
`run_once`; `candles.py`; strip in `get_kline_payload`; backfill CLI/`run()` seam.
