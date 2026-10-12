# Verify Report — smc-zones-signals (issue #74, Fase B2)

**Verdict**: `pass_with_warnings`
**Verified by**: orchestrator (adversarial, fresh probes). The delegated verify sub-agent timed out without output twice; verification was executed inline.
**Branch**: `feat/smc-zones-signals-signals` (HEAD `439f44e`), chain: tracker `feat/smc-zones-signals` + Slice1 `…-zones` (`cd6da95`) + Slice2 `…-range` (`346fefb`) + Slice3 `…-signals` (`54f01d6`) + fix (`439f44e`); all slice PRs base on the tracker.

## Gates (L1)

| Gate | Result |
| --- | --- |
| `python -m pytest tests/ --ignore=tests/web` | **219 passed** |
| `pytest tests/test_boundary.py tests/web/test_no_order_surface.py tests/test_dependency_guard.py` | green (46) |
| `ruff check .` | clean |
| `ruff format --check .` | clean (119 files) |
| `requirements.txt` vs develop | **empty diff** (no new dependency) |
| `src/smc/*.py` imports | stdlib (`__future__`, `typing.NamedTuple`) + intra-package only — no Django/requests/`src.client`/I/O |

## Gates (L2)

- `diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` → **100%** (193 changed lines, 0 missing: `smc/config.py`, `smc/range.py`, `smc/signals.py`, `smc/zones.py`).

## Spec conformance (L3)

- **`smc-zones`**: `OrderBlock(kind,index,top,bottom,anchor)` anchored on **BOS only** (CHoCH not an anchor — probe-verified); OB candle = last opposite candle in the lookback window; `FVG(kind,index,top,bottom)` 3-candle rule with **`top >= bottom` for both kinds** (see W1); `EqualLevel(kind,index,price,twin)` consecutive same-kind within tolerance; `Sweep(kind,index,level,direction)` wick beyond + close back inside. Empty/short/mismatched → `[]`, never raise.
- **`smc-range`**: `DealingRange(high,low,equilibrium,index)`; `dealing_range` over `RANGE_LOOKBACK`; `classify_price` premium/discount/equilibrium; `None`/`lookback<=0` → `None`.
- **`smc-signals`**: `Setup(direction,entry,stop,take_profit,rr,score,index)`; confluence equal-weight 0..4 gated at `MIN_CONFLUENCE`; entry=OB proximal (FVG fallback); stop=distal∓`SL_BUFFER`; take_profit=range extreme if `rr>=MIN_RR` else `entry ± MIN_RR_TP_R*(entry-stop)`; R:R gate at `MIN_RR`; **Setup is a proposal, never an order** (no order verbs/imports in `src/smc/`).
- **Config**: 9 constants; `PURE_MODULES` gained `smc/zones.py`, `smc/range.py`, `smc/signals.py`.
- **B1 seam FROZEN**: `src/smc/{swings,structure}.py` unchanged.

### Adversarial probes (independent, throwaway)
- **OB path long**: `Setup('long', entry=9.5, stop=8.5, take_profit=12.5, rr=3.0)` → `entry>stop`, `tp>entry`. Coherent.
- **OB path short**: `Setup('short', entry=12, stop=13, take_profit=7.5, rr=4.5)` → `entry<stop`, `tp<entry`. Coherent.
- **FVG fallback (both directions)**: after the fix, bullish FVG has `top=11 > bottom=9` → FVG-only long gives `entry=9 > stop=8.5`, `tp=12 > entry`. Coherent.
- **Gates**: `min_confluence=5` → `[]`; `min_rr=999` → `[]`.
- **Edge**: empty/short/mismatched → `[]`/`None`; determinism + non-mutation confirmed.

## Warnings (non-blocking)

- **W1 — Real bug found and fixed in Slice 1's FVG orientation (root cause was the spec/design)**. Both the spec and design assigned the bullish FVG zone as `top=highs[i-1]`, `bottom=lows[i+1]`, but the bullish condition is `highs[i-1] < lows[i+1]`, so `top < bottom` (inverted). Slice 1 masked it with `abs(top-bottom) >= min_gap`, but in Slice 3 the FVG fallback then produced `entry < stop` for a long — incoherent geometry — and one test **encoded** the bug (`Setup("long", 11.0, 13.0, …)`). Fixed at the root (`src/smc/zones.py`: `top=lows[i+1], bottom=highs[i-1]`), the spec/design prose corrected (`top>=bottom` invariant), the fixture comment and the two affected tests updated. Commit `439f44e`. Verified: both kinds now satisfy `top>=bottom`; both directions produce coherent Setup geometry.
- **W2 — `classify_price(price, None)` → `"equilibrium"`** is undocumented in the spec (spec omits the None case). Neutral degradation; flagged for archive to record.
- **W3 — `RL` confluence structure component is always 1** by construction (the candidate derives from a `StructureEvent`). Intentional for v1; E1 may tighten it.
- **W4 — Sweep look-ahead nuance**: sweeps consume confirmed B1 swings (which already exclude unconfirmed trailing pivots) without an extra `index+right<=t` guard; ≤2-bar edge effect, documented simplification.
- **SUGGESTION**: `tasks.md` checkboxes not marked by apply (orchestrator hard contract); engram `sdd/smc-zones-signals/apply-progress` is the completion source.

## Requirement coverage

- New `smc-zones` (5 reqs), `smc-range` (3 reqs), `smc-signals` (5 reqs): satisfied (with W1–W4 notes).
- `core-domain-boundary` DELTA: 3 new modules registered.

## Blockers

None.
