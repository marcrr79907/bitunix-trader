# Design: private-data-sync

## Technical Approach

Two live scanners dictate one seam. `web/trading/` sits inside the credential
scanner's `REQUEST_PATH`, so the new `web/trading/sync.py` is **fetch + persist
only, no `decrypt`**. `web/worker.py` is outside every scanned path, so it owns
decryption and credential iteration (R14.4 trusted zone). Persist exactly like
`ingest.py`/`candles.py`: model dicts + `bulk_create(ignore_conflicts=True)` +
count delta. Field mapping reuses `src.monitor.position_row` /
`src.journal.trade_row`. Maps to private-data-sync R1–R6, market-ingestion R4b,
per-user-isolation R14.2–R14.4, security-invariants R13/R14.

## Data Model (`web/trading/models.py`)

Three `UserOwnedModel` subclasses (FK CASCADE, `for_user`), additive migration
`trading/0004_private_snapshots.py` (deps `0003_candle` + swappable user).

| Model | Fields | Unique |
|-------|--------|--------|
| `PositionSnapshot` | `symbol` Char(32); `side` Char(8) null; `qty`/`avg_open`/`leverage`/`liq_price`/`upnl`/`margin_rate` Float null; `ts` DateTime | `(user, symbol, ts)` `uniq_position_user_symbol_ts` |
| `AccountSnapshot` | `available`/`cross_upnl` Float null; `ts` DateTime | `(user, ts)` `uniq_account_user_ts` |
| `Trade` | `trade_id` Char(64); `symbol` Char(32); `side` Char(8) null; `qty`/`price`/`fee`/`realized_pnl` Float null; `ctime` BigInteger null | `(user, trade_id)` `uniq_trade_user_trade_id` |

`order_id` omitted (proposal resolved). `Float` matches the global snapshots.

## sync.py (`web/trading/sync.py`, no `decrypt`)

```python
_PAGE = 100

def persist_positions(user, rows, ts) -> int:   # position_row + _f coercion
def persist_account(user, row, ts) -> int:      # dict-or-list normalized
def persist_trades(user, rows) -> int:          # trade_row minus order_id

def sync_user(user, client, ts=None) -> dict:
    ts = ts or datetime.now(UTC)
    return {"positions": persist_positions(user, client.positions(), ts),
            "account":   persist_account(user, client.account(), ts),
            "trades":    persist_trades(user, _fetch_trades(client))}

def _fetch_trades(client) -> list[dict]:        # journal.sync pagination
```

`_f(value) -> float|None` (local, mirrors `src.monitor._f`) coerces the
string/null fields `position_row` leaves raw (`qty`, `avg_open`, `leverage`,
`liq_price`). Imports: `trading.models`, `src.monitor`, `src.journal` — **never
`credentials`**. Owned models touched only via `bulk_create`/`count`.

## Worker (`web/worker.py`, trusted zone)

```python
def run_private_sync(client_factory=None) -> int:
    from credentials import decrypt
    from src.client import BitunixClient
    from trading.models import ExchangeCredential
    from trading.sync import sync_user
    factory = client_factory or BitunixClient
    n = 0
    for cred in ExchangeCredential.objects.filter(is_active=True):
        try:
            client = factory(decrypt(cred.api_key_encrypted),
                             decrypt(cred.api_secret_encrypted))
            sync_user(cred.user, client); n += 1
        except Exception as exc:  # ponytail: per-user isolation by spec (R5)
            logger.warning("private sync failed user=%s: %s", cred.user_id, exc)
    return n
```

`run_once` gains a step after ticks+candles, isolated like candles: `try:
run_private_sync() except Exception: log`. `(funding, ticker)` unchanged; no
active creds → no-op.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Decrypt seam | worker.py owns decrypt | decrypt in sync.py | Scanner-forced: `trading/` is in `REQUEST_PATH`; worker is outside it |
| Persist API | `bulk_create(ignore_conflicts=True)` + count delta | `update_or_create` per row | Matches `ingest.py`/`candles.py`; verbs absent from `UNSCOPED_VERBS` → guard green |
| Clock | explicit `ts` param on `persist_positions/account` | stamp `now()` inside persist | Re-sync must be a no-op (R2); an internal clock makes every re-poll a new row. Adds a test seam at zero cost. `sync_user` stamps once, trades keyed by `ctime` |
| Cadence | every cycle (30s), same as ingest | `PRIVATE_SYNC_SECONDS` knob | Proposal default; knob is speculative config (YAGNI) — persist is isolated, a one-line add later. Growth is the accepted, documented carry-forward |
| Models | 3 owned models | one JSON blob | R14 per-row ownership/constraints; matches CLI rows |

## Idempotency

`ignore_conflicts` on `(user,symbol,ts)` / `(user,ts)` / `(user,trade_id)`;
trade ids are per-user so A and B may share one.

## OWNED_MODELS / guard

`OWNED_MODELS += {"PositionSnapshot","AccountSnapshot","Trade"}` in
`test_owned_model_guard.py`. `bulk_create`/`count` are **not** in
`UNSCOPED_VERBS`; the worker's `ExchangeCredential.objects.filter` lives in
`worker.py`, outside the guard's `REQUEST_PATH`. Both scanners stay green.

## Data Flow

    Bitunix private API ─▶ worker.run_private_sync (decrypt creds)
        └▶ sync_user(user, client) ─▶ PositionSnapshot/AccountSnapshot/Trade
                             (bulk_create ignore_conflicts, count delta)

## Testing Strategy (Strict TDD, `python -m pytest`, patch 100%, no sockets)

| # | Test | Branch |
|---|---|---|
| T1 | unique `(user,symbol,ts)`/`(user,ts)`/`(user,trade_id)` reject dup | R1 |
| T2 | same `trade_id` allowed A∥B; `for_user(A)` vs B for 3 models | R1/R14.2 |
| T3 | `persist_*` twice (same `ts`) → 0; empty → 0; no raise | R2 |
| T4 | `sync_user` stub client maps payloads (position/account/trade) | R3 |
| T5 | scanner clean on `sync.py` (no decrypt import/attr/bare/getattr) | R3/R13 |
| T6 | `run_private_sync(stub_factory)`: active cred decrypts+persists | R4/R13 |
| T7 | inactive cred skipped; no creds → no-op (covers `or BitunixClient`) | R4 |
| T8 | A raises, B succeeds → B synced; `run_once` contract intact | R5/R4b |
| T9 | guard fixture flags `PositionSnapshot.objects.all()` | R14.3 |

Fernet key via existing `fernet_key` fixture (`monkeypatch.setenv`), stub
factory + stub client, raw `ExchangeCredential.objects` reads only in the test
file (outside scanned paths).

## Boundary / Rollback

`sync.py` imports `src.monitor`/`src.journal` (already-framework-free `src/`);
no new dependency; no order surface (R11). Revert branch → `main` still ships
the read-only CLI with R13/R14 and global ingest green.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/trading/models.py` | Modify | 3 owned models + unique constraints |
| `web/trading/migrations/0004_private_snapshots.py` | Create | additive |
| `web/trading/sync.py` | Create | fetch + persist, no decrypt |
| `web/worker.py` | Modify | `run_private_sync` + isolated `run_once` step |
| `tests/web/test_owned_model_guard.py` | Modify | `OWNED_MODELS` += 3 |
| `tests/web/test_isolation.py` | Modify | A≠B for 3 models |
| `tests/web/test_private_sync.py` | Create | T1–T5, T9 |
| `tests/web/test_worker_private_sync.py` | Create | T6–T8 |
| `src/`, `web/credentials.py`, `requirements.txt` | Unchanged | boundary preserved |

## Task Breakdown Hint

~450–600 lines vs 400 budget → **chained PRs** (ask-on-risk → orchestrator
confirms). **PR1**: models + migration + `sync.py` + `test_private_sync.py`
(~280). **PR2**: `worker.py` step + `test_worker_private_sync.py` (~180).
**PR3**: `OWNED_MODELS` guard + `test_isolation.py` extension (~60).
`Decision needed before apply: Yes`; `Chained PRs recommended: Yes`;
`400-line budget risk: High`.

## Carry-forward / Open Questions

- **Snapshot growth** (accepted): ~2,880 rows/user/symbol/day, no retention in
  this change. Follow-up: cadence knob and/or extend `prune_snapshots`.
- `Trade.order_id` deferred (CLI has it; #57 omits it).
