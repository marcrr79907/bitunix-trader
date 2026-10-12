# Proposal: smc-zones-signals (Fase B2, issue #74)

## Intent

B1 froze swings + BOS/CHoCH. B2 adds the second pure SMC layer — order blocks,
FVG, EQH/EQL, sweeps, dealing range, confluence→`Setup` — consuming the frozen
B1 seam read-only. Unblocks C1 (render) and E1 (calibration) and is the named
next phase after A-series + B1. No user-visible behavior; pure internal logic.

## Scope

### In Scope
- `src/smc/zones.py`: `OrderBlock`, `FVG`, `EqualLevel`, `Sweep` + finders.
- `src/smc/range.py`: `DealingRange`, `dealing_range`, `classify_price`.
- `src/smc/signals.py`: `Setup` (entry/SL/TP/R:R), `find_setups`.
- `src/smc/config.py`: 8 B2 constants; tests per module; `PURE_MODULES` += 3.

### Out of Scope
- Render (C1), alerts (D), calibration (E1), order execution (HARD fence); FVG
  mitigation/fill tracking; zone merging; Django/endpoint/migration; new deps.

## Capabilities

### New Capabilities
- `smc-zones-signals`: pure SMC zones, dealing range, confluence-gated `Setup`.

### Modified Capabilities
- `core-domain-boundary`: `PURE_MODULES` gains the 3 new module paths.

## Approach

Clone B1: stdlib `NamedTuple` (lowercase `kind`), lists in / sparse out, never
raise (→ `[]`), pure, stdlib-only, tunables in `config.py`. v1 rules (14 explore
questions locked):

| Rule | v1 decision |
|------|-------------|
| Input | finders take `opens` where needed (additive; B1 unchanged) |
| OB | BOS anchor only; last opposite candle before displacement; zone = its `[low, high]`; direction from BOS |
| FVG | `highs[i-1] < lows[i+1]` bullish (mirror bearish); raw unfilled gaps, gap `>= min_gap` |
| EQH/EQL | consecutive same-kind swings within `eq_tolerance` |
| Sweep | wick beyond a prior swing extreme, close back inside the level |
| Range | fixed `range_lookback`; equilibrium = 50%; premium/discount split |
| Confluence | equal-weight 0..4 (structure+OB+FVG+PD), gate `min_confluence` |
| Entry/SL/TP | entry = OB proximal; SL = distal − `sl_buffer`; TP = range extreme else fixed-R; R:R gate `min_rr` |

`Setup` is a proposal, never an order.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/smc/{zones,range,signals}.py` | New | pure SMC detection + signals |
| `src/smc/config.py` | Modified | +8 B2 constants |
| `tests/test_smc_{zones,range,signals}.py` | New | bull/bear + edge battery |
| `tests/test_boundary.py` | Modified | `PURE_MODULES` += 3 paths |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| SMC school ambiguity | High | freeze rules as spec pseudo-code; bull+bear fixtures |
| Fixture cross-triggering | Med | hand-traced synthetic OHLC |
| Downstream coupling (C1/E1) | Med | freeze `NamedTuple` shapes now |
| Branch patch coverage | Med | mirror B1 edge battery |

## Rollback Plan

Pure additive: delete the 3 modules + tests, revert `config.py` constants and
`PURE_MODULES`. No data, migration, or external state — inert until C1/E1 import.

## Read-Only Boundary

`src/smc/` computes over supplied OHLC lists only. MUST NOT place/modify/cancel
orders, import Django/`requests`/`src.client`, do I/O, or expose any execution
path. `requirements.txt` unchanged; order scanner stays clean.

## Dependencies

- B1 seam frozen — B2 consumes it, never changes it. C1/E1 consume B2 shapes.

## Delivery (Chained PRs — Feature Branch Chain)

`400-line budget risk: High` (~950 lines). Base = `feat/smc-zones-signals`
tracker; child PRs target the immediate previous slice.

1. **Slice 1 — `zones.py`** (~410): OB/FVG/EQ/sweeps + boundary + tests.
2. **Slice 2 — `range.py`** (~190): dealing range + premium/discount + tests.
3. **Slice 3 — `signals.py`** (~340): confluence → `Setup` + final wiring.

- Decision needed before apply: Yes · Chained PRs recommended: Yes · budget risk: High

## Success Criteria

- [ ] Each finder matches hand-traced bull AND bear fixtures.
- [ ] Pure: same input → same output; inputs not mutated; empty/short → `[]`.
- [ ] `find_setups` emits only when `score >= min_confluence` and `rr >= min_rr`;
      guards `entry == stop`.
- [ ] No new dependency; `src/` framework-free; `pytest` green; patch 100%; ruff.
