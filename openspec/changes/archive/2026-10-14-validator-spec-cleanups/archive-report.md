# Archive Report: validator-spec-cleanups

**Archived**: 2026-10-14
**Verdict**: `pass` (DOCS-ONLY change — 0 code, 0 tests, no behavior change).
**Delivery**: single PR — **#158**, merged to `develop`. No chain.
**Issue**: #147 (DEBT-6, P2) — deferred verify-warning cleanup before Ola 3.
**Branch**: `feat/validator-spec-cleanups` → `develop`.

## What Shipped

Four **clarifying spec reconciliations** that close the deferred, non-blocking
verification warnings carried forward by three archived changes (chart-config
W3/W4, smc-range W2, alert-rules W1, smc-zones W4). Each delta records the
behavior the code **already implements and already tests**; no requirement is
added, removed, or changed in substance — WHAT already holds, the canonical
specs now SAY it.

**DOCS-ONLY: no production file, no test, no spec-behavior change, no runtime
dependency, no migration, no UI path.**

| Point | Domain | Delivered |
|-------|--------|-----------|
| W3 (cross-token params) | chart-config | R2 accept-and-ignore note: a cross-token param key (e.g. `ema` + `sma_len`) is accepted and stored verbatim — no 400; ignored at render time. |
| W4 (legacy tokens) | chart-config | R2 note: `sma20`/`ema20`/`rsi14` accepted and stored verbatim; JS adapter renders **degraded** (candles only, no indicator series). Unknown param key still → 400. |
| W2 (`classify_price(price, None)`) | smc-range | R2 `range_ is None` → `"equilibrium"` case + scenario + edge-matrix row. |
| W1 (`direction` required) | alert-rules | R2 clarifying note: explicit `direction` REQUIRED for `smc_setup`; missing/unknown → `ValueError` at parse time (not `False`). +2 scenarios. |
| W4 (sweep look-ahead) | smc-zones | R4 confirmed-swings-only ≤2-bar look-ahead note + scenario + edge-matrix row. |

## No-Behavior-Change Proof

```
$ git diff origin/develop -- web/ src/
(empty output)
```

`web/` and `src/` are byte-identical to `develop`. The change touched only
`openspec/**`. No `quotes.py` edit; no new 400.

## Decisions

- **W3/W4 — DOCUMENT, not REJECT.** The issue offered "reject (400) or document
  that they are ignored." A 400 on previously-accepted input is a real behavior
  change with stored-layout migration risk, for a non-defect reachable only via a
  hand-crafted `PUT` (no UI path emits either shape). DOCUMENT keeps the change
  100% non-breaking, preserves stored-data compatibility, and closes the warning
  by making the contract explicit. **REJECT remains available** if the boundary
  is later hardened.
- **W1 — reconciled in the CANONICAL spec, not the frozen archived `design.md`.**
  The `alert-rules` canonical spec R2 now carries the `direction`-required note;
  the stale prose lives only in `openspec/changes/archive/2026-10-12-alert-rules/design.md`,
  which is **untouched** (audit-trail immutability, `openspec-convention.md`).
  The archived archive-report already said to fix the design "only if reused."
- **Single change, single PR.** All four points are small, read-only, and share
  the same doc nature. Well under the 400-line review budget.

## Warnings Closed

| Warning | Origin | Status |
|---------|--------|--------|
| W3 cross-token params | chart-config verify | ✅ Documented in canonical R2 |
| W4 legacy tokens | chart-config verify | ✅ Documented in canonical R2 |
| W2 `classify_price(price, None)` | smc-range verify | ✅ Documented in canonical R2 + edge row |
| W1 `direction` prose | alert-rules verify | ✅ Reconciled in canonical R2; archive design frozen |
| W4 sweep look-ahead | smc-zones verify | ✅ Documented in canonical R4 + edge row |

These warnings stop recurring in every subsequent verify report.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-config | Updated | R2: added accept-and-ignore contract note + 3 scenarios (cross-token key accepted, legacy token degraded, unknown key → 400). R1, R3–R12 preserved. |
| smc-range | Updated | R2: added `range_ is None → "equilibrium"` clause + scenario; R3 edge-matrix gained the `None` row. R1, R3 preserved. |
| alert-rules | Updated | R2: added `direction`-REQUIRED note + 2 scenarios (missing → ValueError, explicit accepted). R1, R3–R9 preserved. |
| smc-zones | Updated | R4: added confirmed-swings-only ≤2-bar look-ahead note + scenario; R5 edge-matrix gained the ≤2-bar row. R1–R3, R5 preserved. |

**No requirement dropped.** Every pre-existing requirement, scenario, and
edge-matrix row in the four canonical specs is preserved; the deltas are
additive clarifications only.

## Verification Gates

- `git diff origin/develop -- web/ src/` EMPTY → no behavior change proven.
- No edit under `openspec/changes/archive/**` (immutable audit trail) during apply.
- `git status` confined to `openspec/**` archive/spec moves.
- Rollback: revert the branch — 4 spec files return to prior text (no code, data,
  dependency, or migration to unwind).

## Carry-forward

- W3/W4 stay DOCUMENT; if the boundary is hardened later, REJECT (validator
  key-set scoping + legacy-token allow-list + 400) is the tracked upgrade path.
- Frozen seams unchanged: chart-config R1 JSON round-trip, alert-rules R2 frozen
  `condition` schema, smc-zones confirmed-swings consumption of the B1 seam.

## SDD Cycle Complete

Explored → proposed → spec'd (4 deltas) → delivered as the deltas themselves
(DOCS-ONLY: the spec files were the deliverable, no apply code) → verified
(`pass`) → merged (#158) → archived.

Traceability: `openspec/changes/archive/2026-10-14-validator-spec-cleanups/`
(explore, proposal, specs, tasks, archive-report); engram
`sdd/validator-spec-cleanups/{archive-report,proposal,spec,tasks}`.
