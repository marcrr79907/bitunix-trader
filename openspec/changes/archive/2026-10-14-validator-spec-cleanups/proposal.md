# Proposal: validator-spec-cleanups

## Intent

Close the four deferred, non-blocking verification warnings carried forward by
three archived changes (issue #147, DEBT-6), so they stop recurring in every
verify report. All four are **documentation gaps** between canonical specs and
code that is already correct and already tested. No production behavior changes.

## Scope

### In Scope
- **W3/W4 (chart-config)**: canonical `chart-config` R2 gains an explicit
  **accept-and-ignore** clause — a cross-token param key and a legacy token
  (`sma20`/`ema20`/`rsi14`) are accepted and stored verbatim; a legacy token
  renders degraded (candles only). Unknown param *keys* still 400.
- **W2 (smc-range)**: canonical `smc-range` R2 gains the `range_ is None →
  "equilibrium"` case + edge-matrix row. Already asserted by
  `test_smc_range.py`.
- **W1 (alert-rules)**: reconciling note in canonical `alert-rules` R2 — explicit
  `direction` is REQUIRED (no default). Stale prose lives only in the **frozen**
  archived `design.md`; that file is not touched (audit trail).
- **W4 (smc-zones)**: one-line note + edge row in canonical `smc-zones` R4
  documenting the ≤2-bar confirmed-swing look-ahead effect (intentional
  simplification, not a defect).

### Out of Scope
- Any `quotes.py` code change, any new 400 (patch gate N/A).
- Editing anything under `openspec/changes/archive/` (audit trail, frozen).
- Any behavior change, migration, dependency, or UI path.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `chart-config`: R2 prose — accept-and-ignore contract for cross-token params
  and legacy tokens.
- `smc-range`: R2 — `None`-range → `"equilibrium"` case + edge row.
- `alert-rules`: R2 — `direction` explicitly required (clarifying note).
- `smc-zones`: R4 — confirmed-swings-only ≤2-bar look-ahead note + edge row.

## Approach

Read-only doc reconciliation in the **canonical** specs only. W3/W4/W2/W1/W4-sweep
each add a clarifying clause/scenario to the owning requirement. No code edit, so
no test change and the 100% patch gate is trivially green. Reconcile W1 in the
canonical spec, not the archived `design.md`, per the archive-immutability rule.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/specs/chart-config/spec.md` | Modified | R2 accept-and-ignore clause |
| `openspec/specs/smc-range/spec.md` | Modified | R2 `None` case + edge row |
| `openspec/specs/alert-rules/spec.md` | Modified | R2 `direction` required note |
| `openspec/specs/smc-zones/spec.md` | Modified | R4 confirmation note + edge row |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| DOCUMENT blesses a validator hole | Med | Prose frames it as reachable only via hand-crafted PUT; no UI path emits it. A 400 would be a breaking change on previously-accepted input with stored-layout migration risk, for a non-defect. |
| Editing archived design (W1) | Low | Reconciled in canonical spec; archive untouched. |
| Doc drift re-opens the warning | Low | Canonical spec is the source of truth; archive report cross-references it. |

## Rollback Plan

Trivial: revert the branch. Four spec files return to their prior text. No code,
dependency, migration, or data to unwind.

## Dependencies

- Archived reports: `chart-config`, `smc-range`, `alert-rules`, `smc-zones`.
- Canonical specs: `openspec/specs/{chart-config,smc-range,alert-rules,smc-zones}/spec.md`.
- Existing tests already cover runtime behavior (no new tests).

## Success Criteria

- [ ] The four canonical specs state the behavior the code already implements.
- [ ] W3/W4 accept-and-ignore contract documented; no 400 added.
- [ ] W1 reconciled in canonical spec; archived `design.md` unmodified.
- [ ] `ruff check . && ruff format --check .` clean; `python -m pytest` green with zero test changes.

## Review Workload Forecast

- Estimated diff: **~40–80 changed lines**, docs-only, 0 code.
- Decision needed before apply: No
- Chained PRs recommended: No
- 400-line budget risk: Low
