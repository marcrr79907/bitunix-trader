# Design: smc-zones-signals (issue #74, Fase B2)

## Technical Approach

Clone the frozen B1 contract (`src/smc/{swings,structure}.py`) into three new pure
modules. Stdlib `NamedTuple` records, lists-in / sparse-lists-out, never-raise,
inputs not mutated, tunables as plain `config.py` constants imported as defaults.
B2 **consumes B1 read-only** and its output shapes are the **frozen seam C1/E1
import**. No Django, no I/O, no new dependency, no order path.

    OHLC ─→ find_order_blocks(structure) ─┐
    OHLC ─→ find_fvg ──────────────────────┼─→ find_setups(swings, structure, range_) ─→ list[Setup]
    swings ─→ find_equal_highs_lows ───────┤
    OHLC + swings ─→ find_liquidity_sweeps ┘
    OHLC ─→ dealing_range ─→ classify_price ─┘

Field names/order follow the change specs verbatim (authoritative over explore's
first draft): `OrderBlock(kind,index,top,bottom,anchor)`,
`FVG(kind,index,top,bottom)`, `EqualLevel(kind,index,price,twin)`,
`Sweep(kind,index,level,direction)`, `DealingRange(high,low,equilibrium,index)`,
`Setup(direction,entry,stop,take_profit,rr,score,index)`.

## Architecture Decisions

| Decision | Choice | Alternative | Rationale |
|---|---|---|---|
| Record type | stdlib `NamedTuple`, lowercase `kind` | dataclass/dict | matches B1, immutable, unpackable, zero deps |
| OB anchor | `kind == "bos"` only | BOS + CHoCH | CHoCH is reversal start, not continuation displacement (spec R1) |
| OB candle | most recent `closes[i] < opens[i]` (bear BOS: `>`), window `[max(0,t-lb), t-1]` | body/close-only | needs `opens`; B2 takes OHLC additively, B1 unchanged |
| OB zone | full candle `[low, high]` | body-only | frozen spec R1 |
| FVG gap | `gap >= min_gap`, absolute price units | fraction-of-price | exact fixtures; tuning deferred to E1 |
| FVG lifecycle | raw unfilled gaps | mitigation tracking | mitigation is a C1/render concern |
| EQ pairing | consecutive same-kind swings | any-in-window | deterministic O(n) |
| Sweep | wick beyond level, close back inside | close inside candle body | spec R4 |
| Range source | fixed lookback | structure extremes | simpler, deterministic, no extra seam |
| Confluence | equal weight 0..4, gate `min_confluence` | weighted | spec R2 |
| TP source | `range_.high/low` if `rr >= min_rr`, else fixed-R `MIN_RR_TP_R` | fixed-R only | spec R3 |
| Entry/SL | OB proximal/distal preferred, FVG fallback | OB only | spec R3 + edge matrix |
| Overlap | separate records, never merged | merge | merge is a render concern |

## Interfaces / Contracts (FROZEN for C1/E1)

```python
# src/smc/config.py  (B2 additions)
OB_LOOKBACK = 10; FVG_MIN_GAP = 0.0; EQ_TOLERANCE = 0.0; SWEEP_LOOKBACK = 20
RANGE_LOOKBACK = 50; SL_BUFFER = 0.0; MIN_RR = 2.0; MIN_CONFLUENCE = 3
MIN_RR_TP_R = 3.0            # fixed-R multiple for the TP fallback

# src/smc/zones.py
class OrderBlock(NamedTuple): kind:str; index:int; top:float; bottom:float; anchor:int
class FVG(NamedTuple):        kind:str; index:int; top:float; bottom:float
class EqualLevel(NamedTuple): kind:str; index:int; price:float; twin:int
class Sweep(NamedTuple):      kind:str; index:int; level:float; direction:str
def find_order_blocks(opens,highs,lows,closes,structure,*,lookback=OB_LOOKBACK)->list[OrderBlock]
def find_fvg(highs,lows,*,min_gap=FVG_MIN_GAP)->list[FVG]
def find_equal_highs_lows(swings,*,tolerance=EQ_TOLERANCE)->list[EqualLevel]
def find_liquidity_sweeps(highs,lows,closes,swings,*,lookback=SWEEP_LOOKBACK)->list[Sweep]

# src/smc/range.py
class DealingRange(NamedTuple): high:float; low:float; equilibrium:float; index:int
def dealing_range(highs,lows,*,lookback=RANGE_LOOKBACK)->DealingRange|None
def classify_price(price,range_)->str          # "premium"|"discount"|"equilibrium"

# src/smc/signals.py
class Setup(NamedTuple):
    direction:str; entry:float; stop:float; take_profit:float; rr:float; score:int; index:int
def find_setups(opens,highs,lows,closes,swings,structure,*,range_=None,
                min_rr=MIN_RR,min_confluence=MIN_CONFLUENCE,sl_buffer=SL_BUFFER)->list[Setup]
```

### Detection pseudo-code (exact)

```
find_order_blocks: guard n=len(closes); if n==0 or len(opens|highs|lows)!=n or lookback<0 -> []
  for ev in structure if ev.kind=="bos" and 0<=ev.index<n:
    for i in range(ev.index-1, max(0,ev.index-lookback)-1, -1):   # most recent first
      if ev.direction=="bullish" and closes[i]<opens[i]: pick=i; break
      if ev.direction=="bearish" and closes[i]>opens[i]: pick=i; break
    if pick: emit OrderBlock(ev.direction, pick, top=highs[pick], bottom=lows[pick], anchor=ev.index)
  sort by index                                  # doji close==open is neither -> skipped

find_fvg: guard n<3 or len(lows)!=n -> []
  for i in 1..n-2:
    if highs[i-1] < lows[i+1]:        top,bottom,kind = highs[i-1],lows[i+1],"bullish"
    elif lows[i-1] > highs[i+1]:      top,bottom,kind = lows[i-1],highs[i+1],"bearish"
    else: continue
    if top-bottom >= min_gap: emit FVG(kind,i,top,bottom)   # kinds mutually exclusive; index-ordered

find_equal_highs_lows: for kind in ("high","low"):
    same=[s for s in swings if s.kind==kind]     # B1 contract: ascending index
    for earlier,later in zip(same,same[1:]):
      if abs(earlier.price-later.price)<=tolerance:
        emit EqualLevel("eqh" if kind=="high" else "eql", later.index, later.price, earlier.index)
  sort by index

find_liquidity_sweeps: guard n==0 or len(highs|lows)!=n or lookback<0 -> []
  for t in range(n):
    bl=bh=None
    for s in swings if s.index<=t and t-s.index<=lookback:      # inclusive window
      if s.kind=="low" and lows[t]<s.price and closes[t]>s.price:   bl=s if bl is None or s.index>bl.index
      elif s.kind=="high" and highs[t]>s.price and closes[t]<s.price: bh=... most recent
    if bl: emit Sweep("low", t, bl.price, "bullish")   # at most one per side per bar
    if bh: emit Sweep("high", t, bh.price, "bearish")  # tie same bar: low then high

dealing_range: if len(highs)==0 or len(lows)!=len(highs) or lookback<=0 -> None
  high=max(highs[-lookback:]); low=min(lows[-lookback:]); return DealingRange(high,low,(high+low)/2,len(highs)-1)
classify_price: p>eq -> "premium"; p<eq -> "discount"; else "equilibrium"
```

### `find_setups` (confluence + derivation)

```
guard: len(closes)!=len(opens|highs|lows) or n==0 -> []; if not structure -> []
ev = structure[-1]; direction = "long" if ev.trend=="up" else "short"; anchor = ev.index
obs = find_order_blocks(opens,highs,lows,closes,structure)
fvgs= find_fvg(highs,lows)
want = "bullish" if long else "bearish"
recent(x) = 0 <= anchor - x.index <= OB_LOOKBACK          # recency of the zone candle
ob  = last obs with kind==want and recent(ob)             # latest match, else None
fvg = last fvgs with kind==want and recent(fvg)           # latest match, else None
zone = ob or fvg; if zone is None -> []                   # no entry zone
if long:  entry=zone.top;    stop=zone.bottom - sl_buffer
else:     entry=zone.bottom; stop=zone.top    + sl_buffer
if entry == stop -> []                                    # degenerate, no raise
# score = 1 (structure, tautological: candidate derived from ev)
#   + 1 recent matching OB  + 1 recent matching FVG
#   + 1 if range_ and classify_price(closes[-1], range_) == ("discount" if long else "premium")
if score < min_confluence -> []
tp = fixed-R fallback: entry ± MIN_RR_TP_R*(entry-stop)
if range_ is not None:
  structural = range_.high if long else range_.low
  if rr_of(structural) >= min_rr: tp = structural
rr = (tp-entry)/(entry-stop) if long else (entry-tp)/(stop-entry)
if rr < min_rr -> []
return [Setup(direction,entry,stop,tp,rr,score,anchor)]
```

`Setup` is a **computed proposal — never an order**; `signals.py` imports no
execution/order symbol. `structure_component` is always 1 by construction (the
candidate equals the latest event's direction); flagged below.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/smc/zones.py` | Create | OB/FVG/EQH-EQL/sweeps + records |
| `src/smc/range.py` | Create | `DealingRange`, `dealing_range`, `classify_price` |
| `src/smc/signals.py` | Create | `Setup`, `find_setups` |
| `src/smc/config.py` | Modify | +9 B2 constants |
| `tests/smc_fixtures.py` | Create | shared synthetic OHLC + `mirror_ohlc` |
| `tests/test_smc_zones.py` | Create | bull/bear + edge battery |
| `tests/test_smc_range.py` | Create | range + classification + edges |
| `tests/test_smc_signals.py` | Create | confluence/entry/SL/TP/R:R + edges |
| `tests/test_boundary.py` | Modify | `PURE_MODULES += ("smc/zones.py","smc/range.py","smc/signals.py")` |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit — zones | bull+bear OB/FVG/EQH/EQL/sweep, no-opposite-candle, below-gap, no-pair, stale level, empty/short/mismatched → `[]`, order, no mutation | literal series + hand-traced asserts; `mirror_ohlc` for the bear twin (mirrors B1's `_mirror`) |
| Unit — range | last-N window, truncation, empty/mismatched/`lookback<=0` → `None`, flat market, premium/discount/equilibrium | exact asserts |
| Unit — signals | score 4 / 3 / below-threshold, no-OB-no-FVG, structural TP clears gate, fixed-R fallback, `rr<min_rr`, `entry==stop`, `range_=None`, purity | full-confluence fixture + targeted degradations |
| Boundary | 3 new modules stdlib-only, no Django | extend `PURE_MODULES`; existing negative-control proves the scanner |

No integration/E2E — pure internal logic, no user-visible behavior. `strict_tdd`:
tests (RED) precede implementation; patch 100%.

## Guard / Edge Matrix

| Edge | Handling |
|---|---|
| empty / mismatched OHLC | `[]` (finders) / `None` (range), never raise |
| `lookback < 0` (zones) / `<= 0` (range) | `[]` / `None` |
| no opposite candle in OB window | no `OrderBlock` |
| doji OB candle (`close==open`) | neither bull nor bear → skipped |
| `choch` event | never anchors an OB |
| FVG `gap < min_gap` | no `FVG` |
| FVG with `<3` bars | `[]` |
| EQ unequal / `tolerance=0.0` | no `EqualLevel` |
| sweep wick, no close-back-inside | no `Sweep` |
| swing older than `lookback`, or `index > t` | not sweepable |
| overlapping zones | separate records, never merged |
| `range_ is None` | PD component 0; fixed-R TP fallback |
| `entry == stop` | record skipped |
| `rr < min_rr` | no `Setup` |
| no OB and no FVG | no entry zone → no `Setup` |
| `PURE_MODULES` blind spot | explicit task; negative-control fixture already proves scanner |

## Delivery — Chained 3 slices (Feature Branch Chain)

Base = `feat/smc-zones-signals` tracker; each child PR targets the **immediate
previous slice**. ~950 lines total → `400-line budget risk: High`.

| Slice | Content | ~Lines | Rollback boundary |
|---|---|---|---|
| 1 `zones.py` | OB/FVG/EQ/sweeps + `tests/test_smc_zones.py` + `smc_fixtures.py` + `PURE_MODULES` zones entry | ~410 | delete `zones.py` + tests, revert one `PURE_MODULES` line, drop 5 constants |
| 2 `range.py` | range + premium/discount + `test_smc_range.py` + `PURE_MODULES` range entry | ~190 | delete `range.py` + tests, revert its `PURE_MODULES` line, drop `RANGE_LOOKBACK` |
| 3 `signals.py` | confluence → `Setup` + `test_smc_signals.py` + `PURE_MODULES` signals entry | ~340 | delete `signals.py` + tests, revert its `PURE_MODULES` line, drop `MIN_*`/`SL_BUFFER` |

Each slice: starts at its module, finishes at green `pytest` + ruff + patch 100%,
autonomous (slice 3 is the only one with a dependency, on 1 & 2), trivial rollback
(pure additive module + one registry line + its constants).

## Resolved Decisions

- **Constant count**: RESOLVED — **9** constants (`OB_LOOKBACK` is required by the
  frozen `find_order_blocks` signature, in addition to the 8 originally listed).
  Spec and design both require it.
- **Structure confluence component**: RESOLVED — kept as spec'd (a `Setup` is only
  considered when a directional `StructureEvent` anchors it, so component (1) is
  always satisfied at that point). Intentional for v1; E1 may tighten it.
- **Sweep look-ahead nuance**: RESOLVED — documented known simplification (≤2-bar
  edge effect): sweeps consume confirmed B1 swings without an extra `index+right<=t`
  guard, since the B1 swing list already excludes unconfirmed trailing pivots.
