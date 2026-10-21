# Archive Report: setup-ledger

**Change**: `setup-ledger` (issue **#260** — first link of the measurable-baseline chain)
**Archived**: 2026-10-21
**Delivered on**: `develop` at `fec7781` via PR #266 (tracker `feat/setup-ledger-to-develop`), after a two-slice chained PR review: #264 (slice 1) → #265 (slice 2)
**Verdict**: PASS_WITH_WARNINGS — both slice verifies 0 CRITICAL / 0 blockers; the fresh adversarial round's 2 CRITICAL findings were fixed before merge
**Closure**: issue #260 CLOSED with a completion comment; PR branches deleted (remote + local)

## What shipped

A global, append-only ledger that persists every SMC setup **as it stood at
emission** (`trading.Setup` + migration `0018`), a pure enriched-capture helper
(`capture_setups` + `SetupRecord` in `src/smc/signals.py`), the
`SMC_ENGINE_VERSION` constant in `src/smc/config.py`, and a zero-network
capture seam (`web/trading/setups.py`) scheduled as one isolated `try/except`
step in `worker.run_once`. `find_setups`, its frozen `Setup` shape, and both
existing callers are byte-identical (verified by empty diffs on the frozen test
file and the `src/smc/` slice-1 tree).

| Task | Status | Delivered |
|---|---|---|
| 1.1–1.5 | ✅ | `SMC_ENGINE_VERSION = "1"`; `SetupRecord` + `capture_setups` pure helper; boundary test green unedited |
| 2.1–2.5 | ✅ | Global `Setup` model (no `user`, not in `OWNED_MODELS`), unique `(symbol, interval, anchor_time, engine_version)`, index `ix_setup_sym_int_anchor`; additive migration `0018_setup` (depends `0017_charttemplate`) |
| 3.1–3.4 | ✅ | `web/trading/setups.py` seam (`run_setup_capture`, env validation naming every offender, `bulk_create(ignore_conflicts=True)`, row-count delta); isolated worker step with the import inside the `try` |
| 4.1–4.2 | ✅ | Gates: ruff, ruff format, `makemigrations --check --dry-run`, pytest; `test_no_order_surface.py` + `test_owned_model_guard.py` green unedited; no new dependency |
| 4.3 | ✅ | Archive (this report); spec sync performed; `git mv` to `archive/2026-10-21-setup-ledger/` left to the orchestrator |

## Specs synced

| Canonical spec | Action |
|---|---|
| `openspec/specs/smc-setup-ledger/spec.md` | **CREATED** (6 requirements R1–R6, 13 scenarios + 2 edge-case matrices) |
| `openspec/specs/smc-signals/spec.md` | **APPENDED** R6 (engine version constant) and R7 (enriched capture helper) — now 7 requirements, 19 scenarios; R1–R5 untouched |

No destructive deltas: every merge was additive. No requirement renumbering was
needed (the canonical `smc-signals` spec ended at R5).

## Verification evidence

| Gate | Result |
|---|---|
| Slice 1 verify (evidence `c6029a0`) | PASS_WITH_WARNINGS — 7/9 requirements, 12/14 scenarios (2 out of scope for the slice), 0 CRITICAL; 177 targeted tests |
| Slice 2 verify (evidence `6e40e6c`) | PASS_WITH_WARNINGS — 4/4 requirements, 8/8 scenarios, 0 CRITICAL; 156 targeted tests |
| Fresh adversarial review (post-slice-2, on the tracker) | **2 CRITICAL** — both FIXED (see below) |
| Final suite at `fec7781` | **1268 passed**; ruff, ruff format, `makemigrations --check --dry-run` all green |

### Adversarial review round — findings and fixes

| Severity | Finding | Fix |
|---|---|---|
| **CRITICAL** | `SETUP_CANDLE_WINDOW` was 100 while every consumer of the same setups (signals screen `SIGNALS_LIMIT`, chart API `MAX_LIMIT`, analytics `LIMIT`) uses **200**. `find_structure` is path-dependent (it seeds its trend at the first break in the window), so a 100-bar window is a *different signal*, not a suffix — the ledger would have recorded what the user is never shown. | `db2a907` — `SMC_WINDOW = 200` in the seam; helper composition pinned to payload defaults; field-level **parity test** replays seeded candles through both `get_smc_payload` and the seam and asserts equality. |
| **CRITICAL** | `engine_version` was the bare constant; changing the window geometry would have silently collided with old rows under the unique key and dropped them. | `db2a907` — `engine_stamp()` returns `"{SMC_ENGINE_VERSION}:w{SMC_WINDOW}"` (e.g. `"1:w200"`), so identity = (anchor, engine, window geometry). |
| HIGH-adjacent | A gappy (non-contiguous) window re-seeds structure and shifts every index — a window with holes must not be recorded as truth. | `a6da614` — continuity-guard test: the pair is declined entirely when the persisted span doesn't match the interval grid. |
| PERF | Capture re-derived on every cycle even when the window hadn't moved. | `f7e763f` — capture gated on candle progress (`n_candles > 0` or the candle cycle failed); isolation and the `(funding, ticker)` return contract unchanged. |
| WARN | Slice-2 verify findings W2 (factually wrong worker comment about import-time validation), W3 (multi-offender `ValueError` untested), W4 (near-tautological default-interval test). | `795530c` — comment corrected; multi-offender path covered; assertion now checks every configured default is a persisted interval. |

## Deviations from the original design

1. **Index name shortened**: `ix_setup_sym_int_anchor` (23 chars) instead of the
   design's `ix_setup_symbol_interval_anchor` — Django's `Index.max_name_length`
   is 30 and the original is 31 chars (`models.E034`, verified empirically in
   the slice-1 adversarial checks). Follows the repo's existing `ix_*` convention.
2. **`engine_version` became a Char(16) string stamped via `engine_stamp()`**
   (`"1:w200"`), fingerprinting the window geometry — the design had the bare
   hand-bumped constant. Necessary consequence of the window fix; keeps the
   unique constraint from swallowing rows derived under new geometry.
3. **Window 100 → 200** (`SMC_WINDOW`), with the parity test described above.
   The design's 100 (chosen to match `ALERT_CANDLE_WINDOW`) recorded a different
   signal than the one displayed; parity with the chart payload wins.
4. **Knobs removed from `capture_setups`**: the helper exposes only
   `atr_window=14`; composition is pinned to the payload's exact chain with
   every tunable at its default (`find_swings → find_structure → dealing_range
   → find_setups`). The caller owns only the window length. Removes the
   `range_` override divergence surface flagged by slice-1 verification (S4).
5. **Capture gated on candle progress** (`f7e763f`) — not in the design; skips
   redundant re-derivation on unchanged windows.
6. (Design-stage, pre-approved) **D4/D5** narrowed the proposal: six unused
   fields dropped (`zone_top/bottom`, `range_high/low`, `has_ob/has_fvg`) and
   the unique key extended with `engine_version`, overriding the proposal's
   3-field constraint which would have made a version bump unable to insert.

## Final metrics

| Metric | Value |
|---|---|
| Files changed | 10 (2 src, 4 web, 4 tests) |
| Lines | **+1033 / −3** (`src/smc/config.py` +4 · `src/smc/signals.py` +82/−3 · `models.py` +39 · `0018_setup.py` +52 · `setups.py` +118 · `worker.py` +15 · tests +723) |
| Full suite | 1268 passed (105 e2e deselected in targeted runs) |
| Gates | ruff check ✓ · ruff format ✓ · `makemigrations --check --dry-run` ✓ · no new dependency ✓ |
| PRs | #264 (slice 1) → #265 (slice 2) → #266 (tracker→develop, merge `fec7781`) |

The 400-line review budget was enforced by the feature-branch chain; slice 2
exceeded its 164-line forecast under the user-accepted `size:exception`.

## Accepted warnings (documented in the verify reports)

- **W1 (both slices, still open)** — pre-existing pytest 9 conftest-visibility
  quirk: a `tests/web/*` module listed before a root `tests/test_*.py` module
  hides the `user_a` fixture. Reproduced on a clean `develop` worktree; not
  attributable to this change. Fix separately (conftest/fixture visibility).
- Slice-1 W2/W3 and slice-2 W2/W3/W4 were fixed before merge (`795530c` and
  the review-fix commits). Slice-1 suggestions S1/S3/S5 are informational only.

## Follow-ups

- **#261 — outcomes**: measure emitted setups against `entry`/`stop`/
  `take_profit`; reuses `run_setup_capture`/`Setup`. Now unblocked — this
  ledger is its baseline.
- **#262 — ATR stop floor**.
- **#263 — `/setups/` screen** (user-facing read of the ledger).
- Harness: fix the W1 pytest conftest-visibility quirk so the prescribed test
  ordering exits 0.
