# Archive Report: private-data-sync

**Archived**: 2026-10-10
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 criticals) — 12/12 requirements, 34/35 scenarios, 371/371 tests
**Delivery**: feature-branch-chain — tracker PR #61 (`feat/private-sync`) + child PRs #62 (`feat/private-sync-tier`) → #63 (`feat/private-sync-worker`) → #64 (`feat/private-sync-guards`), all merged to `develop`
**Merged commit range**: `5fcb5a8`…`8fcd5a6` on `develop` (tracker merge `8fcd5a6`; child merges `e42fa68` #62, `4a93022` #63, `11cc032` #64; branch commits `2835815` planning, `e9e78dd` data tier, `9b8d205` patch-gate fix, `c7ae02c` leverage reconciliation, `a75a1c7` worker, `39a8316` guards)

## What Shipped

Issue #57 (Fase 6b) makes the worker the first real consumer of `credentials.decrypt`
and the BitUnix private read-only API. The two live scanners force one seam:
`web/trading/` sits inside the credential scanner's `REQUEST_PATH` (no `decrypt`
allowed), so the new `web/trading/sync.py` is fetch + persist only; `web/worker.py`
is outside every scanned path, so it owns decryption and credential iteration
(R14.4 trusted zone). Three per-user owned models receive positions, account, and
history-trade snapshots. Strictly read-only (R11): no order surface, ever. Data
source for Fase 6c's UI (#58).

| Area | Delivered |
|------|-----------|
| Models | `web/trading/models.py` — `PositionSnapshot` (`(user,symbol,ts)` unique; `leverage` **Integer** null), `AccountSnapshot` (`(user,ts)`), `Trade` (`(user,trade_id)`, no `order_id`); all `UserOwnedModel` |
| Migration | `web/trading/migrations/0004_private_snapshots.py` additive; `makemigrations --check` clean |
| Sync module | `web/trading/sync.py` (new, 144 lines) — `_f`/`_i` coercion, `persist_positions/account/trades` (`bulk_create(ignore_conflicts=True)` + count delta), `sync_user`, `_fetch_trades` paginated like `journal.sync`; **no `credentials` import** |
| Worker | `web/worker.py` — `run_private_sync(client_factory=None)` iterating `ExchangeCredential.objects.filter(is_active=True)` unscoped, `decrypt` both columns, per-user `try/except → logger.warning`; `run_once` gains an isolated private step after ticks+candles; `(funding, ticker)` contract unchanged |
| Guard | `OWNED_MODELS` now includes the 3 new models; decrypt-free scan of `trading/` stays green |
| Tests | `tests/web/test_private_models.py`, `test_private_sync.py`, `test_worker_private_sync.py` + `test_owned_model_guard.py` / `test_isolation.py` extensions — 43 new/changed tests |
| Untouched | `src/`, `web/credentials.py`, `requirements.txt` (diff empty), `accounts/` |

## Requirement Outcomes

| Req | Domain | Outcome | Notes |
|-----|--------|---------|-------|
| R1 | private-data-sync | ✅ Green | 3 owned models, FK CASCADE + `for_user`, `(user,…)` `UniqueConstraint`s; `trade_id` reusable across users; additive migration. `leverage` is `IntegerField` (spec/design reconciled to Integer, WARNING 2) |
| R2 | private-data-sync | ✅ Green | `bulk_create(ignore_conflicts=True)` + count delta; identical re-persist → 0; empty input → 0 no raise |
| R3 | private-data-sync | ✅ Green | `sync.py` fetch + persist only; no `decrypt` import/call/bare/`getattr`; owned models touched only via `bulk_create`/`count` |
| R4 | private-data-sync | ✅ Green | Worker iterates active creds unscoped, decrypts, builds client, delegates to `sync_user`; runs after global ingest; `(funding,ticker)` preserved |
| R5 | private-data-sync | ✅ Green | Per-credential `try/except`; A raising never aborts B nor the global ingest |
| R6 | private-data-sync | ✅ Green | No order surface (scanner green); `requirements.txt` byte-identical; `src/` framework-free. Runtime-dep assertion is inspection-only (SUGGESTION 1) |
| R14.2 | per-user-isolation | ✅ Green | A≠B proven for all 5 owned models including the 3 new ones |
| R14.3 | per-user-isolation | ✅ Green | `OWNED_MODELS` = 5; scanner flags unscoped queries on the new models; `bulk_create`/`count` sanctioned |
| R14.4 | per-user-isolation | ✅ Green | Worker reads/decrypts/writes across users legitimately; `worker.py` outside guard `REQUEST_PATH` |
| R13 | security-invariants | ✅ Green | `decrypt` confined to worker; `sync.py` scanner-clean; worker decrypts an ACTIVE credential |
| R14 | security-invariants | ✅ Green | Same enforcement as R14.2/R14.3, now covering the 3 new models |
| R4b | market-ingestion | ✅ Green | Isolated private-sync step after ticks+candles; failure isolated; no active creds → no-op |

**Legend**: ✅ green · ⚠️ partial (invariant holds; test-coverage gap).

## Verify Findings (non-blocking)

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| W1 | Warning | Patch gate 99%, not 100% — `web/trading/sync.py` L124 (empty first trades page `break`) uncovered | ✅ **Resolved in `9b8d205`** — coverage test moved into WU1 (`test(sync): cover empty first trades page`); CI green on all 3 child PRs (#62/#63/#64) after the fix |
| W2 | Warning | `PositionSnapshot.leverage` was `IntegerField` while spec R1/design declared `Float` | ✅ **Resolved in `c7ae02c`** — spec R1 + design text reconciled to `Integer`; code, migration `0004`, and canonical spec now agree |
| W3 | Warning | `tasks.md` was 0/33 checked at verify time; completion not readable from the artifact | ✅ **Closed at archive** — archived copy is 33/33 `[x]` (0 unchecked), verified here |
| W4 | Warning | WU3 isolation tests have no independent RED (pure coverage over already-shipped WU1 behavior) | Noted — pipeline-evidence nuance, honestly disclosed in apply-progress `#1412`; not a code defect |
| S1 | Suggestion | R6 "runtime dependencies unchanged" verified only by empty `git diff`, no committed guard test | Noted — mirrors the archived candle-pagination SUGGESTION 1; candidate for a future dependency-guard change |

## Carry-Forward Items

1. **Private-snapshot growth has NO retention.** A per-cycle position/account
   snapshot series grows ~2,880 rows/user/symbol/day and `prune_snapshots` only
   covers the global `FundingSnapshot`/`TickerSnapshot` ticks — it does NOT touch
   `PositionSnapshot`/`AccountSnapshot`. **Flagged for a future change** (e.g. a
   `PRIVATE_SYNC_SECONDS` cadence knob and/or extending `prune_snapshots`).
   Deliberately not solved in 6b.
2. **`Trade.order_id` deferred** — present in the CLI row but omitted in 6b
   (issue #57 field list). Add if a future UI needs the order linkage.
3. **3 non-persisted intervals remain BitUnix-gap-filled.** The private sync
   persists only what the exchange returns; intervals the exchange does not serve
   are gap-filled by the existing BitUnix candle behavior, unchanged by 6b.
4. **S1 dependency-guard test** — optional committed guard asserting no new
   runtime import in `web/`/`src/` outside the declared set.

## SDD Cycle Complete

Planned (`2835815`) → implemented (`e9e78dd` data tier, `a75a1c7` worker,
`39a8316` guards) → verified (`pass_with_warnings`, 0 blockers, 0 criticals) →
WARNINGs resolved (`9b8d205` patch gate, `c7ae02c` leverage) → merged (PR #61
tracker + chain #62→#63→#64 → `develop`, `8fcd5a6`) → archived.

Delta specs merged into the main spec store (source of truth):

- `openspec/specs/private-data-sync/spec.md` — **created** (new capability, R1–R6,
  13 scenarios; delta copied verbatim as the canonical full spec).
- `openspec/specs/per-user-isolation/spec.md` — **updated**: R14.2 applies to all
  5 owned models; R14.3 `OWNED_MODELS` = 5 + new-model scanner scenario + sanctioned
  `bulk_create`/`count`; R14.4 extended to worker private persist. R14.1 unchanged.
- `openspec/specs/security-invariants/spec.md` — **updated**: R13 now consumed
  (sync.py decrypt-free, worker decrypts); R14 enforcement extended to the 3 new
  models. R11/R12 unchanged.
- `openspec/specs/market-ingestion/spec.md` — **updated**: **R4b added** (isolated
  private-sync step in the cycle). R1–R3, R5–R7 unchanged.

Archive audit trail: `openspec/changes/archive/2026-10-10-private-data-sync/`
(explore, proposal, specs, design, tasks, verify-report, archive-report).

## Merge Inventory (main store after sync)

| Domain | Action | Requirements | Scenarios |
|--------|--------|--------------|-----------|
| private-data-sync | Created | R1–R6 (6) | 13 |
| per-user-isolation | Updated | R14.1–R14.4 (4) | 13 (+5 new) |
| security-invariants | Updated | R11–R14 (4) | 19 (+5 new) |
| market-ingestion | Updated (R4b added) | R1–R7 (7) | +3 new |

No requirement was dropped; all pre-existing requirements outside the deltas are
preserved verbatim.

## Traceability — Engram Observation IDs

| Artifact | Observation ID |
|----------|----------------|
| `sdd/private-data-sync/explore` | (openspec file store; see archive folder) |
| `sdd/private-data-sync/proposal` | (openspec file store) |
| `sdd/private-data-sync/spec` | (openspec file store) |
| `sdd/private-data-sync/design` | (openspec file store) |
| `sdd/private-data-sync/tasks` | (openspec file store) |
| `sdd/private-data-sync/apply-progress` | Engram `#1412` |
| `sdd/private-data-sync/verify-report` | (openspec file store) |
| `sdd/private-data-sync/archive-report` | Engram `sdd/private-data-sync/archive-report` |

Merged specs have no standalone Engram observations — they live in the OpenSpec
file store (`openspec/specs/{private-data-sync,per-user-isolation,security-invariants,market-ingestion}/spec.md`).
