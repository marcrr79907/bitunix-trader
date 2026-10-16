# Exploration: persistence-foundation (Ola 3, F11 / issue #124)

> First change of **Ola 3**, and the ONLY roadmap change carrying a **real data
> migration (backfill)**. Must land BEFORE the drawing-interaction feature F4,
> which would otherwise pay migration + rework. Read-only — no order execution.

## Current State

The chart persistence layer grew in two orthogonal shapes and is now
inconsistent, so Ola 3 reconciles it:

- **`Drawing`** is per `(user, symbol, interval)` — a row per shape, indexed
  `(user, symbol, interval)`, **no unique constraint** (many per chart). The
  GET filter *and* the POST body both require `interval`; the JS adapter
  (`controllers/drawings.js`) loads per `(symbol, interval)` and `main.js::switchTo`
  calls `drawings.clearForSwitch()` on **every** switch, so drawings vanish on
  an interval change. **Decision A (locked by user)**: drawings become per
  **symbol** (TradingView-style: one set visible across all intervals of a pair).
- **SMC family toggles** (`state.smc`) are **session-only**: `smc.js::readSmc()`
  reads the six `.smc-toggle` checkboxes, `refreshSmc()` re-renders from the
  already-fetched payload, and nothing persists. Spec `smc-overlay` R7 says
  "Toggle state MUST NOT be persisted" — Ola 3 **inverts** that requirement.
- **`ChartLayout`** holds exactly one layout per `(user, symbol, interval)`
  (`indicators` JSON `[{token, params, style}]`, unique constraint). There is
  **no** multi-layout / named-template concept anywhere.
- **`ChartPreference`** is user-global (OneToOne): `last_interval`, `scale_mode`,
  `chart_type`, `theme`, with a **partial-PUT** endpoint — the natural home for a
  user-global persisted preference.

Only **additive** migrations exist (`CreateModel`, `AddField`). **No precedent**
for `RemoveField`, `RunPython`, or `SeparateDatabaseAndState` in the tree — this
change writes the first destructive migration, so it sets the pattern.

## Affected Areas

- `web/trading/models.py` — `Drawing` drops `interval`, index becomes
  `(user, symbol)`; a persistence field is added to `ChartLayout` **or**
  `ChartPreference` (SMC toggles); optionally `LayoutTemplate` (templates).
- `web/trading/migrations/0012_*` (new) — drop `interval`, rebuild the index;
  `0013_*` (new) adds the toggles field.
- `web/market/views.py` — `api_drawings` GET drops the `interval` filter;
  `_post_drawing` stops requiring `interval`; `api_layout`/`api_preference`
  carry the toggles field if that home is chosen.
- `web/market/quotes.py` — `parse_drawing` unchanged; no `interval` validator
  change (interval is removed from the drawing contract, not re-validated).
- `web/market/templates/market/controllers/drawings.js` — `loadDrawings(symbol)`
  drops interval; `createDrawing` drops interval; `clearForSwitch` invoked only
  on **symbol** change. **File is exactly 300 lines (ceiling) — any net addition
  overflows the guard.**
- `web/market/templates/market/controllers/smc.js` — persist/restore toggles
  (new write path) if SMC persistence lands here.
- `web/market/templates/market/main.js` — `switchTo` conditionally clears
  drawings; boot restores toggles. Touches the `gen` guards; must not regress
  the DEBT-8 `stream.subscribe` fix.
- `web/market/templates/market/controllers/indicators.js` — `saveLayout`/
  `loadLayout` gain `smc` if the layout home is chosen.
- `tests/web/test_market_api.py`, `test_isolation.py`, `test_owned_model_guard.py`,
  `test_market_e2e.py` — the drawings-interval assertions and fixtures change
  (behavior change is expected, not a regression).
- `openspec/specs/{chart-drawings,chart-config,smc-overlay,market-chart}/spec.md`
  — delta specs (drawings key drops interval; smc R7 inverts).

## Migration Design (THE risky part)

**Column-drop policy: DROP `interval` outright** (not keep-as-legacy-ignored).

- Keeping a legacy-ignored column is dead weight: nothing reads it, it invites
  future confusion, and it forces the index to carry a dead column. A plain drop
  is honest and reversible-by-reconstruction.
- Rows per `(user, symbol, interval)` collapse to `(user, symbol)`. Because the
  table has **no unique constraint**, two rows that differed only by interval
  simply **coexist** as distinct shapes or duplicate-looking annotations. That is
  semantically correct (they are distinct user-drawn shapes) and cannot raise
  `IntegrityError`.

**Duplicate policy: KEEP ALL rows, no dedupe.** There is no reliable key to
dedupe on (two hlines at the same price could be intentional), and the absence
of a unique constraint means nothing collides. Deduping would silently destroy
user data — unacceptable on an irreversible-ish migration.

**Forward migration** (single file `0012_drawing_per_symbol.py`, hand-written):

1. `RemoveIndex(model_name="drawing", name="ix_drawing_user_sym_interval")`
2. `RemoveField(model_name="drawing", name="interval")`
3. `AddIndex(model_name="drawing", index=Index(fields=["user","symbol"],
   name="ix_drawing_user_symbol"))`

Order matters on SQLite: the index referencing `interval` MUST be removed
before the column. `makemigrations --check` MUST be green after the model edit.

**Reverse migration (rollback):** re-`AddField(interval, default="1m",
max_length=8)` → re-`RemoveIndex` the new one → re-`AddIndex` the old tuple.
Reverse is **lossy** (every row gets `interval="1m"`; the original per-interval
split is unrecoverable) — this is the documented rollback contract. Archive rule
says "warn before merging destructive deltas"; this is that delta.

**Data-migration / backfill:** none required — the drop *is* the merge. There is
no computed target value to backfill, so **no `RunPython`**. This keeps the
migration deterministic and cheap on a populated prod (one drop + two index
ops). Prod-not-empty is handled by the no-dedupe policy: nothing to collide.

## SMC Toggles Home — Recommendation

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **`ChartPreference` (user-global)** — add `smc` JSONField | Reuses the partial-PUT endpoint verbatim; **consistent with Decision A** (a per-symbol-per-interval toggle would reset on every interval switch, contradicting "configure once per pair"); global toggles don't flicker across intervals; settled pattern. | Not per-chart (can't show different families on 1m vs 1D). | Low: 1 additive `AddField` migration + 1 endpoint field + smc.js read/write. |
| **`ChartLayout` (per chart)** — add `smc` JSONField | Per-chart fidelity; rides the per-key `layout:loaded`/`saveLayout` path already reloaded on `switchTo`. | Couples the SMC controller to the indicators-owned layout endpoint; needs a new bus/`onSmcChange` wiring in `main`; per-interval reset is surprising given drawings are per-symbol. | Medium: 1 additive migration + layout payload + cross-controller wiring. |

**Recommendation: `ChartPreference` (user-global).** It is the smaller diff, it
reuses the partial-PUT semantics designed for exactly this, and it is consistent
with Decision A's "persist once, visible everywhere" philosophy — a per-interval
SMC toggle would silently reset on the exact interval switch whose drawing
persistence we are fixing. The issue leaned toward the layout; this is the
**key decision to confirm**.

## Templates Decision — Recommendation

**Defer `LayoutTemplate` to Ola 5 (the UI).** A named-template model with no UI
to save/load/select is dead data — YAGNI. F11 lists it, but its consumer is a
template picker that does not exist yet. Shipping the model now spends a
migration + model + endpoint + isolation/guard tests on an unused surface. If
the roadmap insists the persistence layer precede the UI, the fallback is a
minimal `LayoutTemplate(UserOwnedModel)` (`name` + `layout` JSON snapshot, unique
`(user, name)`) with a CRUD endpoint — but that is **recommend: Ola 5**. Confirm.

## Key Decisions (for the user)

1. **Migration policy** — DROP `interval`, keep ALL rows, no dedupe, lossy
   reverse. (Recommend: yes.)
2. **SMC toggles home** — `ChartPreference` (user-global) vs `ChartLayout`
   (per chart). (Recommend: ChartPreference.)
3. **Templates in Ola 3 vs Ola 5** — defer to Ola 5. (Recommend: Ola 5.)
4. **POST `interval` back-compat** — accept-and-ignore the key (no 400) vs hard
   reject. (Recommend: accept-and-ignore — minimal, lets stale E2E/clients live.)
5. **Drawings clear semantics on `switchTo`** — clear only on **symbol** change;
   on interval change keep `currentDrawings` attached and skip the refetch.

## Open Questions

- SMC toggles home (decision 2) — the single most consequential fork.
- Templates scope (decision 3).
- Does an interval-only `switchTo` still call `refreshDrawings()` (idempotent
  refetch) or skip it entirely to save a request? (Recommend: skip on
  interval-only, keep on symbol change.)
- Should `main.js::switchTo`'s tool/pending-anchor reset still fire on interval
  change (mid-drawing interval switch)? (Recommend: keep resetting the tool —
  a stale anchor with an old time is worse than dropping it.)

## Risks

- **Irreversible-ish migration on prod-not-empty.** Reverse loses the
  per-interval split. Mitigation: documented contract + archive "warn before
  destructive deltas"; no dedupe so no data destruction on the forward path.
- **First destructive migration in the tree** — no `RemoveField`/`RunPython`
  precedent; SQLite index-before-column ordering is easy to get wrong.
- **Behavior-change test edits.** `test_switch_clears_then_loads_drawings`,
  the `per_interval_drawings` fixture, and the `interval` key in
  `test_click_with_tool_fires_post`'s POST body assert the OLD contract and MUST
  be updated (documented behavior change, not a regression). The change contract
  forbids "assertion edits" only for *frozen invariants* — this is a spec delta.
- **Frozen seams.** `window.marketChart` MUST keep its **8 keys**
  (`drawings` stays; no new key). Store vocabulary is frozen. `MODULE_ALLOWLIST`
  / `CONTROLLER_ALLOWLIST` unchanged.
- **`drawings.js` is at the 300-line ceiling** — net additions overflow
  `test_module_size_guard`. Any growth MUST be offset (or kept in `main.js`,
  which is at 256).
- **`main.js::switchTo` change** touches the `gen` guard ordering and sits next
  to the DEBT-8 `stream.subscribe` fix — do not regress.
- **Patch coverage 100%** (`diff-cover --fail-under=100`) and web `--fail-under=85`
  — every new Python line (migration ops, endpoint branches) must be exercised.
- **No-deps / CSP.** No new runtime dependency; no inline script; `src/`
  framework-free. SMC persistence adds no dependency (JSONField + existing fetch).
- **E2E verify coupling.** E2E is dev-only and flaky under load (documented
  DEBT-8); the drawings/smc E2E edits must be readiness-gated.

## Recommended PR Shape (chained — mandatory with a real migration)

| Slice | Scope | Est. size |
|---|---|---|
| **S1 — drawings per symbol** | `Drawing` model (drop `interval`, new index) + `0012` migration + `api_drawings` GET/POST + `drawings.js`/`main.js` adapter + tests (model/isolation/guard/endpoint/E2E edits) | ~220–280 lines |
| **S2 — SMC toggles persistence** | `ChartPreference.smc` + `0013` additive migration + `api_preference` field + `smc.js` read/write + boot restore + tests | ~130–170 lines |
| **S3 — templates** | `LayoutTemplate` + endpoint + tests | **deferred to Ola 5** (recommended) |

S1 alone approaches the **400-line** review budget; S1 and S2 are autonomous,
own-tested, and trivially revertible. If S3 ships, it is a third chained slice.
**400-line budget risk for S1: High; overall: High** → delivery strategy should
resolve to **chained PRs** (S1 → tracker/feature branch; S2 → S1).

## Recommendation

Proceed to **proposal** with: (1) drawings-per-symbol via a destructive
`RemoveField`+index migration, keep-all/no-dedupe, lossy reverse; (2) SMC toggles
in `ChartPreference` (user-global) unless the user prefers per-chart; (3) defer
templates to Ola 5; (4) chained S1/S2 slices. All three SMC/template/migration
forks are user decisions that gate the spec — confirm before `sdd-spec`.

## Ready for Proposal

**Yes.** The codebase is fully mapped; the migration, endpoint, adapter, and test
deltas are concrete. Blocking user decisions: SMC toggles home, templates
timing, migration duplicate policy (recommended defaults above).
