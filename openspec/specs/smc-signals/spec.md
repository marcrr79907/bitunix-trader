# smc-signals Specification

## Purpose

Pure, deterministic confluence scoring and trade-setup derivation in
`src/smc/signals.py`. Combines the latest B1 structure event with B2 zones and
range to emit a read-only `Setup` proposal. No I/O, stdlib only. `Setup` is a
computed proposal — NEVER an order. New capability — no prior spec.

**Frozen shape** (stdlib `NamedTuple`, field order fixed for C1/E1):

| Record | Fields (in order) |
|--------|-------------------|
| `Setup` | `direction:str, entry:float, stop:float, take_profit:float, rr:float, score:int, index:int` |

`direction ∈ {"long","short"}`; `score ∈ 0..4`; `index` = the bar the setup is
evaluated at (the latest structure event's index).

## Requirements

### Requirement: R1 — Direction candidate

`find_setups(opens, highs, lows, closes, swings, structure, *, range_=None,
min_rr=MIN_RR, min_confluence=MIN_CONFLUENCE, sl_buffer=SL_BUFFER)` MUST derive the
direction candidate from the LATEST `StructureEvent`: `trend == "up"` → long,
`"down"` → short. With no `StructureEvent`, it MUST return `[]` (never raise).

#### Scenario: Latest event sets direction

- GIVEN events ending with a `bullish` BOS (`trend="up"`)
- WHEN `find_setups` runs
- THEN the candidate direction is `"long"`

#### Scenario: No event, no setup

- GIVEN `structure=[]`
- WHEN it runs
- THEN it returns `[]`

### Requirement: R2 — Equal-weight confluence score

The score MUST be the count of aligned components (each 0/1, max 4):
(1) structure — the latest event direction agrees with the candidate;
(2) order block — an `OrderBlock` of matching kind exists within `OB_LOOKBACK`
bars of the anchor; (3) FVG — an `FVG` of matching kind exists within the same
recency window; (4) premium/discount — long requires
`classify_price(...) == "discount"`, short requires `"premium"`. Components MUST
be equally weighted (1 each). A `Setup` MUST be emitted only when
`score >= min_confluence`.

#### Scenario: All four aligned

- GIVEN a bullish structure, a recent bullish OB, a recent bullish FVG, and price in discount
- WHEN it runs
- THEN `score == 4`

#### Scenario: Missing one component

- GIVEN a bullish structure, a recent bullish OB, a bullish FVG, but price in premium
- WHEN it runs
- THEN `score == 3` (the PD component is 0)

#### Scenario: Below threshold suppressed

- GIVEN aligned components totalling `score == 2` and `min_confluence=3`
- WHEN it runs
- THEN no `Setup` is emitted

#### Scenario: No order blocks at all

- GIVEN structure and FVG aligned but no `OrderBlock`
- WHEN it runs
- THEN the OB component is 0 and scoring continues on the rest

### Requirement: R3 — Entry, stop, and take-profit derivation

For a long (short mirrors), `entry` MUST be the proximal edge of the matching
order block (`ob.top`), or the FVG proximal edge when no OB exists. `stop` MUST be
the distal edge minus `sl_buffer` (`ob.bottom - sl_buffer`; mirror short). For a
long, `take_profit` MUST be `range_.high` when `range_` is given and yields
`rr >= min_rr`, else `entry + MIN_RR_TP_R * (entry - stop)`. `rr` MUST be
`(take_profit - entry) / (entry - stop)` for a long (mirror short). A `Setup` MUST
be emitted only when `rr >= min_rr`; `entry == stop` MUST skip the record (never
raise).

#### Scenario: Structural target clears the gate

- GIVEN a long with `entry=100`, `stop=95`, `min_rr=2.0`, and `range_.high=115`
- WHEN it runs
- THEN `take_profit=115.0` and `rr=3.0`

#### Scenario: Fallback fixed-R target

- GIVEN a long whose `range_.high` yields `rr < min_rr` (or `range_ is None`)
- WHEN it runs
- THEN `take_profit = entry + MIN_RR_TP_R * (entry - stop)`

#### Scenario: R:R below the gate suppressed

- GIVEN a candidate whose computed `rr < min_rr`
- WHEN it runs
- THEN no `Setup` is emitted

#### Scenario: Degenerate stop skipped

- GIVEN `entry == stop`
- WHEN it runs
- THEN the record is skipped without raising

### Requirement: R4 — Output shape and ordering

Output MUST be a `list[Setup]` ordered by `index`. Each item MUST unpack as
`(direction, entry, stop, take_profit, rr, score, index)`. A `Setup` MUST be a
computed proposal only — it MUST NOT place, modify, or cancel any order.

#### Scenario: Ordered, immutable records

- GIVEN eligible setups
- WHEN `find_setups` returns
- THEN indices are non-decreasing and each item unpacks as the frozen 7-tuple

### Requirement: R5 — Determinism, purity, never-raise

`find_setups` MUST be pure (same input + params → byte-identical output), MUST NOT
mutate inputs, and MUST NOT use `datetime`, `random`, I/O, or global mutable
state. Empty, too-short, or mismatched-length input MUST return `[]` and MUST NOT
raise.

#### Scenario: Empty in, empty out

- GIVEN empty OHLC lists
- WHEN `find_setups` runs
- THEN it returns `[]` without raising

**Edge-case matrix**

| Input / condition | Result |
|-------------------|--------|
| no `StructureEvent` | `[]` |
| `score < min_confluence` | no `Setup` |
| no OB and no FVG for entry | no `Setup` |
| `rr < min_rr` | no `Setup` |
| `entry == stop` | record skipped |
| `range_ is None` | fixed-R fallback target |
| mismatched OHLC lengths | `[]` |

### Requirement: R6 — Engine version constant

`src/smc/config.py` MUST expose `SMC_ENGINE_VERSION` as a module-level string
constant, hand-bumped whenever scoring, thresholds, or the derivation chain
change. It MUST be a plain constant alongside the existing tunables (no class,
no loader, no env override) and MUST NOT alter any R1-R5 behavior.

#### Scenario: Constant is importable and stable

- GIVEN `src.smc.config`, WHEN imported, THEN `SMC_ENGINE_VERSION` is a non-empty `str`

#### Scenario: Scoring untouched

- GIVEN the frozen fixture set, WHEN `find_setups` runs after the constant is added, THEN outputs are byte-identical to before

### Requirement: R7 — Enriched capture helper

`src/smc/` MUST expose an additive pure helper (`capture_setups`) that returns,
for the same inputs and call chain as `get_smc_payload`, the enrichment the
frozen `Setup` does not carry: the anchor bar `index`, its `anchor_time`
resolved from a caller-supplied `times` list, and the ATR at that index. It
composes the payload chain with every tunable at its default; the caller owns
only the window length.

The helper MUST NOT modify `Setup`, `find_setups`, or their signatures. It MUST
NOT carry `SMC_ENGINE_VERSION`: the version is stamped once at the persistence
layer (R6 of `smc-setup-ledger`), so only one place knows it. The Django layer
MUST NOT reimplement the chain; it MUST call this one helper.

#### Scenario: Enriched record matches the frozen setup

- GIVEN a window yielding a `Setup`, WHEN the helper runs, THEN its direction, entry, stop, take-profit, R:R, score, and index match the `Setup` exactly

#### Scenario: Anchor time resolved like the payload

- GIVEN a window with `times`, WHEN the helper runs, THEN `anchor_time == times[setup.index]`, matching how `_serialize_smc` resolves `time`

#### Scenario: No setup yields an empty result

- GIVEN a window where `find_setups` returns `[]`, WHEN the helper runs, THEN it returns an empty result without raising

#### Scenario: ATR is nullable and anchored

- GIVEN a window shorter than the ATR warm-up, WHEN the helper runs, THEN `atr` is `None`; GIVEN a warm window, THEN `atr` equals `src.indicators.atr(...)[setup.index]`

#### Scenario: Purity preserved

- GIVEN equal inputs, WHEN the helper runs twice, THEN outputs are identical, inputs are unmutated, no clock or I/O is read, and imports are stdlib-only

**Edge-case matrix**

| Input / condition | Result |
|---|---|
| empty or mismatched OHLC | empty enrichment, no raise |
| `structure == []` | empty enrichment, no raise |
| `index` beyond ATR warm-up | `atr = None` |
| `index` out of window bounds | record skipped, no raise |
| `len(times) != len(closes)` | empty enrichment, no raise |
| frozen `Setup` 7-tuple | unchanged, order intact |
