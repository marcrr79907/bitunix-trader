# smc-zones Specification

## Purpose

Pure, deterministic Smart Money Concepts zone detection in `src/smc/zones.py`:
order blocks, fair value gaps, equal highs/lows, and liquidity sweeps. Lists in,
sparse `NamedTuple` records out; no I/O, stdlib only. Consumes the frozen B1 seam
(`Swing`, `StructureEvent`) read-only. New capability — no prior spec.

**Frozen shapes** (stdlib `NamedTuple`, lowercase `kind`, field order fixed for C1/E1):

| Record | Fields (in order) |
|--------|-------------------|
| `OrderBlock` | `kind:str, index:int, top:float, bottom:float, anchor:int` |
| `FVG` | `kind:str, index:int, top:float, bottom:float` |
| `EqualLevel` | `kind:str, index:int, price:float, twin:int` |
| `Sweep` | `kind:str, index:int, level:float, direction:str` |

## Requirements

### Requirement: R1 — Order blocks anchored on BOS

`find_order_blocks(opens, highs, lows, closes, structure, *, lookback=OB_LOOKBACK)`
MUST emit one `OrderBlock` per `StructureEvent` with `kind == "bos"`. For a bullish
BOS at bar `t`, the OB candle MUST be the MOST RECENT bar `i` in
`[max(0, t-lookback), t-1]` with `closes[i] < opens[i]` (bearish candle); the zone
MUST be `top=highs[i], bottom=lows[i]`, `anchor=t`, `kind="bullish"`. Bearish BOS
MUST mirror (most recent `closes[i] > opens[i]`, `kind="bearish"`). `choch` events
MUST NOT anchor an OB. If no opposite candle exists in the window, no record is
emitted (never raise). Output MUST be ordered by `index`.

#### Scenario: Bullish OB from the last opposite candle

- GIVEN a bullish BOS at bar `t`, with bearish candles at `i1 < i2 < t`
- WHEN `find_order_blocks` runs
- THEN one `OrderBlock("bullish", i2, top=highs[i2], bottom=lows[i2], anchor=t)` is emitted

#### Scenario: Bearish OB mirrors

- GIVEN a bearish BOS at bar `t` with a recent bullish candle at `i`
- WHEN it runs
- THEN one `OrderBlock("bearish", i, top=highs[i], bottom=lows[i], anchor=t)` is emitted

#### Scenario: CHoCH is not an anchor

- GIVEN a `choch` event and no `bos` event
- WHEN it runs
- THEN the result is `[]`

#### Scenario: No opposite candle in window

- GIVEN a bullish BOS whose `lookback` window has only bullish candles
- WHEN it runs
- THEN no `OrderBlock` is emitted (no raise)

### Requirement: R2 — Fair value gaps (3-candle rule)

`find_fvg(highs, lows, *, min_gap=FVG_MIN_GAP)` MUST scan `i = 1..n-2`. A bullish
FVG at `i` requires `highs[i-1] < lows[i+1]`, with zone `top=lows[i+1]`
(the upper edge), `bottom=highs[i-1]` (the lower edge). A bearish FVG requires
`lows[i-1] > highs[i+1]`, with zone `top=lows[i-1]`, `bottom=highs[i+1]`. `top`
MUST be `>=` `bottom` in both cases. A gap MUST be emitted only when
`(top - bottom) >= min_gap`. `index` MUST be the middle bar `i`. Output MUST be
ordered by `index`. Raw, unfilled gaps only — mitigation/fill tracking is out of
scope.

#### Scenario: Bullish FVG

- GIVEN `highs=[10,10,12]`, `lows=[8,8,11]` at `i=1` with `highs[0] < lows[2]`
- WHEN `find_fvg` runs
- THEN `FVG("bullish", 1, top=10.0, bottom=11.0)` is emitted when gap `>= min_gap`

#### Scenario: Bearish FVG mirrors

- GIVEN `lows[i-1] > highs[i+1]`
- WHEN it runs
- THEN `FVG("bearish", i, top=lows[i-1], bottom=highs[i+1])` is emitted

#### Scenario: Gap below threshold is skipped

- GIVEN a 3-bar overlap with `(top - bottom) < min_gap`
- WHEN it runs
- THEN no `FVG` is emitted

### Requirement: R3 — Equal highs / equal lows

`find_equal_highs_lows(swings, *, tolerance=EQ_TOLERANCE)` MUST compare
CONSECUTIVE same-kind swings in `swings` (ascending `index`). Two highs are EQH
when `abs(earlier.price - later.price) <= tolerance`; lows mirror as EQL. The
record MUST be `EqualLevel("eqh"|"eql", index=later.index, price=later.price,
twin=earlier.index)`. `tolerance=0.0` MUST mean exact equality only. Output MUST
be ordered by `index`.

#### Scenario: EQH within tolerance

- GIVEN consecutive highs at `(1, 100.0)` and `(5, 100.2)` with `tolerance=0.5`
- WHEN `find_equal_highs_lows` runs
- THEN `EqualLevel("eqh", 5, 100.2, twin=1)` is emitted

#### Scenario: Zero tolerance requires exact equality

- GIVEN consecutive highs `100.0` and `100.2` with `tolerance=0.0`
- WHEN it runs
- THEN no `EqualLevel` is emitted

#### Scenario: Non-consecutive highs are not paired

- GIVEN highs `A`, a low, then high `B` — the highs do not share an adjacent same-kind pair
- WHEN it runs
- THEN no pair is emitted for `A`/`B`

### Requirement: R4 — Liquidity sweeps

`find_liquidity_sweeps(highs, lows, closes, swings, *, lookback=SWEEP_LOOKBACK)`
MUST emit a `Sweep` at bar `t` when a confirmed swing within `lookback` bars
before `t` is wicked beyond and price closes back inside the level. A swing low is
swept when `lows[t] < swing.price` AND `closes[t] > swing.price` →
`Sweep("low", t, swing.price, "bullish")`. A swing high is swept when
`highs[t] > swing.price` AND `closes[t] < swing.price` →
`Sweep("high", t, swing.price, "bearish")`. At most the MOST RECENT qualifying
swing per side per bar MUST emit. Output MUST be ordered by `index`.

#### Scenario: Bullish sweep of a low

- GIVEN swing low at `100.0`, bar `t` with `lows[t]=99.5`, `closes[t]=100.5`
- WHEN `find_liquidity_sweeps` runs
- THEN `Sweep("low", t, 100.0, "bullish")` is emitted

#### Scenario: Bearish sweep of a high

- GIVEN swing high at `110.0`, bar `t` with `highs[t]=110.5`, `closes[t]=109.0`
- WHEN it runs
- THEN `Sweep("high", t, 110.0, "bearish")` is emitted

#### Scenario: Close does not return inside

- GIVEN `lows[t] < swing.price` but `closes[t] <= swing.price`
- WHEN it runs
- THEN no `Sweep` is emitted

#### Scenario: Stale level outside lookback

- GIVEN a swing more than `lookback` bars before `t`
- WHEN it runs
- THEN it is not considered for a sweep

### Requirement: R5 — Determinism, purity, never-raise

Every finder MUST be pure (same input + params → byte-identical output), MUST NOT
mutate inputs, and MUST NOT use `datetime`, `random`, I/O, or global mutable
state. Records MUST be stdlib `NamedTuple`. Empty, too-short, or
mismatched-length input MUST return `[]` and MUST NOT raise.

#### Scenario: Empty in, empty out

- GIVEN empty OHLC lists
- WHEN any finder runs
- THEN it returns `[]` without raising

**Edge-case matrix**

| Input / condition | Result |
|-------------------|--------|
| `len(highs) != len(lows)` | `[]` |
| fewer than 3 bars for FVG | `[]` |
| no `bos` events | no `OrderBlock` |
| no opposite candle in OB window | no `OrderBlock` |
| gap `< min_gap` | no `FVG` |
| `tolerance=0.0`, unequal prices | no `EqualLevel` |
| sweep wick without close-back-inside | no `Sweep` |
| swing older than `lookback` | not sweepable |
| overlapping zones | separate records, never merged |
