# smc-structure Specification

## Purpose

Pure, deterministic Smart Money Concepts core in `src/smc/` (second pure-module
family after `indicators.py`). Lists in, sparse records out; no I/O, no network,
stdlib only. Provides fractal swing pivots, HH/HL/LH/LL labels, trend state, and
BOS/CHoCH events for downstream B2 (zones) and C1 (render). New capability — no
prior spec.

## Requirements

### Requirement: R1 — Fractal swing detection

`find_swings(highs, lows, *, left=SWING_LEFT, right=SWING_RIGHT)` MUST emit bar
`i` as a pivot HIGH iff `highs[i]` is STRICTLY greater than the `left` prior
highs and the `right` following highs (mirror for LOWS with strict `<`). Equal
levels MUST NOT be pivots. Only pivots with all `right` confirming bars present
MUST be emitted; the trailing `right` bars are UNCONFIRMED and MUST never be
emitted (no look-ahead).

- GIVEN `highs=[1,3,2,4,1]`, `lows=[0,1,0,2,0]`, `left=1, right=1`
- WHEN `find_swings` runs
- THEN pivots are `("high",1,3.0)` and `("high",3,4.0)`
- GIVEN `highs=[2,2,1]`, `left=1, right=1`
- WHEN it runs
- THEN no pivot is emitted for tie index `0` (strict inequality)

#### Scenario: Unconfirmed trailing pivot is not emitted

- GIVEN `highs=[1,5,1]`, `left=1, right=1`
- WHEN it runs
- THEN the last bar (a local max) is absent (no `right` confirmation)

### Requirement: R2 — Swing output shape and ordering

Output MUST be a `list[Swing]` in ascending `index` order, where `Swing` is a
stdlib `NamedTuple(kind:str, index:int, price:float)`, `kind ∈ {"high","low"}`.
No `confirmed` flag MAY be present.

#### Scenario: Ordered, immutable records

- GIVEN multiple pivots
- WHEN `find_swings` returns
- THEN indices are non-decreasing and each item unpacks as `(kind, index, price)`

### Requirement: R3 — Swing labeling

`label_swings(swings)` MUST emit `LabeledSwing(kind, index, price, label)` for
each swing from the SECOND same-kind swing onward: a high is `HH` if
`price > ` prior high else `LH`; a low is `HL` if `price > ` prior low else `LL`.
The FIRST swing of each kind is unlabeled and MUST be omitted.

#### Scenario: Bull labeling

- GIVEN highs `1→2→3` and lows `0→1→2`
- WHEN `label_swings` runs
- THEN labels are `HH, HL, HH, HL` (first high/low omitted)

#### Scenario: Bear labeling

- GIVEN highs `3→2→1` and lows `2→1→0`
- WHEN it runs
- THEN labels are `LH, LL, LH, LL`

### Requirement: R4 — Trend state

`trend_state(labeled)` MUST return a `list[str | None]` of
`"up" | "down" | "range" | None`, aligned to the `LabeledSwing` sequence;
leading positions before state is known MUST be `None`. `up` requires HH+HL,
`down` requires LH+LL, otherwise `range`.

#### Scenario: Range then up

- GIVEN a series with no confirmed directional structure
- WHEN `trend_state` runs
- THEN positions are `"range"`/`None`, and `"up"` once HH+HL hold

### Requirement: R5 — BOS events

`find_structure(highs, lows, closes, *, left=…, right=…, use_close=USE_CLOSE)`
MUST emit `StructureEvent(kind, index, price, direction, trend)` with
`kind="bos"` when, in an established trend, price closes (or wicks when
`use_close=False`) beyond the prior relevant swing in the trend direction:
bullish above the active swing high in `up`, bearish below the active swing low
in `down`. Break reference MUST be the bar CLOSE by default (`USE_CLOSE=True`).

#### Scenario: Bullish BOS

- GIVEN an established `up` trend and the active swing high `H`
- WHEN a close is above `H`
- THEN a `bos/bullish` event is emitted at that bar

#### Scenario: Bearish BOS

- GIVEN an established `down` trend and the active swing low `L`
- WHEN a close is below `L`
- THEN a `bos/bearish` event is emitted at that bar

#### Scenario: Close vs wick

- GIVEN a bar whose close is inside `H` but whose high exceeds `H`
- WHEN `find_structure` runs with default `use_close=True`
- THEN no BOS is emitted; with `use_close=False` it is

### Requirement: R6 — CHoCH events

`find_structure` MUST emit `kind="choch"` on the FIRST close (or wick when
`use_close=False`) against the established trend, and that break MUST flip the
trend. CHoCH MUST require a prior established trend. Labels MUST NOT gate CHoCH.

#### Scenario: Bearish CHoCH

- GIVEN an established `up` trend
- WHEN a close falls below the active swing low
- THEN a `choch/bearish` event is emitted and trend becomes `down`

#### Scenario: Bullish CHoCH

- GIVEN an established `down` trend
- WHEN a close rises above the active swing high
- THEN a `choch/bullish` event is emitted and trend becomes `up`

### Requirement: R7 — Active-level update after events

After each emitted event the active reference level MUST update to the most
recent relevant confirmed swing in the (possibly new) trend direction; the same
break MUST NOT re-fire on subsequent bars unless price closes beyond the
updated level.

#### Scenario: Level advances

- GIVEN a bullish BOS at level `H`
- WHEN the next relevant swing high `H2 > H` is confirmed
- THEN the active high becomes `H2` and a close above `H2` emits a new BOS

### Requirement: R8 — Seeding rule

With no established trend, the first decisive break MUST seed the trend
silently (no event). BOS/CHoCH MUST require at least one confirmed high AND one
confirmed low. CHoCH MUST NOT fire without a prior established trend.

#### Scenario: First break seeds silently

- GIVEN only unbroken swings
- WHEN the first break occurs
- THEN trend is set and no event is emitted

### Requirement: R9 — Determinism and purity

Every function MUST be pure: same input and params → byte-identical output;
inputs MUST NOT be mutated; no `datetime`, `random`, I/O, or global mutable
state. Records MUST be `NamedTuple` (`Swing`, `LabeledSwing`, `StructureEvent`).

#### Scenario: Repeatable and non-mutating

- GIVEN any OHLC lists
- WHEN a function runs twice
- THEN outputs are equal and the inputs are unchanged

### Requirement: R10 — Framework-free boundary

`src/smc/` MUST be a package (empty `__init__.py`) whose modules import stdlib
only, and MUST NOT import Django/`requests`/`src.client`, place orders, or do
I/O. `PURE_MODULES` in `tests/test_boundary.py` MUST gain `"smc/config.py"`,
`"smc/swings.py"`, `"smc/structure.py"`.

#### Scenario: Boundary green

- GIVEN the new modules
- WHEN `pytest tests/test_boundary.py` runs
- THEN Django and non-stdlib import checks pass

### Requirement: R11 — Edge and error handling

Empty, too-short, or mismatched-length input MUST return `[]` (or an aligned
`[]`/`None` series) and MUST NOT raise.

#### Scenario: Empty in, empty out

- GIVEN `highs=[]`/`lows=[]`
- WHEN any function runs
- THEN it returns `[]` without raising

**Edge-case matrix**

| Input | Result |
|-------|--------|
| empty series | `[]` |
| `len(highs) != len(lows)` | `[]` |
| `left=0` / `right=0` | valid, immediate-neighbour pivots |
| equal/plateau highs | no pivot (strict) |
| series ends at local extreme | trailing pivot absent |
| single swing per kind | label omitted (no `HH/LL`) |
| no established trend | first break seeds silently |
| close inside / wick beyond level | no BOS unless `use_close=False` |
| flat/range market | `"range"`, no BOS/CHoCH |
