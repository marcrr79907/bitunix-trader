# Proposal: smc-structure

## Intent

The chart shows price, not structure. Fase B1 adds a pure SMC core — swing pivots,
trend labels, BOS/CHoCH — as the second `src/` pure-module family (after
`indicators.py`). It unblocks B2 (order blocks/FVG) and C1 (render). Issue #73.
Why now: A-series done; SMC is the named next phase and B2/C1 wait on this shape.
No user-visible behavior — pure internal logic.

## Scope

### In Scope
- `src/smc/swings.py`: `find_swings(highs, lows, *, left=2, right=2)` — strict
  fractal pivots over OHLC.
- `src/smc/structure.py`: `label_swings` (HH/HL/LH/LL), `find_structure`
  (BOS/CHoCH), `trend_state` (index-aligned `up|down|range|None`).
- `src/smc/config.py`: constants `SWING_LEFT=2`, `SWING_RIGHT=2`, `USE_CLOSE=True`
  imported as function defaults. No class.
- `src/smc/__init__.py` empty package marker.
- Tests: `tests/test_smc_swings.py`, `tests/test_smc_structure.py`, extend
  `PURE_MODULES` in `tests/test_boundary.py`.

### Out of Scope
- Order blocks/FVG/liquidity (B2/C); any render, Django, endpoint, migration.
- Order execution (HARD fence); no new dependency; no CSP change.

## Capabilities

### New Capabilities
- `smc-structure`: pure SMC primitives — swings, trend labels, BOS/CHoCH.

### Modified Capabilities
- `core-domain-boundary`: `PURE_MODULES` gains the three stdlib-only paths.

## Approach

Clone `indicators.py`: framework-free, stdlib-only, pure, list in / sparse list
out, never raise (empty/short/mismatched → `[]`). Output shape frozen as stdlib
`NamedTuple` — `Swing`, `LabeledSwing`, `StructureEvent` — no new dep.

**Locked** (resolve explore's open questions):
- **Pivot**: strict `>`/`<`; equal highs/lows are NOT pivots. Needs `left` bars
  before, `right` after; trailing `right` bars UNCONFIRMED → never emitted.
- **Trend**: `up|down|range` from labels (HH+HL → up, LH+LL → down, else range).
- **BOS**: close beyond the prior relevant swing in trend direction. **CHoCH**:
  first close against the established trend. `USE_CLOSE` toggles close vs wick.
- **Relevant swing**: most recent confirmed extreme in trend direction; level
  updates after each event.
- **Seeding**: no trend → first break seeds silently; CHoCH needs a trend;
  labels inform, don't gate; need ≥1 high AND ≥1 low.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/smc/{__init__,config,swings,structure}.py` | New | pure core, ~130 lines |
| `tests/test_smc_{swings,structure}.py` | New | bull/bear + edge battery |
| `tests/test_boundary.py` | Modified | `PURE_MODULES` += 3 paths |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| SMC ambiguity (BOS vs CHoCH, relevant swing) | Med | freeze state machine; bull/bear fixtures |
| Shape coupling (B2/C1) | Med | freeze now; minimal immutable `NamedTuple` |
| Trailing pivot look-ahead | Med | dedicated edge test |
| Branch patch coverage | Med | mirror `test_indicators.py` battery |

## Rollback Plan

Pure additive module: delete `src/smc/`, new tests, revert `PURE_MODULES`. No
data, migration, config, or external state — inert until B2/C1 import it.

## Read-Only Boundary

`src/smc/` is read-only computation over supplied OHLC lists. It MUST NOT place,
modify, or cancel orders, import Django/`requests`/`src.client`, do I/O or
network, or expose any execution path. `src/` stays framework-free;
`requirements.txt` unchanged; order scanner stays clean.

## Dependencies

- None at runtime (stdlib only). B2 and C1 consume this shape — the freeze is
  their interface.

## Delivery (Single PR)

Internal pure logic, no user-visible behavior, no Django/migration — chaining is
unwarranted. Swings and structure are one cohesive algorithm (BOS is defined over
swings). ~400 lines, tests-dominated.

- Decision needed before apply: No
- Chained PRs recommended: No
- 400-line budget risk: Medium

## Success Criteria

- [ ] `find_swings` emits strict pivots; trailing `right` bars never emitted.
- [ ] `find_structure` correct BOS/CHoCH on bull and bear fixtures.
- [ ] Pure: same input → same output; inputs not mutated; empty/short → `[]`.
- [ ] No new dependency; `src/` framework-free; boundary test green.
- [ ] `pytest` green; patch gate 100%; ruff clean.
