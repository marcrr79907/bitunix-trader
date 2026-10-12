# Exploration: smc-zones-signals (issue #74, Fase B2)

## Executive Summary

B2 is the SECOND pure SMC core piece. It consumes the FROZEN B1 seam
(`src/smc/{config,swings,structure}.py`) and adds three new framework-free
modules: `zones.py` (order blocks, FVG, EQH/EQL, liquidity sweeps), `range.py`
(dealing range / equilibrium / premium-discount), and `signals.py` (confluence →
`Setup` with entry/SL/TP + R:R). No new dependency, no Django, no I/O, no order
execution. B2 clones the exact B1 conventions (NamedTuple records, list-in /
sparse-list-out, never-raise, stdlib-only, plain constants in `smc/config.py`).

**B2 is materially bigger than B1** (~3 modules + 3 test files vs B1's 2+2) and
should ship as a **CHAINED PR**, not a single PR. Details in the last section.

---

## 1. B1 seam recap (what B2 consumes — DO NOT CHANGE)

Read from `src/smc/swings.py` and `src/smc/structure.py`. This is the frozen
public contract; B2 imports it read-only.

### Records (stdlib `NamedTuple`, lowercase `kind` literals)

```python
class Swing(NamedTuple):          # src/smc/swings.py
    kind: str      # "high" | "low"
    index: int
    price: float

class LabeledSwing(NamedTuple):   # src/smc/structure.py
    kind: str      # "high" | "low"
    index: int
    price: float
    label: str     # "HH" | "HL" | "LH" | "LL"

class StructureEvent(NamedTuple): # src/smc/structure.py
    kind: str      # "bos" | "choch"
    index: int
    price: float   # breaking reference level at that bar
    direction: str # "bullish" | "bearish"
    trend: str     # trend AFTER the event: "up" | "down"
```

### Function signatures

```python
find_swings(highs: list[float], lows: list[float], *,
            left: int = SWING_LEFT, right: int = SWING_RIGHT) -> list[Swing]
label_swings(swings: list[Swing]) -> list[LabeledSwing]
trend_state(labeled: list[LabeledSwing]) -> list[str | None]
find_structure(highs: list[float], lows: list[float], closes: list[float], *,
               left: int = SWING_LEFT, right: int = SWING_RIGHT,
               use_close: bool = USE_CLOSE) -> list[StructureEvent]
```

### Conventions B2 MUST keep (verbatim mirror of B1 / `indicators.py`)

- `from __future__ import annotations` at the top of every module.
- **No classes** anywhere in `src/` — only stdlib `NamedTuple` records for
  structured outputs; plain functions otherwise. No dataclass, no dict payloads.
- **Lists in, sparse lists out.** Event/record lists carry their own `index`;
  never a positional alignment unless explicitly a same-length series.
- **Never raise.** Empty / too-short / mismatched-length input → `[]`. Guard
  clauses return `[]` (or `None`), never throw.
- **Pure / deterministic.** Same input + params → byte-identical output. No
  `datetime`, `random`, I/O, network, or global mutable state. Inputs not mutated.
- **Stdlib only.** No new dependency; may import `src.smc.*` intra-package.
- **Tunables** are plain module-level constants in `src/smc/config.py`, imported
  as function default arguments (single source of truth; caller may override per
  call). Existing: `SWING_LEFT=2`, `SWING_RIGHT=2`, `USE_CLOSE=True`.
- **Strict comparison** for swing equality (B1 already frozen) — B2 tolerances are
  explicit, not implicit.
- `src/smc/` is a package; `__init__.py` stays empty.
- **Read-only.** No order verb, no order path, ever.

### What B2 consumes specifically

- `find_swings(...)` → `list[Swing]` — the swing highs/lows for EQH/EQL and
  liquidity sweeps.
- `find_structure(...)` → `list[StructureEvent]` — the BOS/CHoCH displacement
  anchors for order blocks, and the trend direction for signal confluence.
- `trend_state(label_swings(swings))` — optional; the aligned trend series is
  C1-friendly but sparse `StructureEvent.trend` is enough for B2 signals.
- B1 does **not** expose `opens`; B2 needs a decision on candle direction (Q2).

---

## 2. Domain design (function signatures + data shapes)

### 2.1 `src/smc/zones.py`

New records (all stdlib `NamedTuple`, lowercase `kind`):

```python
class OrderBlock(NamedTuple):
    kind: str        # "bullish" | "bearish"
    index: int       # bar index of the opposite candle (OB candle)
    top: float       # upper edge of the zone
    bottom: float    # lower edge of the zone
    anchor: int      # bar index of the displacement event (BOS) that caused it

class FVG(NamedTuple):
    kind: str        # "bullish" | "bearish"
    index: int       # bar index of the MIDDLE candle (the gap bar)
    top: float       # upper edge of the gap
    bottom: float    # lower edge of the gap

class EqualLevel(NamedTuple):
    kind: str        # "eqh" | "eql"
    index: int       # bar index of the LATER of the two swings
    price: float     # the equal level (the later swing's price)
    twin: int        # bar index of the EARLIER of the two swings

class Sweep(NamedTuple):
    kind: str        # "high" | "low"  (which prior level was swept)
    index: int       # bar index of the sweeping candle
    level: float     # the prior swing level that was swept
    direction: str   # "bullish" | "bearish" (implied trade direction)
```

Functions:

```python
find_order_blocks(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float],
    structure: list[StructureEvent], *,
    lookback: int = OB_LOOKBACK,
) -> list[OrderBlock]: ...

find_fvg(
    highs: list[float], lows: list[float], *,
    min_gap: float = FVG_MIN_GAP,
) -> list[FVG]: ...

find_equal_highs_lows(
    swings: list[Swing], *,
    tolerance: float = EQ_TOLERANCE,
) -> list[EqualLevel]: ...

find_liquidity_sweeps(
    highs: list[float], lows: list[float], closes: list[float],
    swings: list[Swing], *,
    lookback: int = SWEEP_LOOKBACK,
) -> list[Sweep]: ...
```

**Detection rules (exact — these are the ones the spec MUST freeze):**

- **Order block** — "última vela opuesta al desplazamiento". For each
  `StructureEvent` with `kind == "bos"` at bar `t` (the displacement):
  - bullish BOS (`direction == "bullish"`): scan backward from `t - 1` down to
    `max(0, t - lookback)` and take the MOST RECENT bar `i` that is a **bearish
    candle** (`closes[i] < opens[i]`); its zone is `OrderBlock("bullish", i,
    top=highs[i], bottom=lows[i], anchor=t)`. No opposite candle in the window →
    no OB (never raise).
  - bearish BOS mirror: most recent **bullish candle** (`closes[i] > opens[i]`),
    `OrderBlock("bearish", i, top=highs[i], bottom=lows[i], anchor=t)`.
  - `choch` events are NOT anchors in v1 (a CHoCH is a reversal start, not a
    continuation displacement). **Open decision Q3.**
  - Zone bounds = full candle range `[low, high]` (not body). **Open Q4.**
  - Output ordered by `index`.

- **FVG (3-candle rule)** — bullish when `highs[i-1] < lows[i+1]` (candle 1 high
  below candle 3 low); gap zone `[highs[i-1], lows[i+1]]` on the middle bar `i`.
  Bearish when `lows[i-1] > highs[i+1]`; zone `[highs[i+1], lows[i-1]]`. Emit
  only when `(top - bottom) >= min_gap`. Scan `i = 1 .. n-2`; output ordered by
  `index`. **Confirmation vs mitigation is out of scope** (B2 emits raw,
  unfilled gaps; tracking fill/mitigation is a render/alert concern). **Open Q5.**
  - `min_gap` units: absolute price units by default (**open Q6**), so fixtures
    stay exact and instrument-agnostic tuning is deferred to E1 calibration.

- **EQH/EQL** — over confirmed `Swing` records, compare CONSECUTIVE same-kind
  swings: two highs are EQH when `abs(a.price - b.price) <= tolerance`; mirror
  EQL. Emit `EqualLevel("eqh"/"eql", later.index, later.price, earlier.index)`.
  Equal-and-strict: `tolerance = 0.0` means only exact equality counts.
  **Open Q7** (consecutive vs any-within-window pairing).

- **Liquidity sweep** — a wick beyond a prior confirmed swing then close back
  inside. For each bar `t`, for each confirmed swing whose level exists and is
  within `lookback` bars before `t`:
  - swing low sweep (bullish implied): `lows[t] < swing.price` AND
    `closes[t] > swing.price` → `Sweep("low", t, swing.price, "bullish")`.
  - swing high sweep (bearish implied): `highs[t] > swing.price` AND
    `closes[t] < swing.price` → `Sweep("high", t, swing.price, "bearish")`.
  - Only the MOST RECENT qualifying swing per side per bar emits (no duplicate
    sweeps of the same stale level). Output ordered by `index`. **Open Q8**
    (close-back-inside the swing level vs inside the sweep candle body).

### 2.2 `src/smc/range.py`

```python
class DealingRange(NamedTuple):
    high: float
    low: float
    equilibrium: float   # (high + low) / 2
    index: int           # bar index at which the range is evaluated (last bar)

def dealing_range(
    highs: list[float], lows: list[float], *,
    lookback: int = RANGE_LOOKBACK,
) -> DealingRange | None: ...

def classify_price(price: float, range_: DealingRange) -> str:
    # "premium" | "discount" | "equilibrium"
```

- `dealing_range` takes the last `lookback` bars, `high = max(highs[-lookback:])`,
  `low = min(lows[-lookback:])`, `equilibrium = (high + low) / 2`. Returns `None`
  when input is empty (never raise). **Open Q9** — fixed lookback vs structure
  extremes (last swing high + last swing low). Recommend fixed lookback for v1
  (simpler, deterministic, no extra seam); a structure-extreme variant can be a
  separate function if C1/E1 needs it.
- `classify_price`: `price > equilibrium → "premium"`, `< → "discount"`,
  `== → "equilibrium"`.

### 2.3 `src/smc/signals.py`

```python
class Setup(NamedTuple):
    direction: str   # "long" | "short"   (trade direction)
    entry: float
    stop: float      # stop loss
    take_profit: float
    rr: float        # (take_profit - entry) / (entry - stop)  for long; mirror short
    score: int       # confluence score (0..4)
    index: int       # bar index the setup is evaluated at (anchor/last bar)

def find_setups(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float],
    swings: list[Swing], structure: list[StructureEvent], *,
    range_: DealingRange | None = None,
    min_rr: float = MIN_RR,
    min_confluence: int = MIN_CONFLUENCE,
    sl_buffer: float = SL_BUFFER,
) -> list[Setup]: ...
```

**Confluence model (the spec must freeze the exact scoring):**

- Direction candidate from the LATEST `StructureEvent`: `trend == "up"` → long,
  `"down"` → short. No event → no setups (never raise).
- Score = count of aligned components (each 0/1, max 4):
  1. **Structure** — latest event direction agrees with the candidate.
  2. **Order block** — an `OrderBlock` of matching kind exists (recent).
  3. **FVG** — an `FVG` of matching kind exists (recent).
  4. **Premium/discount** — long requires `classify_price(...) == "discount"`
     (buy in discount); short requires `"premium"`.
- Emit `Setup` only when `score >= min_confluence`.
- **entry/SL/TP derivation** (long; short mirrors):
  - `entry` = the proximal edge of the matching order block (long: `ob.top`;
    fall back to the FVG proximal edge when no OB).
  - `stop` = the distal edge of that zone minus `sl_buffer` (long: `ob.bottom -
    sl_buffer`).
  - `take_profit` = the preferred structural target: for long, `range_.high` when
    `range_` given and it yields `rr >= min_rr`, else `entry + MIN_RR_MULTIPLE *
    (entry - stop)`. **Open Q10** (target source: structure level vs fixed R
    multiple).
  - `rr = (take_profit - entry) / (entry - stop)` (long); mirror for short.
  - Emit only when `rr >= min_rr`; guard `entry != stop` (else skip, never raise).
- Output ordered by `index`. B2 is **read-only**: `Setup` is a computed proposal,
  never an order. **Open Q11** (RLogic target selection + `MIN_RR_MULTIPLE`).

---

## 3. Config — new tunables in `src/smc/config.py`

Plain module-level constants, imported as function defaults (mirror B1):

```python
# --- B2 zones / range / signals -------------------------------------------
OB_LOOKBACK = 10        # bars scanned back for the opposite OB candle
FVG_MIN_GAP = 0.0       # minimum gap size (price units) for an FVG
EQ_TOLERANCE = 0.0      # max |Δprice| for two swings to be an equal level
SWEEP_LOOKBACK = 20     # bars a prior swing stays "sweepable"
RANGE_LOOKBACK = 50     # bars in the dealing-range lookback window
SL_BUFFER = 0.0         # extra distance beyond the zone distal edge for the SL
MIN_RR = 2.0            # minimum reward:risk to emit a setup
MIN_CONFLUENCE = 3      # minimum confluence score (0..4) to emit a setup
```

All are overridable per call via keyword arguments. No class, no env, no I/O.

---

## 4. Determinism

Identical to B1 / `indicators.py`:

- No `datetime`, `random`, I/O, network, or global mutable state.
- Pure functions: same input + params → byte-identical output.
- Inputs not mutated.
- Never raise: empty / short / mismatched-length → `[]` (or `None` for the single
  `DealingRange`).
- Sparse record lists carry their own `index`.
- All records stdlib `NamedTuple` — immutable, tuple-unpackable, hashable.

---

## 5. Boundary

`tests/test_boundary.py` `PURE_MODULES` MUST gain the three new paths:

```python
PURE_MODULES = (
    "indicators.py",
    "metrics.py",
    "smc/config.py",
    "smc/swings.py",
    "smc/structure.py",
    "smc/zones.py",      # NEW
    "smc/range.py",      # NEW
    "smc/signals.py",    # NEW
)
```

`test_pure_modules_are_stdlib_only` has a negative-control fixture already
(`test_pure_module_scanner_flags_a_violation`), so the scanner is proven. The
Django check auto-covers any new `src/**/*.py` via `rglob`; only the stdlib-only
check is blind without the `PURE_MODULES` entries. `tests/test_dependency_guard.py`
independently allows `src.smc.*` intra-package imports (local roots) — no edit
needed there.

---

## 6. Open questions / decisions the spec MUST lock

| # | Question | Recommendation (to freeze in spec) |
|---|----------|-----------------------------------|
| Q1 | Does B2 take `opens`? | **YES** — order blocks need candle direction; pass OHLC. No new dep, matches the real data shape. |
| Q2 | OB candle direction without opens | Moot if Q1=yes: use `close < open` (bearish) / `close > open` (bullish). |
| Q3 | OB anchor = BOS only, or BOS + CHoCH? | **BOS only** in v1 (continuation displacement). CHoCH feeds reversal logic (out of scope). |
| Q4 | OB zone bounds | Full candle range `[low, high]` (proximal = high for bullish OB). Body-only is an alternative. |
| Q5 | FVG raw gap vs mitigation tracking | **Raw, unfilled gaps only.** Fill/mitigation is a render/alert concern (C1/D). |
| Q6 | FVG `min_gap` units | Absolute price units; fraction-of-price is the alternative, defer tuning to E1. |
| Q7 | EQH/EQL pairing | **Consecutive same-kind swings** within tolerance (deterministic, O(n)). |
| Q8 | Sweep close-back definition | Close back INSIDE the swept swing level (`close > swing_low` / `< swing_high`). |
| Q9 | Dealing-range source | **Fixed lookback** over last `RANGE_LOOKBACK` bars; structure-extreme variant deferred. |
| Q10 | TP source | Structure target (`range_.high/low`) when it clears `min_rr`; else a fixed R multiple. |
| Q11 | Confluence weights | Equal weight (1 each), max 4; threshold `MIN_CONFLUENCE`. |
| Q12 | Output NamedTuple names/fields | As designed in §2 — freeze for C1/E1 consumers. |
| Q13 | OB/`range_` recency window | OB uses the latest BOS; zones/FVG are "recent" if within `OB_LOOKBACK` of the anchor bar. |
| Q14 | `Setup.index` semantic | Bar index the setup is evaluated at (latest event/last bar). Freeze for C1. |

---

## 7. Risks

- **SMC school ambiguity** — OB definition (last opposite candle vs last down
  close), FVG confirmation vs mitigation, sweep window, dealing-range source all
  differ across ICT/LuxAlgo/TradingView. *Mitigation:* freeze every rule in the
  spec (§2) as pseudo-code, not prose; bull AND bear fixtures per rule.
- **No `opens` in the B1 seam** — OB candle direction is undefined without opens.
  *Mitigation:* Q1/Q2 — B2 takes `opens` explicitly (additive input, no B1
  change).
- **Fixture design** — need clean synthetic OHLC series that trigger EACH zone
  (bullish OB, bearish OB, bullish FVG, bearish FVG, EQH, EQL, sweep-high,
  sweep-low) without accidentally triggering others. *Mitigation:* reuse the B1
  fixture-helper style (literal series + hand-traced expectations); one small
  helper per test file, mirror `test_smc_structure.py`'s `_mirror`.
- **Downstream coupling (C1 render, E1 calibration)** — `OrderBlock`, `FVG`,
  `Setup` are public seams; renaming fields later ripples. *Mitigation:* freeze
  the shapes now (Q12), keep them minimal + immutable.
- **Patch 100% coverage** — every branch (no-opposite-candle, below-min-gap, no
  paired swing, score < threshold, rr < min, entry == stop) needs a covering test
  line. *Mitigation:* mirror the B1 edge battery per function; no untested guard.
- **Scope creep** — no render (C1), no alerts (D), no real-trade calibration
  (E1), no order execution. *Mitigation:* fence in the proposal.
- **Overlap/nesting ambiguity** — multiple OBs/FVGs can overlap; the spec must
  state whether overlapping zones merge or stay separate. *Recommend separate
  records, no merging* (simplest; merge is a C1 concern).

---

## 8. Proposed scope boundary + PR shape (honest size estimate)

### Size estimate

| File | Impl | Tests | Total |
|------|------|-------|-------|
| `src/smc/zones.py` | ~160 | `tests/test_smc_zones.py` ~250 | ~410 |
| `src/smc/range.py` | ~70 | `tests/test_smc_range.py` ~120 | ~190 |
| `src/smc/signals.py` | ~140 | `tests/test_smc_signals.py` ~200 | ~340 |
| `src/smc/config.py` | +9 | — | +9 |
| `tests/test_boundary.py` | +3 | — | +3 |
| **Total** | **~380** | **~570** | **~950** |

**~950 changed lines — well past the 400-line review budget. `400-line budget
risk: High`.**

### Recommended: CHAINED PRs, 3 slices

B2 is NOT B1: three modules, three test files, and `signals.py` depends on both
`zones.py` and `range.py`. A single PR would hand the reviewer ~950 lines of
closely-related logic — exactly the cognitive-load situation the chained-PR guard
exists to prevent. Anyway, unlike B1, the three modules have a real dependency
order and each is an autonomous, independently-verifiable deliverable.

Chain (Feature Branch Chain, base = a `feat/smc-zones-signals` tracker branch):

1. **Slice 1 — `zones.py`** (~410 lines): OB, FVG, EQH/EQL, sweeps + boundary
   entry + `tests/test_smc_zones.py`. Autonomous: pure detection over B1 records.
   Rollback: delete module + tests, revert `PURE_MODULES`.
2. **Slice 2 — `range.py`** (~190 lines): dealing range, equilibrium,
   premium/discount + boundary entry + `tests/test_smc_range.py`. Independent of
   slice 1 (consumes only OHLC). Smallest slice.
3. **Slice 3 — `signals.py`** (~340 lines): confluence → `Setup` (entry/SL/TP/R:R)
   + boundary entry + `tests/test_smc_signals.py`. Consumes slices 1 & 2.

The issue's suggested split (`zones+range | signals`) is the **2-slice**
alternative: slice 1 becomes ~600 lines (**High** budget risk) and slice 2 ~340.
If the reviewer prefers two PRs, fold `range.py` into the `signals.py` slice
(range + signals ≈ 520) and keep `zones.py` alone (~410) — still slightly over,
but the cleaner of the two-PR options.

**Recommendation: 3-slice chain.** Each slice has a clear start, clear finish,
autonomous scope, its own verification (`pytest`, ruff, patch 100%), and a trivial
rollback (pure additive module).

### Out of scope (fence)

- Render (C1), alerts (D), calibration with real trades (E1).
- FVG mitigation/fill tracking, zone merging.
- Any Django/web/endpoint/migration; any new dependency; any order execution.

---

## Affected Areas

- **NEW**: `src/smc/zones.py`, `src/smc/range.py`, `src/smc/signals.py`.
- **EDIT**: `src/smc/config.py` (+8 B2 constants).
- **NEW**: `tests/test_smc_zones.py`, `tests/test_smc_range.py`,
  `tests/test_smc_signals.py`.
- **EDIT**: `tests/test_boundary.py` (`PURE_MODULES` += 3 paths).
- **ARCHIVE-TIME**: new `openspec/specs/smc-zones-signals/spec.md`.

No `web/`, no Django model, no migration, no endpoint — pure logic only.

## Ready for Proposal

**YES** — architecture is a direct clone of the proven B1 pattern; no dependency,
no Django, no migration. The spec MUST lock: OB input/definition (Q1–Q4), FVG
scope (Q5–Q6), sweep/range rules (Q8–Q9), confluence + entry/SL/TP/R:R (Q10–Q11),
and the output NamedTuple shapes (Q12–Q14).
