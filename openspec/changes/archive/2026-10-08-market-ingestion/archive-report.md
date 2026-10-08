# Archive Report: market-ingestion

**Archived**: 2026-10-08
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 critical) — 7/7 requirements, 12/14 scenarios, 212/212 tests
**Delivery**: 2 chained PR slices (#37 → #38) → tracker #36 → `develop`
**Merged commit range**: `e9fbc38`…`eb1fdfb` on `develop`

## What Shipped

Phase 3 turns the boot-only worker into a real **global market ingester**: it
polls the two read-only public endpoints the client already exposes (tickers +
funding) on an interval and idempotently persists time-series snapshots shared
by all users. Two new **global** models (no `user` FK, not `UserOwnedModel`) land
in the existing `trading` app, fed by one narrow ingestion module and a real
worker loop with backoff and clean shutdown. Strictly read-only — no order
surface, no new runtime dependency (no RQ). `src/` and `accounts` untouched;
this adds the first `web/ → src/` import, the intended direction.

| Area | Delivered |
|------|-----------|
| Global models | `web/trading/models.py` — `FundingSnapshot`, `TickerSnapshot` (no FK, `UniqueConstraint(symbol, ts)`) |
| Migration | `web/trading/migrations/0002_market_snapshots.py` — additive; `makemigrations --check` green (CI gate) |
| Ingestion service | `web/trading/ingest.py` — `fetch_market` (reuses `src.monitor.fetch_rows`, epoch-ms→UTC once) + `persist_market` (`bulk_create(ignore_conflicts=True)`, one `transaction.atomic()`) |
| Worker loop | `web/worker.py` — `INGEST_POLL_SECONDS` (default 30), `min(backoff*2, 300)`, per-cycle log, SIGTERM/SIGINT `Event`; `idle_loop` kept byte-compatible for `scheduler.py` |
| Scheduler | `web/scheduler.py` — unchanged; still boots via `worker.idle_loop` (R5) |
| Tests | `tests/web/test_ingest.py` (13), `tests/web/test_service_stubs.py` (10) — stub client, no sockets; `test_boundary.py` + order surface green |
| W2 fix | `71e3f4e` (develop `1e3d093`) — skip rows with no market data in `fetch_market` |
| W2b fix | `7fd05d9` (develop `ee687c2`) — decide funding and ticker presence per series |

## Requirement Outcomes

| Req | Domain | Outcome | Notes |
|-----|--------|---------|-------|
| R1 | market-ingestion | ✅ Green | Global models carry no owner; unique `(symbol, ts)` per model (constraint introspection) |
| R2 | market-ingestion | ✅ Green | Re-persist identical rows → `(0, 0)`; `bulk_create(ignore_conflicts=True)` |
| R3 | market-ingestion | ✅ Green | Round-trip; UTC-aware `ts` + raw epoch-ms `next_funding_time`; empty symbols AND empty API response persist `(0, 0)` |
| R4 | market-ingestion | ✅ Green | One cycle ingests + returns 0; backoff `[60,120,240,300,300]` then recovery; clean stop between cycles |
| R5 | market-ingestion | ✅ Green | Worker and scheduler both boot one iteration (`idle_loop` compatible) |
| R6 | market-ingestion | ⚠️ Partial | Core has no Django import (✅); "Web may depend on core" direction proven implicitly by import success, no explicit assertion (W3) |
| R7 | market-ingestion | ⚠️ Partial | No order surface in new code (✅); "dependency file unchanged" verified by `git diff` only, no test (W4) |

**Legend**: ✅ green · ⚠️ partial (test-coverage gap, invariant holds).

## Carry-Forward Items

1. **Retention/pruning deferred by design D2** — snapshots accumulate
   unbounded: 4 symbols × 2880 polls/day (30 s) = **~11,520 rows/table/day**.
   Ship-without-prune was a deliberate, documented deferral (not silent
   accumulation). **Later add `prune_snapshots --older-than=<days>`**, scheduled
   by `pg_cron` or the worker; add a `ts` index then if deletes get hot.
   ⚠️ **DO NOT lose this item.**
2. **R6 web→core direction untested (W3)** — `tests/test_boundary.py` asserts
   only the forbidden direction (`src/` imports no Django). Add a boundary test
   asserting `src/` does not import `web`/`trading`/`scheduler`.
3. **R7 dependency-file invariant untested (W4)** — add a guard test that no
   new runtime import appears in `web/`/`src/` outside the declared set.
4. **`design.md` snippet is stale (SUGGESTION 1)** — `design.md:62-68` uses
   `len(bulk_create(..., ignore_conflicts=True))` as the inserted count, which is
   wrong (returns all attempted rows). Shipped code uses a row-count delta and is
   correct; the design doc was left as-is in the audit trail. Correct it if the
   doc is ever reused as a template.
5. **Infinite-loop deployed behavior (SUGGESTION 2)** — `run_loop(iterations=None)`
   with no signal loops forever by design (long-running worker); worth a one-line
   docstring note.
6. **`MultiFernet` key rotation** — out of scope (pre-existing, unchanged).

## Verify Findings (non-blocking, fix before the noted trigger)

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| W2 | Medium | Empty API response fabricated `(2,2)` rows instead of `(0,0)`, violating R3 | ✅ **Closed** — `71e3f4e` (develop `1e3d093`) + 5 tests; probes a1–a3 return `(0,0)` |
| W2b | Low | Whole-row guard dropped a real funding payload when all three price fields were `None` | ✅ **Closed** — `7fd05d9` (develop `ee687c2`) decides funding and ticker presence per series |
| W1 | Low | `tasks.md` checkboxes all `[ ]` despite completed work (29 unchecked) | ✅ **Fixed at archive** — all 29 boxes checked in archived copy |
| W3 | Low | R6 "Web may depend on core" has no explicit boundary test | Open — add reverse-direction assertion |
| W4 | Low | R7 "Dependency file unchanged" is untested | Open — add runtime-import guard test |
| S1 | Suggestion | `design.md` `persist_market` snippet uses wrong `len(bulk_create(...))` count | Documented (design bug caught in apply; shipped code correct) |
| S2 | Suggestion | `run_loop(iterations=None)` infinite-loop deployed behavior undocumented | Opportunistic docstring note |
| S3 | Suggestion | Guard funding-without-price limitation not documented | Superseded by W2b fix (per-series guard) |

**Apply design bug**: `len(bulk_create(ignore_conflicts=True))` returns the rows
*attempted*, not *inserted* — the design snippet's count was wrong on duplicate
input. The shipped `persist_market` uses a row-count delta and is correct; the
adversarial probe confirmed the stale formula returned 2 while inserting 0.

## SDD Cycle Complete

Planned → implemented → verified (re-verified, W2 fixed and closed) → archived.
Delta spec merged into the main spec store:

- `openspec/specs/market-ingestion/spec.md` (new capability — full spec, R1–R7)

No existing capability was modified (`core-domain-boundary` and
`security-invariants` were constraints to satisfy, not alter).

Archive audit trail: `openspec/changes/archive/2026-10-08-market-ingestion/`
(explore, proposal, design, specs, tasks, verify-report).

## Traceability — Engram Observation IDs

| Artifact | Observation ID |
|----------|----------------|
| `sdd/market-ingestion/apply-progress` | 1340 |
| `sdd/market-ingestion/verify-report` | 1342 |

Proposal/spec/design/tasks have no standalone Engram observations — they live in
the OpenSpec file store (both delta and merged main spec). Merged specs have no
standalone observations either; they live in the OpenSpec file store.
