# Exploration: smc-structure (issue #73, Fase B1)

## Current State

### The pure-core model to mirror

`src/indicators.py` is the reference implementation of the pure core:

- Module docstring states the contract ("Lists in, lists/numbers out. No I/O,
  no network, stdlib only. Output length always equals input length; positions
  that cannot be computed are `None` (leading warm-up).").
- `from __future__ import annotations` at the top of every module.
- Pure module-level functions only — **zero classes anywhere in `src/`**
  (`grep dataclass|NamedTuple|TypedDict` over the repo returns nothing).
- Type hints are `list[float]` in, `list[float | None]` out; multi-output
  functions return a `tuple[list, ...]` (`macd`, `bollinger`, `stochastic`).
- Private helpers are `_`-prefixed (`_rsi_from`, `_macd_line`).
- Warm-up is leading `None` padding; the output length ALWAYS equals the input
  length; defensible guards return `None`, never raise (`window < 1`, empty
  input, divide-by-zero).
- Parameters that vary are function keyword args with literal defaults
  (`macd(series, fast=12, slow=26, signal=9)`), NOT module constants.

`src/metrics.py` confirms the scalar convention: `None` for undefined, same
length/`[]` for list outputs, no classes.

### Config convention (important divergence)

`src/config.py` is an **env/secrets loader**, not a domain-tunable module: it
holds plain module-level constants (`FUNDING_EXTREME`, `POLL_SECONDS`) and one
`load_env()` helper. There is **no existing precedent for a domain-tunable
config module**. Indicator tunables live as function-argument defaults, not
constants. `src/smc/config.py` is therefore a NEW pattern; the laziest
consistent choice is module-level constants that the functions import as their
default-argument values (one source of truth, no class).

### Test convention

`tests/test_indicators.py` (445 lines):

- One file per module: `tests/test_<module>.py`.
- Synthetic literal series, exact-value asserts, `from pytest import approx`
  for floats.
- Grouped by function with `# --- name ---` section banners.
- Each function gets the same edge battery: known values, triangulation
  (second input exercising the general branch), empty input, invalid param
  (`window < 1`), length preserved, **does not mutate input**.
- Markers: `pyproject.toml` `addopts = "-q -m 'not e2e'"`; only `e2e` is a
  registered marker. Unit tests carry no marker.
- Patch gate: `diff-cover --fail-under=100` on changed lines (spec
  `patch-coverage-gate` R1) → **every changed line needs a covering test**.

### Boundary enforcement (must stay green)

`tests/test_boundary.py` is stdlib-only (parses with `ast`, never imports
Django):

- `_django_offenders(SRC)` walks `src/**/*.py` via `rglob` → **any** new file
  under `src/smc/` is auto-scanned for `django` imports.
- `PURE_MODULES = ("indicators.py", "metrics.py")` is a tuple of names joined
  to `SRC`. `test_pure_modules_are_stdlib_only` checks each existing entry's
  imports against `sys.stdlib_module_names`. **New modules MUST be added here**
  as `"smc/swings.py"`, `"smc/structure.py"`, `"smc/config.py"` — otherwise
  they are never checked for non-stdlib imports (the Django check still covers
  them, but the stdlib-only check would be blind). The comment on L17 already
  says "Extend this set as new pure domain modules are added."
- `tests/test_dependency_guard.py` independently scans `src/**/*.py` against
  `stdlib + declared-deps + local-roots`; `src` is a local root, so
  `from src.smc.config import ...` and `from src.indicators import ...` are
  allowed. A third-party import fails this guard.
- `src/smc/` MUST be a package (empty `__init__.py`, mirroring `src/__init__.py`)
  for `from src.smc.swings import find_swings` to resolve.

### Existing SMC references

None. `grep` for `smc|BOS|CHoCH|swing` finds only fences saying SMC is out of
scope for A1/A2/A3. B1 is genuinely new — no prior spec or code.

## Affected Areas

- `src/smc/__init__.py` — NEW empty package marker.
- `src/smc/config.py` — NEW tunables (swing strength, close-vs-wick).
- `src/smc/swings.py` — NEW fractal pivots over OHLC.
- `src/smc/structure.py` — NEW HH/HL/LH/LL, trend, BOS, CHoCH.
- `tests/test_smc_swings.py` — NEW deterministic fixture tests.
- `tests/test_smc_structure.py` — NEW BOS/CHoCH bull/bear fixture tests.
- `tests/test_boundary.py` — extend `PURE_MODULES` with the three new paths.
- `openspec/specs/` — a new `smc-structure` domain spec at archive time
  (mirrors `technical-indicators`).

No web/, no Django model, no migration, no endpoint — pure logic only.

## Domain design (SMC primitives)

### `src/smc/swings.py`

```python
def find_swings(
    highs: list[float],
    lows: list[float],
    *,
    left: int = SWING_LEFT,   # default 2
    right: int = SWING_RIGHT, # default 2
) -> list[Swing]:
    """Confirmed fractal pivots, ordered by index.

    Bar i is a pivot HIGH iff highs[i] is strictly greater than the `left`
    highs before it and the `right` highs after it (mirror for LOWS). Only
    pivots with `right` bars of confirming data are emitted, so the trailing
    `right` bars can never produce a pivot (the unconfirmed edge case).
    """
```

Data shape (recommended: stdlib `NamedTuple` — immutable, tuple-unpackable,
attribute-readable, hashable, zero deps, and the first structural type in the
repo). Alternative shapes are an open decision (below):

```python
class Swing(NamedTuple):
    index: int
    price: float
    kind: str  # "high" | "low"
```

Rules to lock:

- **Strict comparison** (`>` / `<`). Equal/plateau highs are NOT pivots — this
  kills the double-pivot ambiguity. (Open decision.)
- Only confirmed pivots are returned. An unconfirmed trailing pivot is simply
  absent, exactly like indicator warm-up: confirmation needs `right` future
  bars, which is the same "data not yet available → not emitted" rule.
- `len(highs) == len(lows)`; mismatched/empty input → `[]` (never raise).
- Output is time-ordered by `index`; a single bar can be neither both a high
  and a low in practice (high ≥ low), but the function does not assume it.

### `src/smc/structure.py`

```python
class LabeledSwing(NamedTuple):
    index: int
    price: float
    kind: str   # "high" | "low"
    label: str  # "HH" | "HL" | "LH" | "LL"

class StructureEvent(NamedTuple):
    index: int
    price: float
    kind: str       # "BOS" | "CHoCH"
    direction: str  # "bullish" | "bearish"

def label_swings(swings: list[Swing]) -> list[LabeledSwing]:
    """HH/HL/LH/LL from consecutive same-kind swings.

    A swing high is HH if its price > the previous swing high, else LH; a swing
    low is HL if > the previous swing low, else LL. The first swing of each kind
    is unlabeled (no predecessor) and is emitted with label "" or omitted — to
    be locked by the spec.
    """

def find_structure(
    swings: list[Swing],
    *,
    use_close: bool = USE_CLOSE,
    closes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[StructureEvent]:
    """BOS/CHoCH events, ordered by index, from confirmed swings.

    Formal rule (issue): the reference break uses the bar's CLOSE (or the wick
    when use_close is False) crossing the prior RELEVANT swing level.

    State machine over swings in index order:
      - Maintain `trend` in {"none","up","down"} and the active high/low.
      - In an UP trend, a close ABOVE the active swing high  -> BOS bullish
        (continuation); it becomes the new active high.
      - In an UP trend, a close BELOW the active swing low   -> CHoCH bearish
        (first break against trend) and trend flips to down.
      - Mirror for DOWN. With no established trend, the first decisive break
        sets the initial trend without emitting a CHoCH.
    """

def trend_state(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    ... config ...,
) -> list[str | None]:
    """Optional index-aligned per-bar trend: "up"|"down"|"range"|None warm-up.

    Mirrors the indicators' same-length/None-padding contract so C1 render can
    color bars without offset bookkeeping.
    """
```

### `src/smc/config.py`

Recommended (mirrors `src/config.py` — plain constants, no class):

```python
SWING_LEFT = 2
SWING_RIGHT = 2
USE_CLOSE = True   # close-vs-wick break mode
```

Functions import these as their default-argument values (single source of
truth). A dataclass is rejected: 3 scalar values do not need a class and `src/`
has none.

### Determinism

- No `datetime`, no `random`, no I/O, no global mutable state.
- List in / list out; sparse event lists carry their own `index`.
- Same input + same params → byte-identical output.
- Never raises on empty/short/mismatched input → returns `[]` (or `[]`/`None`
  for the aligned series), matching indicator edge handling.

## Open Questions / Decisions the spec MUST lock

1. **Output shape** — `NamedTuple` (recommended: stdlib, named, tuple-compatible,
   first structural type in `src/`) vs `dict` vs bare `tuple`. Downstream B2/C1
   consume this, so it must freeze here.
2. **Pivot equality** — strict `>`/`<` (recommended, kills plateau/double-pivot)
   vs `>=`/`<=`.
3. **"Relevant swing" for BOS** — is it the most recent confirmed swing high
   (uptrend) / low (downtrend), and does the level UPDATE to the new swing after
   each BOS? Recommended: yes — the active level moves to the breaking swing's
   successor. This is the single most ambiguous SMC point; the spec must write
   the exact algorithm, not a prose gloss.
4. **BOS vs CHoCH ordering** — CHoCH = FIRST break against the prevailing trend;
   BOS = break in the trend direction. With no established trend, does the first
   break emit a BOS or seed the trend silently? Recommended: seed trend, no
   event (else every start is a spurious signal).
5. **HH/HL ↔ CHoCH interaction** — does a CHoCH require prior HH/HL labels, or
   only the break? Recommended: break-rule driven; labels are informative, not
   gating. Must be stated so B2 can rely on it.
6. **Range vs trend** — definition of "range": no active swing broken and last
   high/low not both HH/HL (or LH/LL). Recommended: trend is event-driven
   (`none` until first BOS/seed, then up/down); "range" is a render-only label.
7. **Minimum swings before signals** — how many confirmed swings are needed
   before a BOS/CHoCH may fire. Recommended: at least one confirmed high AND one
   confirmed low (so both levels exist).
8. **close-vs-wick default** — recommended `USE_CLOSE = True` for both BOS and
   CHoCH (issue's "cierre rompe el swing previo").
9. **Symmetric vs independent left/right strength** — the issue says "fuerza
   izquierda/derecha configurable" → independent `left`/`right`, both default 2.
10. **Unconfirmed trailing pivot** — confirm the rule: never emitted; the last
    `right` bars are structurally bare. No `confirmed` flag in the output.
11. **Trend-state output** — per-bar aligned series vs event-derived only.
    Recommended: provide the aligned series (C1-friendly) AND events.
12. **Label of the first swing of each kind** — omitted vs `""` vs a neutral
    label. Recommended: emitted only from the second same-kind swing onward.

## Risks

- **SMC definition ambiguity across schools** — LuxAlgo/TradingView/ICT differ on
  BOS-vs-CHoCH ordering and "relevant swing". Mitigation: freeze the exact state
  machine (Q3–Q5) in the spec; test both bull and bear fixtures.
- **Downstream coupling (B2 zones, C1 render)** — the output shape is a public
  seam; changing it later ripples. Mitigation: decide the shape now (Q1), keep it
  minimal and immutable.
- **Unconfirmed-trailing-pivot temptation** — a naive implementation emits the
  last pivot using only left-side data, which is a look-ahead-free but WRONG
  pivot. Mitigation: dedicated edge-case test (series ending exactly at a local
  extreme).
- **Equal highs / gaps / single swing** — plateaus create double pivots; a gap
  (high[i] < low[i-1]) can confuse wick-mode breaks. Mitigation: strict equality
  rule + explicit fixtures.
- **100% patch coverage** — every branch (empty, short, `left/right=0`, wick vs
  close, range vs trend, first-swing unlabeled) needs a test line. Mitigation:
  mirror the `test_indicators.py` edge battery per function; no untested guard.
- **Boundary-test blind spot** — forgetting `PURE_MODULES` entries silently
  un-checks non-stdlib imports. Mitigation: explicit task + the existing
  negative-control fixtures already prove the scanner works.
- **Scope creep into B2/C1** — no zones, no signals, no rendering. Fence in the
  proposal.

## Proposed scope boundary + rough size (SINGLE PR)

B1 is pure internal logic with **no user-visible behavior, no Django surface, no
migration** — the exact profile where chaining is NOT warranted. A 2–3 PR chain
here would create artificial slices of one cohesive algorithm (swings and
structure are meaningless apart: BOS/CHoCH is defined over swings). Ship as
**one PR**.

- `src/smc/{__init__.py,config.py,swings.py,structure.py}` — ~130 lines.
- `tests/test_smc_swings.py` — ~120 lines.
- `tests/test_smc_structure.py` — ~150 lines (bull + bear + edge battery).
- `tests/test_boundary.py` `PURE_MODULES` — +3 lines.

Total ≈ 400 lines. **400-line budget risk: Medium** (dominated by tests).
Recommended: single PR; keep test fixtures tight and factor a small helper for
building OHLC series. If tests alone push past ~300 lines, split into a
tests-only follow-up PR rather than chaining the implementation.

## Affected Areas (summary)

- NEW: `src/smc/__init__.py`, `src/smc/config.py`, `src/smc/swings.py`,
  `src/smc/structure.py`.
- NEW: `tests/test_smc_swings.py`, `tests/test_smc_structure.py`.
- EDIT: `tests/test_boundary.py` (`PURE_MODULES` += `"smc/config.py"`,
  `"smc/swings.py"`, `"smc/structure.py"`).
- ARCHIVE-TIME: new `openspec/specs/smc-structure/spec.md`.

## Recommendation

Build `src/smc/` as the second pure-core module family, cloning the
`src/indicators.py` conventions exactly: framework-free, stdlib-only, pure
functions, sparse event lists (with `index`), `NamedTuple` records, tunables as
constants in `src/smc/config.py` imported as function defaults. Implement a
strict-comparison fractal pivot finder (`find_swings`) and an event-driven
structure state machine (`find_structure`) whose BOS/CHoCH rule is "close (or
wick) breaks the prior relevant swing", with a C1-friendly aligned
`trend_state`. Deliver as a SINGLE PR (~400 lines) with deterministic synthetic
fixtures for bull and bear BOS/CHoCH plus the unconfirmed-trailing pivot edge.
Add the new modules to the boundary allowlist.

## Ready for Proposal

YES — the architecture is a direct clone of the proven `src/indicators.py`
pattern; there is no dependency, no Django, no migration. The spec MUST lock:
**output shape** (Q1), **strict equality** (Q2), the **"relevant swing" +
level-update rule** (Q3), **BOS/CHoCH ordering and trend seeding** (Q4), and the
**close-vs-wick default** (Q8).
