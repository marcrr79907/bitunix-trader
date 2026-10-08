# Proposal: user-data-foundation

## Intent

Phase 0 shipped the R13/R14 *mechanisms* but persisted no data. Phase 2 makes R13 real (per-user exchange secrets as Fernet ciphertext) and flips R14 from "harness ready" to "enforced" (A cannot read B's rows). Strictly read-only: **no order execution, ever.**

## Scope

### In Scope
- New app (`trading` suggested) with TWO owned models behind ONE contract:
  - `ExchangeCredential` (R13+R14): `user` FK, `label`, `api_key_encrypted`/`api_secret_encrypted` `TextField`, `is_active`, timestamps. Ciphertext-only.
  - `Watchlist` (R14): `user` FK, `symbol`, `created_at`, `UniqueConstraint(user, symbol)`.
- Ownership deep module: abstract `UserOwnedModel` (FK `user`) + `for_user(user)` accessor.
- Migration + `INSTALLED_APPS`; `makemigrations --check` green.
- `tests/web/test_isolation.py` flipping the Phase-0 harness red→green (A≠B).
- R13 round-trip: save → raw DB value is ciphertext → `credentials.decrypt` restores (worker zone).
- Scanner hardening: order scanner = tpsl/account verbs + `getattr` + forbidden path strings, scanning `web/` **and** `src/`; credential scanner `REQUEST_PATH` += new app.

### Out of Scope
- `AlertRule`, `Trade`, `PositionSnapshot`, `AccountSnapshot`, global market snapshots.
- Worker sync loop, JSON API/DRF, UI, alerts, `MultiFernet` rotation.
- **Any order execution — HARD invariant.**

## Capabilities

### New Capabilities
- `user-credentials`: Fernet ciphertext storage, encrypt-at-boundary, decrypt worker-only.
- `per-user-isolation`: `UserOwnedModel` + `for_user`; cross-user denial.
- `market-watchlist`: per-user symbol list (second owned model proving the seam).

### Modified Capabilities
- `security-invariants`: R13/R14 go from stated constraint to enforced + scanned (delta).

## Approach

One app holds both models under one abstract `UserOwnedModel` (`user` FK + `for_user`): small interface, hidden scoping — the deep module. Two concrete models make the seam real. Credentials reuse `web/credentials.py` unchanged: encrypt at boundary, model ciphertext-only, decrypt worker-only. `src/`/`accounts` untouched.

**R14 direction (design decides):** recommend **`for_user` + scanner guard over manager-default-scoping**. A contextvar "current user" manager fails *open* when unset (silent cross-tenant leak); `for_user` fails *closed* at the call site and the scanner catches unscoped `.objects` on owned models. Honest limitation: Django has no RLS — R14 holds only while all access routes through `for_user`; the test proves the mechanism, not every caller.

**Worker boundary:** the worker legitimately reads ALL users' credentials (trusted zone) — not cross-tenant access.

**Reuse vs New**: REUSED — `src/*`, `accounts`, `credentials.py`. NEW — `web/trading/`, `tests/web/test_isolation.py`, scanner hardening.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/{models.py,apps.py,migrations/}` | New | `UserOwnedModel`, `ExchangeCredential`, `Watchlist` |
| `web/config/settings/base.py` | Modified | add app to `INSTALLED_APPS` |
| `tests/web/test_isolation.py` | New | R14 A≠B enforcement |
| `tests/web/test_credentials_mechanism.py` | Modified | `REQUEST_PATH` += new app; DB round-trip |
| `tests/web/test_no_order_surface.py` | Modified | verbs + `getattr` + path strings; `web/`+`src/` |
| `src/`, `web/accounts/`, `web/credentials.py` | Unchanged | boundary preserved |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| R14 is mechanism, not kernel (no RLS) | Med | `for_user` + scanner guard; limitation stated |
| New app desyncs credential scanner | Med | Extend `REQUEST_PATH` (explicit task) |
| Plaintext write into `TextField` | Low | `set_secrets` guard + ciphertext round-trip test |
| Scanner false positives on read paths | Low | Match precise mutating fragments, not bare `order` |
| App-name churn after apply | Low | Settle name in design before apply |

## Rollback Plan

Revert the branch: delete `web/trading/` (+ migration), remove the `INSTALLED_APPS` line, delete `test_isolation.py`, restore the two scanner test files. `src/`, `accounts`, CLI and `credentials.py` stay untouched, so `main` still ships a working read-only CLI and the Phase-0 suite stays green.

## Dependencies

- `CREDENTIALS_FERNET_KEY` present in env (existing Phase-0 contract).

## Open Questions

- App name: `trading` vs `portfolio`? (recommend `trading`.)
- R14: `for_user`+scanner (recommended) vs manager-default-scoping?
- `Watchlist` stays? (recommend stays — second model makes the seam real.)
- Minimal masked staff read view, or model-level R14 proof only? (recommend model-level + scanner.)

## Success Criteria

- [ ] `python -m pytest` green under Strict TDD; isolation + round-trip tests pass.
- [ ] `ruff check . && ruff format --check .` green; `makemigrations --check` green.
- [ ] R14: A cannot read B's rows for BOTH models.
- [ ] Persisted credential values are ciphertext; `decrypt` restores in the worker zone.
- [ ] Scanners catch `getattr` and path-string order calls across `web/`+`src/`.
- [ ] No order-execution surface; no new runtime dependency.

## Review Workload Forecast

- Estimated diff: **~400–500 changed lines** (models + migration + isolation/round-trip tests + two scanner hardenings).
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High
