# Design: setup-outcomes

## Technical Approach

Same split as the ledger (#260): the resolution math is a new additive pure
helper in `src/smc/signals.py` next to `capture_setups`; the persistence
pipeline is a new `evaluate_setups` command following the `run()`-seam pattern
of `backfill_candles`/`prune_snapshots`; a global `SetupOutcome` model records
one resolution per setup (1:1, overwrite on re-evaluation). `Setup`, `Candle`,
and the SMC engine are untouched; the command reads only `Setup` + `Candle`,
writes only `SetupOutcome`, zero network. The six explore.md ambiguities are
resolved by the proposal's binding "Recorded decisions".

## Architecture Decisions

### D1 — Pure resolver: additive helper in `src/smc/signals.py` (A), not a new module (B), not `web/` (C)

**Choice**: `resolve_setup(direction, entry, stop, take_profit, candles, *, horizon_bars=200) -> OutcomeRecord` in `src/smc/signals.py`, additive next to `capture_setups`. Inputs are plain values: direction str, entry/stop/take_profit floats, `candles: list[(time, high, low)]` ascending with `time > anchor_time` (caller filters). Output is an `OutcomeRecord` NamedTuple (`status, resolved_time, bars_to_resolution, mfe_r, mae_r, sl_then_tp`) — module pattern is NamedTuple (`Setup`, `SetupRecord`), same immutability and equality the pure tests already assert.

**Alternatives rejected**: (B) new `src/smc/outcomes.py` — a new pure module must be registered in `tests/test_boundary.py::PURE_MODULES`; one more file and one more test edit for one function (same reasoning as the ledger's D1-A′). (C) resolver in `web/` — duplicates outcome math outside `src/smc/` and is untestable without Django, defeating the DB-free five-state unit test (R9). *Note*: supersedes the proposal's Affected Areas entry `src/smc/outcomes.py`.

**Reason**: one home for SMC math, zero duplication, no boundary registration — `test_boundary.py` stays green unmodified (`smc/signals.py` already in `PURE_MODULES`).

### D2 — Global `SetupOutcome`, additive migration `0019_setupoutcome`

**Choice**: model in `web/trading/models.py`: `OneToOneField(Setup, on_delete=CASCADE, related_name="outcome")` (its unique index is the idempotency key), `status` Char(16), `resolved_time` BigInt null, `bars_to_resolution` Integer null, `mfe_r`/`mae_r` Float null, `sl_then_tp` Boolean null, `horizon_bars` Integer, `engine_version` Char(16), `evaluated_at` auto_now. Global like `Setup`: no `user` FK, not `UserOwnedModel`, absent from `OWNED_MODELS`. Migration `0019_setupoutcome` depends on `0018` (verified leaf), creates only `setup_outcomes`.

**Alternatives rejected**: ManyToOne FK — allows multiple outcomes per setup, forcing "latest" filtering at every read; the proposal fixes 1:1 overwrite. Extra `status` index — no aggregation consumer yet (additive later when one exists).

**Reason**: mirrors `Setup`'s global contract exactly (guards untouched); CASCADE keeps outcomes recomputable, never orphaned.

### D3 — Resolution walk: deterministic, conservative, no look-ahead

**Choice** (pseudo-code):

```
walked = candles[:horizon_bars]                  # ascending, time > anchor
touches(p, hi, lo) = lo <= p <= hi
r = abs(entry - stop); long = direction == "long"

a = first i with touches(entry, ...)             # activation
if a is None:                                    # not_triggered
    window = walked (full horizon)
    mfe_r/mae_r via direction formulas; mae_r = min(raw, 0)   # clamp
    → (not_triggered, None, None, mfe, mae, sl_then_tp=None)

for j in range(a, len(walked)):                  # resolution scan
    sl, tp = touches(stop), touches(tp)
    sl and tp → ambiguous @ j                    # conservative: never TP
    sl        → stop_loss   @ j
    tp        → take_profit @ j
else → expired @ None

window = walked[a : j+1 if resolved else end]    # MFE/MAE window
bars_to_resolution = j - a                       # 0 same candle; NULL unresolved
if status in {stop_loss, ambiguous} and r > 0:
    sl_then_tp = any(touches(tp) for k in range(j+1, len(walked)))
else: sl_then_tp = None
if r == 0: mfe_r = mae_r = sl_then_tp = None     # never divide by zero
resolved_time = walked[j].time, else NULL
```

Invariants: activation candle may itself resolve (`bars_to_resolution=0`); touches of stop/TP *before* activation are ignored (not_triggered, window = full horizon); the clamp is needed only for not_triggered — an activated window always contains the activation candle's adverse touch (≤ 0 by construction); empty `walked` → `not_triggered` with NULL MFE/MAE (never raises, per module contract); `sl_then_tp` reads strictly after `j` — it is a documented post-resolution statistic, never a decision input. The command also slices the queryset `[:horizon_bars]` (volumetry bound); results are identical because the resolver never walks beyond `horizon_bars`.

**Reason**: OHLC cannot order SL vs TP inside one candle — `ambiguous` (counted as SL in any aggregation, never a win) is the only honest conservative answer.

### D4 — `evaluate_setups`: `run()` seam, injected `now`, idempotent upsert

**Choice**: `web/trading/management/commands/evaluate_setups.py` with module-level `run(now, interval, horizon_bars, max_setups, dry_run, out) -> int`; `handle` only parses flags and reads the wall clock ONCE (`int(time.time())`), mirroring `prune_snapshots`. Selection: `Setup.objects.order_by("anchor_time", "id")`, filtered by `interval` when given (absent → every ledger interval; no distinct query needed). Per setup, the full-horizon gate `anchor_time + horizon_bars × INTERVAL_SECONDS[setup.interval] ≤ now` (R6; ineligible skipped, no write — canonical mapping from `trading.candles`). Candles: direct `Candle.objects.filter(symbol=, interval=, time__gt=anchor_time).order_by("time")[:horizon_bars]` (proposal's approach; composite index bounds it). Persistence: `SetupOutcome.objects.update_or_create(setup=setup, defaults={...})` — re-running duplicates nothing; another horizon overwrites the outcome, never the `Setup`. `--max-setups` slices the ordered queryset. `--dry-run` computes, reports `would_write`, skips persistence. `engine_version` copies `setup.engine_version` verbatim (R8). Final `out("evaluate done: ...")` line mirrors the sibling commands.

**Alternatives rejected**: per-`(symbol, interval)` candle cache — memory for no measured gain at cron scale; `market.quotes._db_rows` — drags a `market/` dependency into `trading/` for a before/want reshape the direct query doesn't need.

**Reason**: exact `backfill_candles`/`prune_snapshots` seam; `now` injected once keeps the loop deterministic (R6).

### D5 — Testing: two Strict TDD slices

**Choice**:
- **Slice 1** — `tests/test_smc_outcomes.py` (pure, DB-free): table-driven — 5 statuses, ambiguous-as-SL, `sl_then_tp` True/False/NULL, R=0 NULLs, long/short MFE/MAE sign formulas, `bars_to_resolution` 0 / M / NULL, not_triggered mae clamp, determinism (repeat-run equality). `tests/web/test_setup_outcomes_model.py`: global contract (no `user`, absent from `OWNED_MODELS` — AST pattern of `test_setups_model.py`), field types via `get_internal_type`, OneToOne `related_name`, migration AST (only `CreateModel`, no alter/delete, depends on `0018`), leaf `>= "0019"`.
- **Slice 2** — `tests/web/test_evaluate_setups.py`: direct `run()` calls with seeded `Candle` rows (`OutRecorder` pattern of `test_prune_snapshots.py`) + one `call_command` wiring test; idempotent re-run; horizon recalculation overwrites the outcome with `Setup` byte-identical; dry-run writes nothing; full-horizon gate skips, then evaluates when `now` advances; `--interval` / `--max-setups` selection order.

**Alternatives rejected**: mocking the ORM in pure tests (they need no Django at all); E2E/LiveServer (no HTTP surface — it's a batch command).

**Reason**: guards (`test_boundary.py`, `test_no_order_surface.py`, `test_owned_model_guard.py`) stay green unmodified; each spec scenario maps to one named test.

### D6 — Cron: `cron-evaluate` documented like its siblings

**Choice**: add `| cron-evaluate | 0 * * * * (hourly) | python web/manage.py evaluate_setups |` to the `docs/deployment.md` cron table and extend the dashboard instructions to a third service, same env rules (no gunicorn, no migrations, no Redis, no port).

**Alternatives rejected**: a loop inside `worker.py`/`scheduler.py` — couples evaluation cadence to the worker process and breaks the container-decoupled batch contract (`batch-jobs` R3).

**Reason**: identical contract to `cron-backfill`/`cron-prune`; hourly matches the 1h default capture cadence.

## Module Boundaries

| File | Owns |
|---|---|
| `src/smc/signals.py` | `OutcomeRecord` + `resolve_setup`. Pure: stdlib, no I/O, never raises. |
| `web/trading/models.py` | `SetupOutcome` row schema (persistence only, no math). |
| `web/trading/migrations/0019_setupoutcome.py` | Additive DDL. |
| `web/trading/management/commands/evaluate_setups.py` | Gate + queries + upsert. |
| `docs/deployment.md` | Cron contract. |

## Data Flow

```
cron-evaluate ──→ evaluate_setups.run(now, …)
                     │ Setup.objects (ordered ledger, full-horizon gate)
                     │ Candle.objects (per setup, time__gt, [:horizon])
                     ▼
              resolve_setup  (pure, src/smc/signals.py)
                     │ OutcomeRecord
                     ▼
              SetupOutcome.update_or_create(setup=…)   ← dry-run skips
```

## Data Model — `trading.SetupOutcome` (migration `0019_setupoutcome`, depends on `0018`)

| Field | Type | Null | Note |
|---|---|---|---|
| `setup` | OneToOne(Setup, CASCADE) | no | `related_name="outcome"`; unique = idempotency key |
| `status` | Char(16) | no | `take_profit`/`stop_loss`/`ambiguous`/`expired`/`not_triggered` |
| `resolved_time` | BigInteger | yes | resolution candle OPEN, UNIX s |
| `bars_to_resolution` | Integer | yes | from activation; 0 same-candle |
| `mfe_r` / `mae_r` | Float | yes | `mae_r ≤ 0`; NULL when R = 0 |
| `sl_then_tp` | Boolean | yes | only for `stop_loss`/`ambiguous` |
| `horizon_bars` | Integer | no | horizon used in THIS evaluation |
| `engine_version` | Char(16) | no | copied from the setup verbatim |
| `evaluated_at` | DateTime(auto_now) | no | changes on every re-run (1:1, no history) |

## Affected Areas (per slice)

| File | Slice | Action |
|---|---|---|
| `src/smc/signals.py` | 1 | Modify — `OutcomeRecord` + `resolve_setup` (~75) |
| `web/trading/models.py` | 1 | Modify — `SetupOutcome` (~30) |
| `web/trading/migrations/0019_setupoutcome.py` | 1 | Create (~40) |
| `tests/test_smc_outcomes.py` | 1 | Create (~130) |
| `tests/web/test_setup_outcomes_model.py` | 1 | Create (~70) |
| `web/trading/management/commands/evaluate_setups.py` | 2 | Create (~85) |
| `tests/web/test_evaluate_setups.py` | 2 | Create (~130) |
| `docs/deployment.md` | 2 | Modify (~6) |

Slice 1 ≈ 345 lines, Slice 2 ≈ 220; whole change ≈ 565.
`Decision needed before apply:` No.
`Chained PRs recommended:` Yes — two slices, each under the 400-line budget.
`400-line budget risk:` Medium whole-change, Low per slice.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (pure, DB-free) | 5 statuses, ambiguous-as-SL, `sl_then_tp`, R=0, sign formulas, clamp, determinism | Table-driven fixtures, NamedTuple equality |
| Unit (model) | Global contract, field types, migration AST, leaf | `get_internal_type` + AST, pattern of `test_setups_model.py` |
| Integration (command) | Gate, ordering, idempotency, dry-run, recalc, flags | Direct `run()` + one `call_command`, seeded `Candle` rows |
| E2E | None | No HTTP surface; guards + `makemigrations --check` |

## Rollback

Additive only. Revert the cron service first (no new runs), then the command,
the resolver, and the model. Reversing `0019` drops only `setup_outcomes`;
`Setup`, `Candle`, and the engine are untouched. Outcomes are recomputable at
any time from `Candle` + `Setup`. Never destructive.

## Open Questions

None blocking.
