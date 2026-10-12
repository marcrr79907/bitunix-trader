# Design: smc-structure (issue #73, Fase B1)

## Technical Approach

A new pure package `src/smc/` cloning the `indicators.py` contract: stdlib only,
list-in / sparse-list-out, never raise, inputs not mutated. Two pure modules:
`swings.py` (strict fractal pivots) and `structure.py` (labels, trend, BOS/CHoCH
state machine). Tunables are plain constants in `smc/config.py` imported as
function defaults (mirrors `src/config.py` — no class). Outputs are the frozen
seam B2/C1 consume. No Django, no I/O, no new dependency.

    OHLC lists ──→ find_swings ──→ list[Swing] ──→ label_swings ──→ trend_state
                                      │
                                      └──→ find_structure(highs,lows,closes) ──→ list[StructureEvent]

## Architecture Decisions

| Decision | Choice | Alternative rejected | Rationale |
|---|---|---|---|
| Record type | stdlib `NamedTuple`, fields `(kind,index,price[,label\|direction,trend])` | dataclass / dict / bare tuple | zero deps, immutable, tuple-unpackable, hashable. `src/` has no classes; the first structural type stays stdlib. |
| Pivot equality | strict `>` / `<` | `>=` / `<=` | plateaus create double pivots; strict is deterministic. |
| Trailing pivot | never emitted (`range(left, n-right)`) | emit with flag | matches indicator warm-up: data not yet available → absent; no look-ahead. |
| `kind` literals | `"high"/"low"`, `"bos"/"choch"` (lowercase) | spec's `"BOS"/"CHoCH"` | brief freezes lowercase; reconciliation flagged in Open Questions. |
| Break reference | `closes` by default (`use_close=USE_CLOSE=True`) | wick-only | issue: "cierre rompe el swing previo". |
| Struct signature | `find_structure(highs, lows, closes, *, left, right, use_close)` | brief's `(highs, lows, *, …)` | spec R5 (close-vs-wick) is unsatisfiable without `closes`; matches `atr(highs, lows, closes, window)` positional convention. |
| Trend state input | `trend_state(labeled)` | `trend_state(highs, lows, closes, …)` | brief freezes labeled input; keeps the function a pure fold over labels. Flagged in Open Questions. |

## Interfaces / Contracts

```python
# src/smc/config.py
SWING_LEFT = 2
SWING_RIGHT = 2
USE_CLOSE = True

# src/smc/swings.py
class Swing(NamedTuple):
    kind: str   # "high" | "low"
    index: int
    price: float

def find_swings(highs, lows, left=SWING_LEFT, right=SWING_RIGHT) -> list[Swing]: ...

# src/smc/structure.py
class LabeledSwing(NamedTuple):
    kind: str; index: int; price: float; label: str   # "HH"|"HL"|"LH"|"LL"

class StructureEvent(NamedTuple):
    kind: str       # "bos" | "choch"
    index: int
    price: float    # breaking reference value at that bar
    direction: str  # "bullish" | "bearish"
    trend: str      # trend AFTER the event: "up" | "down"

def label_swings(swings) -> list[LabeledSwing]: ...
def trend_state(labeled) -> list[str | None]: ...
def find_structure(highs, lows, closes, *, left=SWING_LEFT,
                   right=SWING_RIGHT, use_close=USE_CLOSE) -> list[StructureEvent]: ...
```

### `find_swings` scan (exact)

```
n = len(highs)
if n == 0 or len(lows) != n or left < 0 or right < 0: return []
for i in range(left, n - right):            # last `right` bars unconfirmed
    hi = highs[i]
    if all(hi > highs[i-k] for k in 1..left) and all(hi > highs[i+k] for k in 1..right):
        emit Swing("high", i, hi)
    lo = lows[i]
    if all(lo < lows[i-k] for k in 1..left) and all(lo < lows[i+k] for k in 1..right):
        emit Swing("low", i, lo)
sort by (index, 0 if high else 1)           # deterministic tie order
```
`k` ranges exclude `0`; `left=0`/`right=0` ⇒ empty `all` ⇒ immediate-neighbour pivots.

### `label_swings` / `trend_state`

```
label_swings: fold per kind; first of each kind omitted.
  high: prev_high exists and price > prev_high → "HH" else "LH"
  low:  prev_low  exists and price > prev_low  → "HL" else "LL"
trend_state(labeled) -> same length; None until both a high-label and a low-label exist:
  latest high=="HH" and latest low=="HL" → "up"
  latest high=="LH" and latest low=="LL" → "down"
  else → "range"
```

### `find_structure` state machine (frozen)

`swings = find_swings(...)`; if no confirmed high OR no confirmed low → `[]` (R8).
Iterate bars `t = 0..n-1`; a swing at `j` becomes usable when `j + right <= t`.

```
trend ∈ {"none","up","down"}; active_high/active_low + armed_high/armed_low flags
for t:
  # 1) confirm: roll active_high to the LATEST confirmed high (armed=True); mirror low
  # 2) refs: up_ref = closes[t] if use_close else highs[t]  (down_ref mirror)
  #    break_up = active_high and armed_high and up_ref > active_high
  #    break_dn = active_low  and armed_low  and down_ref < active_low
  # 3) transition (break_up wins ties)
  #    none : break_up → trend="up",  armed_high=False   (SEED, no event)
  #           break_dn → trend="down", armed_low=False
  #    up   : break_up → emit "bos"/bullish/trend "up", armed_high=False
  #           break_dn → emit "choch"/bearish, trend="down", armed_low=False
  #    down : break_dn → emit "bos"/bearish/trend "down", armed_low=False
  #           break_up → emit "choch"/bullish, trend="up", armed_high=False
```

R7: setting `armed_*=False` after a break consumes the level — the same break
cannot re-fire. The level re-arms only when a **new** swing of that kind
confirms, which advances `active_*`. `choch` requires an established trend
(`none` only seeds). Labels do not gate events.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit — swings | known pivots, strict tie exclusion, `left/right=0`, unconfirmed trailing pivot, short/empty/mismatched → `[]`, order, no mutation | `tests/test_smc_swings.py`, literal series + exact asserts |
| Unit — structure | bull BOS chain, bear BOS, bearish/bullish CHoCH, quiet seed, close-vs-wick, label/trend folds, first-of-kind omitted, no-look-ahead, purity (run twice, inputs unchanged) | `tests/test_smc_structure.py` + shared tiny OHLC fixture helper |
| Boundary | `src/smc/{config,swings,structure}.py` stdlib-only, no Django | extend `PURE_MODULES` |

No integration/E2E layer — pure internal logic, no user-visible behavior.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/smc/__init__.py` | Create | empty package marker |
| `src/smc/config.py` | Create | `SWING_LEFT/SWING_RIGHT/USE_CLOSE` |
| `src/smc/swings.py` | Create | `Swing`, `find_swings` |
| `src/smc/structure.py` | Create | `LabeledSwing`, `StructureEvent`, `label_swings`, `trend_state`, `find_structure` |
| `tests/test_smc_swings.py` | Create | pivot + edge battery |
| `tests/test_smc_structure.py` | Create | BOS/CHoCH bull+bear + edge battery |
| `tests/test_boundary.py` | Modify | `PURE_MODULES += ("smc/config.py","smc/swings.py","smc/structure.py")` |

## Guard / Edge Matrix

| Edge | Handling |
|---|---|
| empty / mismatched length | `[]`, never raise (R11) |
| `left<0` / `right<0` | `[]` (frozen) |
| `left=0` / `right=0` | valid immediate-neighbour pivots |
| equal/plateau highs | strict `>` ⇒ no pivot |
| series ends at local extreme | trailing pivot absent (`n - right` bound) |
| one high and one low tie same index | sort by `(index, high-first)` |
| `<1` confirmed high or low | `find_structure` → `[]` |
| first break, no trend | seeds silently, no event |
| close inside / wick beyond level | no BOS unless `use_close=False` |
| repeated close beyond a broken level | `armed=False` consumes it; no re-fire |
| 100% patch coverage | every branch has a test line (fixtures + edge battery) |
| `PURE_MODULES` blind spot | explicit task; negative-control fixtures already prove the scanner |

## Migration / Rollout

No migration. Pure additive module — inert until B2/C1 import it. **SINGLE PR**
(pure internal logic, no user-visible behavior; swings and structure are one
cohesive algorithm). Rollback = delete `src/smc/` + new tests, revert
`PURE_MODULES`. `requirements.txt`, CSP, `src/` boundary unchanged.

**Estimated lines**: `src/smc` ≈ 130; tests ≈ 250; boundary +3 → **≈ 385
(Medium 400-line risk, tests-dominated)**.

- Decision needed before apply: No
- Chained PRs recommended: No
- 400-line budget risk: Medium

## Resolved Decisions

- **Spec casing/fields**: RESOLVED — the change spec `specs/smc-structure/spec.md`
  was reconciled to the brief: `kind` lowercase (`"high"/"low"`, `"bos"/"choch"`)
  and field order `(kind,index,price[,label|direction,trend])`. Verified consistent.
- **`find_structure` signature**: RESOLVED — `find_structure(highs, lows, closes, *,
  left, right, use_close)` (positional `closes`, matching the `atr(highs,lows,closes,…)`
  convention). `closes` is required by R5 close-vs-wick.
- **`trend_state` input**: RESOLVED — `trend_state(labeled)` (pure fold over labels),
  output swing-aligned via `LabeledSwing.index`. C1 maps positions through `index`.
