# Tasks: candle-store

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

Tracker: `feat/candle-store` (current branch, merges to `develop`). Strict TDD:
every WU is RED → GREEN → full-suite. No sockets (`python -m pytest`).

## Guard/Edge Matrix (every row = a test in its WU)

- [x] Global `Candle` has NO `user` FK, does NOT inherit `UserOwnedModel` (R1)
- [x] `UniqueConstraint(symbol,interval,time)` rejects a duplicate row (R1)
- [x] Composite `(symbol,interval,time)` index present (R1)
- [x] `kline()` maps ms→s int, floats, `quoteVol`→`quote_vol`; missing→`None` (R1 delta)
- [x] `start_time`/`end_time` → `startTime`/`endTime` ms; omitted when `None` (R1 delta)
- [x] Backfill: empty page stops the series, no raise (R3)
- [x] Backfill: resume cursor = `Min(time)*1000 - 1`, not `now` (R3)
- [x] Backfill: `--start` bounds earliest requested candle (R3)
- [x] Backfill: `--dry-run` inserts nothing; re-run inserts 0 new (idempotent) (R3)
- [x] Backfill: injected sleep called between pages, no real delay (R3)
- [x] `is_closed` per interval incl. `1M`=31d boundary; forming excluded (R4)
- [x] Worker cycle persists closed candles AND keeps tick counts (R4)
- [x] Candle failure isolated: funding/ticker still persist, loop survives (R4)
- [x] `/market/api/kline` candle is EXACTLY `{time,open,high,low,close}` (R3 delta)
- [x] `src/` framework-free; `requirements.txt` unchanged (R6)
- [x] Scanner clean: no order surface (R5)

## WU1 (PR1) — data tier

Base `feat/candle-store` (tracker). Depends: none.

- [x] 1.1 **RED** `tests/test_client_kline.py`: range params pass/omitted; `quote_vol` map + missing→`None`; update exact-dict asserts for the new key.
- [x] 1.2 **RED** `tests/web/test_candles_model.py`: no owner FK; unique dup rejected; composite index present.
- [x] 1.3 **GREEN** `src/client.py::kline(symbol, interval="1m", limit=100, start_time=None, end_time=None)`: conditional `startTime`/`endTime` params + `quote_vol` mapping.
- [x] 1.4 **GREEN** `web/trading/models.py`: global `Candle` (symbol/interval/time/open/high/low/close/quote_vol; UniqueConstraint + composite Index).
- [x] 1.5 **GREEN** `web/trading/migrations/0003_candle.py` additive; `makemigrations --check` green.
- [x] 1.6 Full suite + ruff green.
- [x] 1.7 **Rollback**: revert `models.py`, `client.py`, delete `0003_*` + new test. Dropped `candles` table = derived data only.

## WU2 (PR2) — backfill command

Base WU1 branch. Depends: WU1.

- [x] 2.1 **RED** `tests/web/test_backfill_candles.py` (via `call_command`, stub client, recorder `sleep`, fixed `now`): fills; idempotent re-run = 0 new; resume from `Min(time)`; `--dry-run` inserts nothing; empty page stops; `--start` bounds; error aborts series.
- [x] 2.2 **GREEN** package markers `web/trading/management/__init__.py`, `management/commands/__init__.py`.
- [x] 2.3 **GREEN** `management/commands/backfill_candles.py`: module-level `run(client, symbols, intervals, start, end, dry_run, sleep, out) -> int` (backward pagination via `endTime`, resume cursor, `--start` bound, empty→stop, `bulk_create(ignore_conflicts=True)`, throttle); `Command.handle` parses `--symbol`(append, default `config.SYMBOLS`), `--interval`(append, all 8), `--start`, `--end`, `--sleep`(0.15), `--dry-run`.
- [x] 2.4 Full suite + ruff green; `--sleep 0` keeps tests fast.
- [x] 2.5 **Rollback**: delete `management/` + test. No schema change.

> SQLite-dev caveat: full ~1.87M-row backfill targets Postgres prod; on dev run
> partial (`--start`/RANGE arg). Idempotent + resumable, so a partial run is safe.

## WU3 (PR3) — continuous ingestion + strip

Base WU2 branch. Depends: WU2.

- [x] 3.1 **RED** `tests/web/test_candles.py`: `is_closed` all intervals incl. `1M`; `fetch_closed_candles` drops forming; `persist_candles` idempotent.
- [x] 3.2 **RED** `tests/web/test_worker_candles.py`: cycle persists closed + keeps tick counts; candle raise → ticks still persist, loop lives.
- [x] 3.3 **RED** `tests/web/test_market_api.py`: candle exactly five keys when upstream carries `quoteVol`.
- [x] 3.4 **GREEN** `web/trading/candles.py`: `INTERVAL_SECONDS`, `CANDLE_INTERVALS`, `is_closed(time, interval, now)`, `fetch_closed_candles(client, symbols, now=None)`, `persist_candles(rows)`.
- [x] 3.5 **GREEN** `web/worker.py::run_once`: append candle cycle AFTER `persist_market`, isolated `try/except Exception` (never breaks ticks).
- [x] 3.6 **GREEN** `web/market/quotes.py::get_kline_payload`: project each candle to exactly `{time,open,high,low,close}`.
- [x] 3.7 Volumetry note (backfill ~1.87M; growth ~1,709/day) in `docs/deployment.md`.
- [x] 3.8 **Rollback**: restore `worker.py`, `quotes.py`; delete `candles.py` + new tests. Worker redeploy restores prior ingest-only loop.

## Phase 4 — Verification

- [x] 4.1 `python -m pytest` green (Strict TDD); patch coverage 100%.
- [x] 4.2 `ruff check . && ruff format --check .` + `makemigrations --check` green.
- [x] 4.3 Boundary + scanner green: `src/` framework-free, no order surface, no new runtime dep.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | WU1 ~200, WU2 ~250, WU3 ~200 → ~500–650 total |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 (each targets prior branch) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |
| Tracker branch | `feat/candle-store` → merges to `develop` |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium
