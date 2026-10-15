# Delta for alert-rules

Issue #147 (DEBT-6, W1) — **clarifying delta only**: reconciles the canonical spec
with the code, which already REQUIRES an explicit `direction` and already has a test
for it. The stale prose lives only in the frozen archived `design.md`, which is not
touched (audit trail). No code change.

## MODIFIED Requirements

### Requirement: R2 — Frozen `condition` schema

`condition` MUST be one JSON object with a discriminating `type`; exactly the
three schemas below are valid. Unknown `type`, unknown `op`, or a scalar-only
violation MUST evaluate to `False` (never raise). The schema MUST NOT change
without a new capability delta.

**`direction` is REQUIRED (clarifying note; W1).** For `smc_setup`, `direction`
MUST be present in the stored condition — there is no default. A missing or
unknown `direction` is a **configuration breach** and MUST raise `ValueError` at
parse time (`_parse_smc_setup`), NOT evaluate to `False`. This is the schema
contract; the frozen design prose that reads as if `direction` were optional with
a default is stale.

| `type` | Required keys | Constraint |
|--------|---------------|------------|
| `price` | `op` (`above\|below`), `level` (number) | strict compare on latest close |
| `indicator` | `name`, `params` (object, default `{}`), `op`, `level` | `name` scalar series only: `rsi\|sma\|ema\|atr\|vwap` |
| `smc_setup` | `direction` (`long\|short\|any`), `min_score` (int, default `MIN_CONFLUENCE`) | any matching `Setup` on latest bar |

Tuple indicators (`macd`, `bollinger`, `stochastic`) MUST be rejected as
unsupported in v1 (deferred to an additive sub-selector key).

#### Scenario: Unknown type is false

- GIVEN `condition={"type":"magic"}`
- WHEN the engine evaluates it
- THEN the result is `False` without raising

#### Scenario: Tuple indicator rejected

- GIVEN `condition={"type":"indicator","name":"macd",...}`
- WHEN the engine evaluates it
- THEN the result is `False` (no exception)

#### Scenario: Missing direction is a config breach

- GIVEN `condition={"type":"smc_setup"}` (no `direction`)
- WHEN the condition is parsed
- THEN `ValueError` is raised (never silently defaulted)

#### Scenario: Explicit direction is accepted

- GIVEN `condition={"type":"smc_setup","direction":"any"}`
- WHEN the condition is parsed
- THEN it parses and `direction` is `"any"`
