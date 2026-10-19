# Delta for alert-rules

Issue #124 (F11): `_pair_error` currently rejects every symbol outside `SYMBOLS`
(`web/market/alerts.py:47`), which blocks alerts for the exchange-wide catalog. This
ADDS R12 (catalog-based symbol validation) and leaves R1–R11 in force — the model,
engine, dedup, sink and transport are unchanged. **R12 supersedes only R10's
`symbol ∈ SYMBOLS` membership clause**; R10's remaining contract, including the
`interval ∈ CANDLE_INTERVALS` bound, is unchanged.

## ADDED Requirements

### Requirement: R12 — Catalog-based symbol validation

`alerts._pair_error` MUST validate the symbol against the symbol catalog
(`symbol-catalog`) instead of `SYMBOLS` membership. When the catalog is warm and the
symbol is absent → 400 `invalid symbol`. When the catalog is cold or unavailable, it
MUST fail open for any symbol matching `^[A-Z0-9]{2,24}$` and MUST store the rule.
Rationale (normative, to prevent a future "fix"): the rule is per-user owned, never
shared, never executed as an order, and the worker already skips unknown intervals
(`worker.py:167-168`); the alternative is a network call on every request. A malformed
symbol MUST be 400 in every state. The interval rule MUST be unchanged: only
`CANDLE_INTERVALS` are evaluable, and the check order stays symbol → interval.

#### Scenario: Warm catalog accepts a listed symbol

- GIVEN a warm catalog containing `DOGEUSDT`
- WHEN A POSTs a rule on `DOGEUSDT` with `1h`
- THEN 201 is returned and the rule is stored

#### Scenario: Warm catalog rejects an unknown symbol

- GIVEN a warm catalog without `FAKEUSDT`
- WHEN A POSTs a rule on `FAKEUSDT`
- THEN 400 `invalid symbol` is returned and nothing is written

#### Scenario: Cold catalog fails open

- GIVEN a cold/unavailable catalog
- WHEN A POSTs a rule on `ARBUSDT`
- THEN 201 is returned and the rule is stored

#### Scenario: Cold catalog still rejects malformed symbols

- GIVEN a cold/unavailable catalog
- WHEN A POSTs a rule on `abc/usdt` or `A`
- THEN 400 is returned and nothing is written

#### Scenario: Interval rule is unchanged

- GIVEN a warm catalog containing `BTCUSDT`
- WHEN A POSTs a rule with `interval="1m"`
- THEN 400 is returned for the invalid interval (`alert-rules` R10 unchanged)

#### Scenario: A catalog symbol outside `BITUNIX_SYMBOLS` can be stored

- GIVEN `config.SYMBOLS` does not include `DOGEUSDT` and the catalog does
- WHEN A POSTs a rule on `DOGEUSDT`
- THEN 201 is returned and the rule persists (previously rejected by `SYMBOLS` membership)
