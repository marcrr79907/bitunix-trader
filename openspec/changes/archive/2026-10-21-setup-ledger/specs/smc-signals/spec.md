# Delta for smc-signals

## ADDED Requirements

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

`src/smc/` MUST expose an additive pure helper that returns, for the same inputs
and call chain as `get_smc_payload`, the enrichment the frozen `Setup` does not
carry: the anchor bar `index`, its `anchor_time` resolved from a caller-supplied
`times` list, and the ATR at that index.

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
