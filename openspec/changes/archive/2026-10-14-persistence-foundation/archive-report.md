# Archive Report: persistence-foundation

**Archived**: 2026-10-14
**Verdict**: `pass_with_warnings` (0 blockers, 0 critical; 2 non-blocking warnings —
W1 class-C E2E flake DEBT-8, W2 `tasks.md` checkboxes) — `chart-drawings` R1/R2/R4/R7,
`smc-overlay` R7, `chart-config` R8/R9, `per-user-isolation` R14.2 (all MODIFIED).
**Delivery**: Feature Branch Chain, 3 PRs, all **based on the tracker**
`feat/persistence-foundation` — **#163** (S1 drawings) + **#164** (S2 SMC toggles) →
**#165** (tracker → `develop`), merged.
**Issue**: #124 (Ola 3 / F11) — **only PARTIALLY closed**; reopened for the remaining
F11 items (see Carry-forward).
**Branch**: `feat/persistence-foundation` (tracker `2db9262`) ← S1 `025a381`, S2
`20c6787`; verify HEAD `20c6787` → merge `60e7ffa` on `develop`.

## What Shipped

Two persistence seams that were inconsistent before F4 (drawing-interaction) lands.
This change carries the **first destructive migration in the tree**.

| Area | Delivered |
|------|-----------|
| Drawings per symbol | `Drawing` key drops `interval` → `(user, symbol)`; index `ix_drawing_user_symbol`; no unique constraint. `api_drawings` GET filters `(user, symbol)` only (stray `interval` ignored); POST accept-and-ignores `interval` (never 400); DELETE unchanged. JS: `loadDrawings(symbol)`, `createDrawing` body drops `interval`; `switchTo` clears drawings + refetches **only on a symbol change** — an interval-only switch keeps shapes with no refetch. |
| Migration `0012_drawing_per_symbol` | **Destructive** (first `RemoveField` in the tree). SQLite-safe order: `RemoveIndex(ix_drawing_user_sym_interval)` → `AlterField(interval, default="1m")` (load-bearing: sets the reverse default) → `RemoveField(interval)` → `AddIndex(ix_drawing_user_symbol)`. **Keep ALL rows, no dedupe** (no unique constraint ⇒ nothing collides; dedupe would destroy user data). **Reverse is LOSSY** — re-adds `interval="1m"` to every row; the original per-interval split is NOT recoverable. |
| SMC toggles persisted | SMC family toggles (`swings|structure|order_blocks|fvg|range|setups`) persisted **user-global** on `ChartPreference.smc` (`JSONField(default=dict)`); `{}` means all-ON. Boot restores from the preference and applies to the checkboxes; toggling re-renders with no refetch and debounce-saves through the existing partial-PUT `/market/api/preference`. Toggles MUST NOT reset on an interval switch (user-global, not per-chart). Failed fetch/save is non-fatal. |
| Migration `0013_chartpreference_smc` | **Additive** — `AddField(smc, JSONField(default=dict))`. Zero data loss; independent of `0012`. |
| Preference API | `GET` body gains `smc` (default `{}`); `PUT` accepts `smc` as a JSON object, validated by `parse_smc` (dict, keys ⊆ the 6 families, bool values; else `ValueError` → 400 no-write). Partial PUT applies only present keys. |
| Seams held | `window.marketChart` still exactly its 8 frozen keys (no new key); `drawings.js`/`smc.js` ≤300 lines; `gen` guard + DEBT-8 `stream.subscribe` untouched; no new runtime dependency; CSP unchanged; `src/` framework-free; order scanner clean. |

## Deferred to Ola 5 (issue #124 only PARTIALLY closed)

- **Layout templates** (`LayoutTemplate`): **deferred to Ola 5** — no UI consumer yet
  (shipping it now would be dead data). Out of scope in the proposal.
- **Symbol search**: **deferred** (out of scope; listed in the proposal's "Out of
  Scope").
- Because these F11 items remain, **issue #124 was reopened for the remaining F11
  work** after the tracker PR merged. This archive closes only the slice delivered
  here (drawings per symbol + SMC toggle persistence), not the whole F11 epic.

## Requirements Satisfied

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-drawings | R1 — Drawing model, ownership, and index (MODIFIED) | ✅ Key `(user, symbol)`; index `ix_drawing_user_symbol`, no unique constraint; `0012` removes the old index before dropping `interval`, keeps all rows, no dedupe; reverse lossy (`interval="1m"`). 5 scenarios. |
| chart-drawings | R2 — Drawings CRUD API (MODIFIED) | ✅ GET `?symbol=` returns the caller's `(user, symbol)` rows (no `interval` filter); POST stores `(user, symbol)` and accepts-and-ignores a stray `interval`; DELETE idempotent 404 on miss. 8 scenarios. |
| chart-drawings | R4 — Validation before write (MODIFIED) | ✅ `interval` is no longer part of the contract — its presence/value never 400s; unknown `kind` / bad shape still 400 before write; `parse_drawing` unchanged. 3 scenarios. |
| chart-drawings | R7 — Load and restore on boot and switch (MODIFIED) | ✅ Fetch per `symbol`; `switchTo` clears+reloads only on a symbol change, interval-only keeps drawings with no refetch; failed fetch non-fatal; 8-key seam held. 6 scenarios. |
| smc-overlay | R7 — Per-element toggles persist per user (MODIFIED; was session-only) | ✅ Toggles persisted user-global on `ChartPreference.smc`; loaded at boot; survive reload and interval switch; failed fetch defaults all-ON. 4 scenarios. |
| chart-config | R8 — User-global interval preference model (MODIFIED) | ✅ `ChartPreference` gains `smc` `JSONField(default=dict)`; `0013` additive. 3 scenarios. |
| chart-config | R9 — Preference API (MODIFIED) | ✅ GET/PUT body carries `smc`; partial PUT; `parse_smc` invalid → 400 no-write; one-row-per-user upsert via `for_user`. 10 scenarios. |
| per-user-isolation | R14.2 — Cross-user read denied (MODIFIED) | ✅ Drawing evidence re-keyed to `(user, symbol)`; ownership unaffected; A≠B `DoesNotExist` holds for the per-symbol Drawing (and all other owned models). 10 scenarios. |

**Compliance summary**: 8/8 requirements, 47/47 scenarios compliant (verify-report).

**Preserved untouched** (no requirement dropped):
- `chart-drawings`: R3 (A ≠ B isolation), R5 (kind-specific point/style schemas), R6
  (Lightweight Charts v5 render contract), R8 (read-only boundary / CSP / no new
  dependency). R5's validation matrix row was updated from `interval ∉ INTERVALS → 400`
  to "interval present → accepted and ignored" solely to stay coherent with the
  modified R4 — no R5 semantic change.
- `smc-overlay`: R1–R6, R8–R11 (endpoint, candle window, frozen payload, degradation,
  market-global scoping, render contract, multi-TF reload, payload↔drawn equality,
  single-source, read-only/CSP/no-dep).
- `chart-config`: R1–R7, R10–R13 (layout persistence, layout API, layout isolation,
  boot restore, save on change, param vocabulary, CSP; preference boot restore, R11/R12
  preference isolation + CSP, R13 theme vocabulary).
- `per-user-isolation`: R14.1, R14.3, R14.4, R14.5.

Delta fit: all four deltas were MODIFIED-only; every requirement matched by name and
was replaced in place. No requirement name collision; no ADDED/REMOVED delta; merge
non-destructive. `chart-drawings` keeps 8 requirements, `smc-overlay` 11,
`chart-config` 13, `per-user-isolation` 5 — same counts as before the merge.

## Warnings Carried (non-blocking)

- **W1 — class-C E2E flake under load (DEBT-8)**: the E2E suite is non-deterministic
  when run end-to-end under resource pressure (run1 all-green, run2 1 failure, run3 4
  failures — each a different, **untouched** test, `Page.goto`/`wait_for_function`
  timeouts). The 9 change-specific E2E tests are deterministic in isolation, and CI
  does not run E2E. Judged a **pre-existing infra flake, not a regression** —
  documented, not hidden, not retried.
- **W2 — `tasks.md` checkboxes**: 27/27 tasks completed (apply-progress) but the file
  shipped with 0 `[x]` because the apply session's hard contract forbids editing
  `openspec/**`. **Bookkeeping only — resolved by this archive**: all 27 checkboxes
  flipped to `[x]`.

## Rollback (MUST be a deliberate, warned decision)

- **S2 (SMC toggles)**: revert PR — drop `0013`, remove the `smc` field + endpoint +
  `smc.js` writes. `0013` is **additive; zero data loss**. Independent of S1.
- **S1 (drawings)**: `migrate trading 0011` runs the **LOSSY reverse** (re-adds
  `interval` defaulted to `"1m"`); **the original per-interval split is NOT
  recoverable**. The forward path never destroyed rows (keep-all). Rollback MUST be a
  deliberate, warned operation, never an accident. Each chained PR is independently
  revertible.

## Verification Evidence (from verify-report)

- `makemigrations --check --dry-run`: `No changes detected` (exit 0).
- `node --test "tests/js/**/*.test.js"`: **162 passed, 0 fail**.
- `pytest tests/`: **914 passed, 69 deselected**; `--ignore=tests/web`: **337 passed**.
- `diff-cover --fail-under=100`: **100%** patch (`quotes.py`, `views.py`, `models.py`).
- `ruff check .` / `ruff format --check .`: clean / 140 files formatted.
- `requirements.txt` vs `develop`: **empty diff**.
- Migration adversarial probe (throwaway sqlite, real `migrate` CLI): 3 seeded rows
  (same symbol, differing `interval`) all survived `0012`; `migrate trading 0011`
  restored `interval="1m","1m","1m"` (lossy).
- Endpoint probe: POST stale `interval:"1h"` → 201; GET `?symbol=` vs
  `?symbol=&interval=7m` identical; A≠B isolated.
- SMC probe: default `smc:{}`; PUT round-trips; `smc:"nope"` / `{"bogus":true}` /
  `{"range":1}` each → 400 no-write with prior value intact.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-drawings | Updated | R1/R2/R4/R7 replaced (per-`(user,symbol)` keying; `0012` destructive order + keep-all + lossy reverse; GET/POST contract; survives-interval-switch). R3/R5/R6/R8 preserved (R5 matrix row + R3 scenario re-worded for interval coherence). 8 requirements retained. |
| smc-overlay | Updated | R7 replaced — toggles now persisted on `ChartPreference.smc` (was session-only; "not persisted" scenario removed). R1–R6, R8–R11 preserved. 11 requirements retained. |
| chart-config | Updated | R8 (model + `smc`, `0013` additive) and R9 (API `smc` + partial PUT + `parse_smc` 400) replaced. R1–R7, R10–R13 preserved. 13 requirements retained. |
| per-user-isolation | Updated | R14.2 Drawing evidence re-keyed to `(user, symbol)`. R14.1/R14.3/R14.4/R14.5 preserved. 5 requirements retained. |

## Carry-forward

- **#124 (Ola 3 / F11) is PARTIALLY closed** and was **reopened** for the remaining
  F11 items — **layout templates** and **symbol search**, both deferred to **Ola 5**.
  Ola 5 MUST consume them.
- **W1 (DEBT-8 class-C E2E flake) remains open** — pre-existing infra flake; a
  follow-up harness rework (per-test DB isolation / transactional live server) could
  address it. Not introduced by this change.
- **Migration rollback hazard persists**: `migrate trading 0011` is LOSSY on drawings
  (per-interval split unrecoverable). Anyone reverting S1 MUST warn first.
- Frozen seams remain in force: 8-key `window.marketChart`, layered ESM inventory,
  module-size ceiling (300), `#68` single-write-path, DEBT-1 channel guard, per-user
  ownership.

## SDD Cycle Complete

Explored → proposed (chained, first destructive migration) → designed → tasked →
implemented (Feature Branch Chain: #163 S1 + #164 S2 → tracker #165) → verified
(`pass_with_warnings`; 47/47 scenarios, patch 100%, migration round-trip independently
reproduced) → merged to `develop` → archived.

Traceability: `openspec/changes/archive/2026-10-14-persistence-foundation/`
(explore, proposal, design, specs, tasks, verify-report); engram
`sdd/persistence-foundation/archive-report`.
