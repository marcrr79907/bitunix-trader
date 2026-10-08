# Proposal: market-ingestion

## Intent

Phase 0 shipped `web/worker.py` as a boot-only stub that pings Redis and idles. Phase 3 turns it into the real **global market ingester**: poll the two read-only public endpoints the client already exposes (tickers + funding) on an interval and persist time-series snapshots shared by all users. Strictly read-only: **no order execution, ever.**

## Scope

### In Scope
- Two **GLOBAL** models in the existing `trading` app (NOT `UserOwnedModel`, no user FK), mirroring the core tables 1:1:
  - `FundingSnapshot`: `symbol(32)`, `ts` (UTC), `funding_rate`/`mark_price`/`index_price` (Float, null), `next_funding_time` (BigInteger, null, raw epoch ms), `funding_interval` (Integer, null). ← `client.funding_rate_batch()`.
  - `TickerSnapshot`: `symbol(32)`, `ts` (UTC), `last_price`/`high`/`low`/`quote_vol` (Float, null). ← `client.tickers(symbols)`.
  - `UniqueConstraint(symbol, ts)` per model; persist via `bulk_create(ignore_conflicts=True)`.
- `web/trading/ingest.py`: `fetch_market(client, symbols)` + `persist_market(...)` (idempotent); epoch-ms → UTC `datetime` converted once at the boundary.
- Real `web/worker.py` loop: Django setup, `INGEST_POLL_SECONDS` (default 30), exponential backoff `min(backoff*2, 300)`, structured logging, SIGTERM/SIGINT clean shutdown. NO RQ.
- Additive migration `trading/0002_*`; `makemigrations --check` stays green.
- Tests (Strict TDD): ingest round-trip + idempotency (stub client, no sockets); worker loop with injected client + backoff/shutdown; rewrite `tests/web/test_service_stubs.py`.

### Out of Scope
- `Candle`/OHLC ingestion (no OHLC endpoint exists in `src/client.py`).
- RQ/Celery/job queue; scheduler becomes real (stays a boot-only stub).
- JSON API/DRF, UI/charts, alerts/notifications.
- Per-user `PositionSnapshot`, `AccountSnapshot`, `Trade`, `AlertRule`.
- Retention/pruning job — **flagged, not built** (see Risks R1).
- **Any order execution — HARD invariant, never.** `MultiFernet` key rotation.

## Capabilities

### New Capabilities
- `market-ingestion`: poll + idempotently persist global funding/ticker snapshots; real worker loop (backoff, logging, clean shutdown).

### Modified Capabilities
- None. (`core-domain-boundary` and `security-invariants` R11/R14 are constraints to satisfy, not alter.)

## Approach

Two narrow global tables match the core's proven shape (`src/db.py`); collapsing them would create a wide sparse table and lose per-series `(symbol, ts)` idempotency. **Reuse `src.monitor.fetch_rows`** for the fetch — single source of truth for field names, no forked parser. It stamps `ts` internally via `time.time()`; idempotency is therefore tested at the **persist layer** (persist same rows twice → second is a no-op), so no clock seam is required. Reuse `src.config.SYMBOLS` and the proven backoff from `src/monitor.py`. No new runtime dependency.

**App placement (design decides):** recommend **`trading`** — already installed/migrated/scanned; no wiring cost. A new `market` app buys a cleaner global-vs-per-user split at real wiring cost; split in Phase 4 if it grows a second concern.

**Boundary (honest constraints):** this adds the **first `web/ → src/` import** — the intended direction, guarded by `tests/test_boundary.py` + `core-isolation` CI. `src/` stays framework-free and unchanged. The worker is the **trusted zone** (R14.4); global models carry no user FK, so the owned-model guard is unchanged.

**Read-only:** computation + persistence only — no `Client` mutation, no order endpoints.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/models.py` | Modified | add `FundingSnapshot`, `TickerSnapshot` (global, no FK) |
| `web/trading/migrations/0002_*.py` | New | additive schema |
| `web/trading/ingest.py` | New | `fetch_market` + `persist_market` (idempotent) |
| `web/worker.py` | Modified | real loop: Django setup, backoff, signals |
| `web/scheduler.py` | Unchanged | stays a stub; keep `idle_loop` compatible |
| `tests/web/test_service_stubs.py` | Modified | rewrite worker contract |
| `tests/web/test_ingest.py` | New | round-trip + idempotency + loop |
| `src/`, `web/accounts/`, `web/config/`, `requirements.txt` | Unchanged | boundary preserved |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| R1 Unbounded data growth (~11,520 rows/day/table) | High | **Ship without pruning but flag it**; later prune management command. Not silently accumulated in prod |
| First `web/ → src/` import erodes boundary | Low | Boundary tests + `core-isolation` CI guard |
| UTC correctness (ms int vs `DateTimeField`) | Med | Convert once at boundary with `tz=utc`; keep `next_funding_time` raw ms |
| Coverage gates (web ≥85%, patch 100%) vs loop lines | Med | Injectable `iterations`/`stop`/`sleep`; no real sleeps |
| `scheduler.py` shares `worker.idle_loop` | Low | Keep compatible `idle_loop` or update both together |
| No OHLC source makes `Candle` speculative | — | Explicitly deferred (YAGNI) |

## Rollback Plan

Revert the branch: delete `web/trading/ingest.py`, `tests/web/test_ingest.py`, and the `trading/0002_*` migration; restore `web/trading/models.py`, `web/worker.py`, `tests/web/test_service_stubs.py`. `src/`, `accounts`, CLI and `credentials.py` stay untouched, so `main` still ships a working read-only CLI. If the worker is deployed, redeploy the previous stub image.

## Dependencies

- Existing Phase-0 contract: worker env (`DJANGO_SETTINGS_MODULE`, `DATABASE_URL`) — already set in `docker-compose.yml:51`.

## Open Questions

- App placement: `trading` (recommended) vs a new `market` app?
- Retention: ship without prune + flagged risk (recommended) vs a prune command now?
- Fetch: reuse `src.monitor.fetch_rows` (recommended) vs direct client call with a clock seam?

## Success Criteria

- [ ] `python -m pytest` green under Strict TDD; ingest round-trip + idempotency pass with a stub client (no sockets).
- [ ] Re-persisting the same rows inserts **0** new rows (idempotent).
- [ ] Worker boots, ingests `iterations` cycles, backs off on error, and returns 0 on SIGTERM/SIGINT.
- [ ] `ruff check . && ruff format --check .` green; `makemigrations --check` green.
- [ ] `tests/test_boundary.py` green; `src/` unchanged; no new runtime dependency.
- [ ] Global models carry no user FK and do not inherit `UserOwnedModel`.
- [ ] No order-execution surface.

## Review Workload Forecast

- Estimated diff: **~350–450 changed lines** (2 models + migration + ingest + real worker + rewritten/new tests).
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: Medium
