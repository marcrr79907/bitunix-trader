# smc-setup-outcomes Specification

## Purpose

Resolve every `Setup` from the ledger against the real candles that follow it
and record **what happened next** — TP, SL, ambiguous, expired, not-triggered —
plus MFE/MAE in R and **`sl_then_tp`**: setups that touched SL and, had the
stop held, would have reached TP. Second link of the measurable-baseline chain:
the ledger stores intentions, outcomes measure them. Read-only surface — never
an order.

## Requirements

### Requirement: R1 — Global SetupOutcome model

`trading` MUST define a GLOBAL `SetupOutcome`: no `user` FK, MUST NOT inherit
`UserOwnedModel`, MUST NOT be in `OWNED_MODELS`. It MUST be
`OneToOneField(Setup)` with fields: `status` Char(16) restricted to
`take_profit | stop_loss | ambiguous | expired | not_triggered`;
`resolved_time` BigInt nullable (OPEN time, UNIX seconds, of the resolving
candle); `bars_to_resolution` Integer nullable; `mfe_r` / `mae_r` Float
nullable; `sl_then_tp` Boolean nullable; `horizon_bars` Integer (horizon used
in THIS evaluation); `engine_version` Char(16); `evaluated_at` DateTime(auto).
The migration MUST be additive: it creates only `setup_outcomes` and keeps
`makemigrations --check` green.

#### Scenario: Global, outside ownership

- GIVEN `SetupOutcome`, WHEN inspected, THEN it has no `user`, is absent from `OWNED_MODELS`, and links one-to-one to `Setup`

#### Scenario: Additive migration

- GIVEN the change, WHEN migrations are applied and checked, THEN only `setup_outcomes` is created and `makemigrations --check` pends nothing

### Requirement: R2 — Deterministic resolution semantics

Resolution MUST walk candles of the same `(symbol, interval)` with
`time > anchor_time`, ascending, up to `horizon_bars` candles (default 200),
using only each candle's OHLC (no look-ahead). A candle "touches" a price when
`low ≤ price ≤ high`. Outcomes:

| Status | Condition |
|---|---|
| `not_triggered` | entry never touched within the horizon |
| `take_profit` | after activation, a candle touches `take_profit` and not `stop`, with no earlier resolution |
| `stop_loss` | after activation, a candle touches `stop` and not `take_profit`, with no earlier resolution |
| `ambiguous` | the first post-activation resolution candle touches `stop` AND `take_profit` in the same candle |
| `expired` | the horizon is exhausted with no stop/TP resolution |

`resolved_time` MUST be the resolution candle's `time`; NULL for
`not_triggered` and `expired`. `ambiguous` MUST be counted as `stop_loss` in
any aggregation (conservative): it MUST NEVER be reported as a win.

#### Scenario: TP before SL wins

- GIVEN a long setup whose horizon contains a candle touching TP before any candle touching stop, WHEN resolved, THEN status is `take_profit` and `resolved_time` is that candle's `time`

#### Scenario: Same-candle SL+TP is ambiguous, never optimistic

- GIVEN a post-activation candle whose range covers both `stop` and `take_profit`, WHEN resolved, THEN status is `ambiguous` with `resolved_time` = that candle, AND any aggregation counts it as a loss, never a win

#### Scenario: Horizon exhausted

- GIVEN a setup activated early whose price touches neither stop nor TP for the full `horizon_bars`, WHEN resolved, THEN status is `expired` with `resolved_time` NULL

### Requirement: R3 — Activation and bars_to_resolution

Activation MUST be the FIRST walked candle touching `entry`. `bars_to_resolution`
MUST equal the distance in candles from the activation candle to the resolution
candle: 0 when the same candle resolves, and NULL when the setup never
activated (`not_triggered`) or never resolved (`expired`).

#### Scenario: Resolves on the activation candle

- GIVEN the activation candle also touches `take_profit`, WHEN resolved, THEN `bars_to_resolution` is 0

#### Scenario: Resolution later

- GIVEN activation on candle N and resolution on candle N+M (M > 0), WHEN resolved, THEN `bars_to_resolution` is M regardless of how far the anchor precedes activation

#### Scenario: Never activated

- GIVEN entry is never touched in the horizon, WHEN resolved, THEN status is `not_triggered` and `bars_to_resolution` is NULL

### Requirement: R4 — MFE/MAE in R

With `R = |entry − stop|`, excursions MUST be computed over the window from
activation to resolution inclusive (to the horizon end if activated but
unresolved; over the full walked horizon when never activated):

| Direction | `mfe_r` | `mae_r` |
|---|---|---|
| long | `max((high − entry) / R)` | `min((low − entry) / R)` |
| short | `max((entry − low) / R)` | `min((entry − high) / R)` |

`mae_r` MUST be ≤ 0: for a never-activated setup whose price never crossed to
the adverse side, `mae_r` MUST be clamped to 0 (the formula alone could be
positive there). When `R = 0`, `mfe_r`, `mae_r`, and `sl_then_tp` MUST be NULL
(the resolver MUST NOT divide by zero). A resolved TP setup MUST have
`mfe_r ≥ rr`.

#### Scenario: Long excursion signs

- GIVEN an activated long setup whose window's highest high is `H_max` and lowest low is `L_min`, WHEN resolved, THEN `mfe_r == (H_max − entry)/R` and `mae_r == (L_min − entry)/R ≤ 0`

#### Scenario: Short excursion signs

- GIVEN an activated short setup, WHEN resolved, THEN `mfe_r == (entry − L_min)/R` and `mae_r == (entry − H_max)/R ≤ 0`

#### Scenario: R = 0 degrades to NULL

- GIVEN a setup with `entry == stop`, WHEN resolved, THEN `mfe_r`, `mae_r`, and `sl_then_tp` are NULL and nothing raises

### Requirement: R5 — sl_then_tp

`sl_then_tp` MUST be computed ONLY for status `stop_loss` or `ambiguous`: True
iff a candle STRICTLY AFTER the resolution candle touches `take_profit` within
the horizon; False otherwise. It MUST be NULL for every other status (including
`expired` with stop touched) and when `R = 0`.

#### Scenario: Stop then TP strictly later

- GIVEN a setup resolved as `stop_loss` on candle N, and a later candle within the horizon touching `take_profit`, WHEN resolved, THEN `sl_then_tp` is True

#### Scenario: Stop without later TP

- GIVEN a setup resolved as `stop_loss` with no TP touch in strictly later candles, WHEN resolved, THEN `sl_then_tp` is False

#### Scenario: Not applicable statuses stay NULL

- GIVEN statuses `take_profit`, `expired`, or `not_triggered`, WHEN resolved, THEN `sl_then_tp` is NULL

### Requirement: R6 — Full-horizon gating

A setup is eligible for evaluation only when the FULL horizon of candles is
available: `now ≥ anchor_time + horizon_bars × interval_seconds` (per the
canonical interval-seconds mapping). The command MUST take `now` ONCE and
inject it; MUST NOT read the wall clock inside the evaluation loop.
Ineligible setups MUST be skipped without writing an outcome.

#### Scenario: Incomplete horizon skipped

- GIVEN a setup whose `anchor_time + horizon_bars × interval_seconds` is in the future relative to the injected `now`, WHEN the command runs, THEN no `SetupOutcome` is written for it

#### Scenario: Becomes eligible later

- GIVEN a previously skipped setup and a `now` past its horizon end, WHEN the command runs again, THEN it is evaluated

### Requirement: R7 — evaluate_setups command

`manage.py evaluate_setups [--interval I] [--horizon-bars N] [--max-setups M]
[--dry-run]` MUST follow the established command pattern: a module-level
`run(...)` seam with injectable `out` and an injected `now`; `handle` only
parses flags. Rules:

- `--interval` is OPTIONAL: absent → every interval present in the `Setup`
  ledger (distinct); setups are processed in deterministic order, ascending
  `anchor_time`.
- `--horizon-bars` defaults to 200; it changes only the evaluation, never the
  `Setup` rows.
- Persistence MUST be idempotent via `update_or_create` keyed by the setup:
  re-running duplicates nothing; re-evaluating with another horizon overwrites
  the outcome.
- `--max-setups` bounds how many setups are processed per run.
- `--dry-run` MUST write nothing and report what would be written.
- The command MUST read only `Setup` and `Candle`, write only `SetupOutcome`,
  and make zero network calls.

#### Scenario: Idempotent re-run

- GIVEN a completed evaluation, WHEN the same command runs again, THEN outcome count is unchanged and no row is duplicated

#### Scenario: Horizon recalculation leaves Setup untouched

- GIVEN an existing outcome with `horizon_bars` 200, WHEN the command runs with `--horizon-bars 100`, THEN the outcome is overwritten with the new horizon and every `Setup` row is byte-identical

#### Scenario: Dry run writes nothing

- GIVEN eligible setups, WHEN `--dry-run`, THEN `SetupOutcome` count is unchanged and the report lists what would be written

#### Scenario: Optional interval selects all, deterministically

- GIVEN setups across intervals `1h` and `4h` and no `--interval`, WHEN the command runs, THEN both intervals are evaluated in ascending `anchor_time` order

### Requirement: R8 — Engine version stamp copy

`SetupOutcome.engine_version` MUST copy the evaluated setup's `engine_version`
verbatim (the composed stamp, e.g. `"1:w200"`), and re-evaluation MUST NOT
change it.

#### Scenario: Stamp copied verbatim

- GIVEN a setup stamped `"1:w200"`, WHEN evaluated and re-evaluated with another horizon, THEN the outcome's `engine_version` is `"1:w200"` both times

### Requirement: R9 — Purity, determinism, guards

The resolver MUST be a pure, deterministic, stdlib-only, DB-free, clock-free
function in `src/smc/` registered in `PURE_MODULES`: it receives setup
parameters and OHLC lists, returns a value object with all outcome fields, and
equal inputs produce identical outputs. Unit tests without DB MUST cover all
five statuses. The guards `test_boundary.py`, `test_no_order_surface.py`, and
`test_owned_model_guard.py` MUST stay green unmodified.

#### Scenario: Pure five-state test

- GIVEN deterministic OHLC fixtures and no database, WHEN the resolver runs, THEN each of the five statuses is produced by its fixture and repeated runs are identical

#### Scenario: Guards stay green

- GIVEN the new model, resolver, and command, WHEN the three guards and `makemigrations --check` run, THEN all pass without edits

#### Scenario: No network, no orders

- GIVEN a client that raises on any call, WHEN evaluation runs, THEN no network call is made and no order surface exists
