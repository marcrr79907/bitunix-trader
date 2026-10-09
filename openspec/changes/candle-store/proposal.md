# Proposal: candle-store

## Intent

Candles are ephemeral today (market-chart A4): every `/market/api/kline` call hits BitUnix REST and nothing is stored, so the chart is capped at ~200 rows and future analysis (pattern detection, backtesting) has no data floor. Issue #43 supersedes A4 for the data tier: persist OHLC candles in our DB to build a durable, queryable historical dataset independent of BitUnix's ~3-year API depth, fed by a one-time backfill plus continuous ingestion of closed candles.

## Scope

### In Scope
- **GLOBAL** `Candle` model in the existing `trading` app (no user FK, not `UserOwnedModel`): `symbol` Char(32), `interval` Char(8), `time` BigInt (UNIX seconds, candle open), `open`/`high`/`low`/`close` Float, `quote_vol` Float(null). `UniqueConstraint(symbol, interval, time)` + composite index `(symbol, interval, time)`.
- Additive migration `trading/0003_*`; `makemigrations --check` green.
- `src/client.py::kline()` extended with optional `start_time`/`end_time` (epoch ms, pass-through) + `quote_vol` mapping; backward compatible; read-only, unsigned.
- `manage.py backfill_candles` (`web/trading/management/commands/`): backward pagination via `endTime` until depth exhausted, per symbol × interval (confirmed set: 5m, 15m, 1h, 2h, 4h, 1d, 1w, 1M — NOT 1m). Idempotent (`ignore_conflicts`), resumable (resume from oldest stored `time`), throttled (~0.15s sleep, 10 req/s budget), `--dry-run`, logging.
- Worker continuous ingestion: each 30s cycle appends per symbol × interval a `kline(limit=2)` fetch and persists only CLOSED candles (bucket window passed); existing funding/ticker ingestion untouched.
- Volumetry documented (rows per interval/symbol/year; backfill estimate ~1.87M rows, growth ~624k rows/yr).
- Tests (Strict TDD, no sockets): model constraints, kline params + mapping, backfill pagination/resume/idempotency via `call_command`, worker candle cycle, updated kline exact-dict tests.

### Out of Scope
- Chart pagination / `/market/api/kline` behavior changes (issue #44).
- Retention/prune of candles or snapshots (issue #45 — flagged: table grows unbounded).
- Pattern detection, backtesting engine, precomputed indicators.
- Per-user candles (R14 n/a — global data, no owner FK).
- Deriving larger intervals from 5m (single-source aggregation).
- **Order execution — HARD invariant, never.** New runtime dependencies — none.

## Capabilities

### New Capabilities
- `candle-store`: global Candle model + additive migration, kline time-range params, resumable throttled backfill command, worker closed-candle continuous ingestion, volumetry doc.

### Modified Capabilities
- `market-chart`: R1 — `kline()` mapping gains `quote_vol` (and optional range params); the payload contract in `quotes.get_kline_payload` must keep its exact `{time, open, high, low, close}` candle shape (strip or filter the new key before it reaches `/market/api/kline`).

## Approach

Reuse-first (matches market-ingestion patterns): `Candle` mirrors the snapshot global-model shape in `web/trading/models.py`; persistence via `bulk_create(ignore_conflicts=True)` + unique constraint (idempotency by `(symbol, interval, time)`); backfill lives in a management command next to the models it fills, paginating backward with `endTime` (BitUnix ignores `startTime`; backward-verified). Resume = continue from `Min(time)` of stored candles. Worker appends candle persistence to the existing `run_once` loop — never replaces funding/ticker ingestion; closure is derived from the candle's own bucket boundary (pure function, easy TDD). `src/` stays framework-free; worker remains the trusted zone; no new runtime dependency.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/models.py` | Modified | add global `Candle` |
| `web/trading/migrations/0003_*.py` | New | additive schema |
| `web/trading/management/commands/backfill_candles.py` | New | resumable throttled backfill |
| `src/client.py` | Modified | `kline()` range params + `quote_vol` mapping |
| `web/worker.py` | Modified | append closed-candle cycle to ingest loop |
| `web/trading/ingest.py` or new `candles.py` | Modified/New | closed-candle fetch/persist helper |
| `web/market/quotes.py` | Modified | keep chart payload candle shape exact (strip new key) |
| `tests/test_client_kline.py`, `tests/web/test_ingest.py`/new, `tests/web/test_worker_candles.py` | Modified/New | TDD suites |
| `web/market/views.py`, `web/market/urls.py`, `requirements.txt`, `web/scheduler.py` | Unchanged | no endpoint/UI/dep changes |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| kline mapping change leaks `quote_vol` into chart payload / breaks exact-dict tests | High | Explicit key filter in `quotes.py`; update exact assertions; delta spec |
| Backfill is long (~20-40 min) and aborts mid-run | Med | Idempotent + resumable from `Min(time)`; `--dry-run` first; abort-on-error with clear log |
| BitUnix rate limit (10 req/s/ip) shared with worker + live page | Med | Conservative throttle sleep; worker cycle amortizes ~32 req over 30s |
| Patch coverage 100% vs pagination/command lines | Med | Injectable `sleep` + stub client + `call_command` tests; exhaustive branches |
| `1M`/`1w` closure boundary math (bucket seconds approximate) | Med | Closure from candle `time` + interval seconds; design confirms rule (R5) |
| Unbounded growth (~1,709 rows/day) | Med | Documented volumetry; prune deferred to issue #45 (flagged, not silent) |
| 1.87M-row backfill on SQLite dev | Low | Batched `bulk_create`; full backfill targets Postgres prod |

## Rollback Plan

Revert the branch: delete `web/trading/management/`, the `trading/0003_*` migration, new test files, and the closed-candle helper; restore `web/trading/models.py`, `src/client.py`, `web/worker.py`, `web/market/quotes.py`. The dropped `candles` table removes only derived data (re-backfillable from BitUnix). Worker redeploy restores the previous ingest-only loop; funding/ticker ingestion is untouched throughout.

## Dependencies

- BitUnix public REST kline (read-only, unsigned, 10 req/s/ip; ~3y depth).
- Existing worker contract (`INGEST_POLL_SECONDS`, `DJANGO_SETTINGS_MODULE`) — unchanged.

## Open Questions

- Chart payload shape: strip `quote_vol` in `quotes.py` (recommended) vs keep it in the API response?
- Closure rule for `1w`/`1M` (approximate bucket seconds vs persist-when-newer-candle-appears)?
- Backfill default bounds: full depth vs `--start` cap; symbol×interval ordering.

## Success Criteria

- [ ] `python -m pytest` green (Strict TDD); patch coverage 100%; ruff clean.
- [ ] Backfill fills to BitUnix depth; re-running inserts 0 new rows (idempotent); interrupted run resumes from oldest stored candle.
- [ ] Volumetry documented (rows per interval/symbol/year; ~1.87M backfill estimate).
- [ ] Worker persists closed candles without degrading funding/ticker ingestion.
- [ ] `makemigrations --check` green; no new runtime dependency; `requirements.txt` intact.
- [ ] `/market/api/kline` payload shape unchanged (candles `{time, open, high, low, close}`).
- [ ] No order-execution surface; boundary scanners green.

## Review Workload Forecast

- Estimated diff: **~500–650 changed lines** (model + migration ~80, client + tests ~120, command ~150, worker/ingest + tests ~180, quotes strip ~20).
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: Medium
