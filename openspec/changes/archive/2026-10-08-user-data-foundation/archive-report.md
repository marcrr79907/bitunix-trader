# Archive Report: user-data-foundation

**Archived**: 2026-10-08
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 critical after re-verify) — 14/14 requirements, 31/32 scenarios, 191/191 tests
**Delivery**: 3 chained PR slices (#32 → #33 → #34) → tracker #31 → `develop`
**Merged commit range**: `2158a33`…`a21e8ed` on `develop`

## What Shipped

Phase 2 makes the Phase-0 security *mechanisms* real: per-user exchange
credentials stored as Fernet ciphertext (R13), and the `user_a`/`user_b`
isolation harness flipped from "ready" to "enforced" (R14). A new `trading`
Django app owns two models behind one ownership deep module, plus scanner
hardening over `web/` + `src/`. Strictly read-only — no order surface, no new
runtime dependency. `src/` and `accounts` untouched.

| Area | Delivered |
|------|-----------|
| Trading app | `web/trading/{__init__,apps,models}.py` — abstract `UserOwnedModel` (`user` FK + `for_user`), `ExchangeCredential`, `Watchlist` |
| Migration | `web/trading/migrations/0001_initial.py` — additive; `makemigrations --check` green (CI gate) |
| Settings | `web/config/settings/base.py` — `INSTALLED_APPS += "trading"` |
| Encryption boundary | `ExchangeCredential.set_secrets` encrypts via `web/credentials.py`; ciphertext-only columns; no `decrypt_*` method |
| R14 enforcement | `tests/web/test_isolation.py` (5), `tests/web/test_owned_model_guard.py` (12 cases) — unscoped-query AST scanner + worker trusted-zone |
| Credential scanner | `tests/web/test_credentials_mechanism.py` — `REQUEST_PATH` += `web/trading`; DB ciphertext round-trip; 9 tests |
| Order scanner | `tests/web/test_no_order_surface.py` — 23 verbs + `getattr` + 16 forbidden mutating paths over `web/` + `src/`; 7 tests |
| Tooling prerequisite | PR #30 (issue #29) — `ruff` excludes `openspec/` so docs are not reformatted; merged to `develop` (`2667553`) as a prerequisite of this cycle |

## Requirement Outcomes

| Req | Domain | Outcome | Notes |
|-----|--------|---------|-------|
| R13.1 | user-credentials | ✅ Green | Ciphertext at rest; raw column ≠ plaintext; round-trip restores via `credentials.decrypt` |
| R13.2 | user-credentials | ✅ Green | `set_secrets` encrypts at the boundary; request path never decrypts |
| R13.3 | user-credentials | ✅ Green | Empty/whitespace raises `ValueError`; no plaintext accessor |
| R13.4 | user-credentials | ✅ Green | Worker-zone decrypt on `*_encrypted`; model stays key-unaware |
| R14.1 | per-user-isolation | ✅ Green | `for_user(A)` owner-only, `for_user(B)` empty, empty-owner → `[]` |
| R14.2 | per-user-isolation | ✅ Green | `for_user(B).get(pk=A_row)` → `DoesNotExist` for both models |
| R14.3 | per-user-isolation | ✅ Green | Unscoped-query AST scanner catches `.objects.<verb>()`; scoped `for_user` passes |
| R14.4 | per-user-isolation | ✅ Green | Worker trusted zone reads across users legitimately |
| R14.5 | market-watchlist | ✅ Green | Per-user symbol list; cross-user read denied |
| R14.6 | market-watchlist | ✅ Green | Duplicate `(user, symbol)` → `IntegrityError`; same symbol across users persists |
| R14.7 | market-watchlist | ✅ Green | Reads route through `for_user`; owner only |
| R11 | security-invariants | ⚠️ Partial | Read-only enforced by scanner; "read-only credential" operational scenario has no code-level test |
| R12 | security-invariants | ✅ Green | Secrets out of repo; no live secret committed (unchanged) |
| R13 | security-invariants | ✅ Green | Enforced + scanned; new app included in credential scanner |
| R14 | security-invariants | ✅ Green | Enforced + scanned; no cross-user read |

**Legend**: ✅ green · ⚠️ partial (test-coverage gap, invariant holds).

## Carry-Forward Items

1. **R11 read-only-credential scenario untestable from code** — the "API key
   carries read-only permission" property is an operational provisioning
   control, not introspectable from the codebase. Documented out-of-band
   control; add a config assertion only if the key scope ever becomes
   representable.
2. **R14.3 scanner static-analysis ceiling** — the unscoped-query scanner
   matches a direct `<Name>.objects.<verb>()` call only. Four bypass shapes
   evade it: `getattr(ExchangeCredential.objects, "get")(...)`, manager alias
   (`q = ....objects; q.get(...)`), import alias, and qualified
   attribute chains (`trading.models.ExchangeCredential.objects.get(...)`).
   No current offender; optional hardening is a light scope/alias pass.
3. **`tasks.md` checkbox hygiene** — checkboxes were left `[ ]` through
   apply/verify to avoid child-branch merge conflicts; **fixed at archive**
   (all 38 boxes checked in the archived copy).
4. **No UI/endpoint for R14** — model-level proof only (design D4); a masked
   staff read view is deferred until the UI lands.
5. **`MultiFernet` key rotation** — out of scope; rotating
   `CREDENTIALS_FERNET_KEY` bricks all ciphertext (documented in `.env.example`).

## Verify Findings (non-blocking, fix before the noted trigger)

| # | Severity | Finding | Fix trigger |
|---|----------|---------|-------------|
| C1 | Critical | R14.3 unscoped-query scanner missing (found in first verify) | ✅ **Fixed in-change** — `d14b550` adds `test_owned_model_guard.py`; re-verify closes it |
| W1 | Low | `tasks.md` checkboxes all `[ ]` despite completed work | ✅ **Fixed at archive** — boxes checked in archived copy |
| W2 | Low | R14.4 worker read untested | ✅ **Closed** — `test_worker_zone_reads_across_users` |
| W3 | Low | R11 "read-only credential enforced" untested (pre-existing) | Documented out-of-band control; not a regression |
| S1 | Suggestion | R14.3 scanner evaded by `getattr`/alias/qualified chain (4 shapes) | Opportunistic — light scope/alias pass |
| S2 | Suggestion | Order-scanner `getattr` matches a constant verb only | Opportunistic — documented static-analysis ceiling |
| S3 | Suggestion | `for_user(unsaved_user)` raises `ValueError`, not `[]` | Opportunistic — short-circuit on `pk is None` |

## SDD Cycle Complete

Planned → implemented → verified (re-verified, prior CRITICAL closed) →
archived. Delta specs merged into the main spec store:

- `openspec/specs/user-credentials/spec.md` (new)
- `openspec/specs/per-user-isolation/spec.md` (new)
- `openspec/specs/market-watchlist/spec.md` (new)
- `openspec/specs/security-invariants/spec.md` (updated — R11/R13/R14 modified,
  R12 preserved; R11–R14 all present)

Archive audit trail: `openspec/changes/archive/2026-10-08-user-data-foundation/`
(explore, proposal, design, specs, tasks, verify-report).

## Traceability — Engram Observation IDs

| Artifact | Observation ID |
|----------|----------------|
| `sdd/user-data-foundation/apply-progress` | 1329 |
| `sdd/user-data-foundation/verify-report` | 1331 |

Proposal/spec/design/tasks have no standalone Engram observations — they live
in the OpenSpec file store (both delta and merged main spec). Merged specs have
no standalone observations either; they live in the OpenSpec file store.
