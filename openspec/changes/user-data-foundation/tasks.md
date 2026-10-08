# Tasks: user-data-foundation

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Guard/Edge Matrix (every row = a test in its WU)

- [ ] Ciphertext-at-rest: raw column ≠ plaintext (R13.1)
- [ ] Round-trip: `credentials.decrypt(raw)` restores key/secret (R13.1)
- [ ] Empty/whitespace `set_secrets` → raises, no row (R13.3)
- [ ] No plaintext accessor on `ExchangeCredential` (R13.3)
- [ ] `for_user(A)` owner-only, `for_user(B)` empty (R14.1, both models)
- [ ] `for_user(B).get(pk=A_row)` → `DoesNotExist` (R14.2, both models)
- [ ] Empty owner → `[]`, no raise (R14.1)
- [ ] Duplicate `(user, symbol)` → `IntegrityError` (R14.6)
- [ ] Same symbol across users persists (R14.6)
- [ ] Request-path decrypt fixture → credential scanner catches (R13.2)
- [ ] `getattr(client, "place_order")` → order scanner catches (R11)
- [ ] Mutating path string → scanner catches (R11)
- [ ] Four read literals → scanner does NOT match (R11)
- [ ] `makemigrations --check` green
- [ ] `tests/test_boundary.py` green (`src/` framework-free)

## WU1 (PR1) — `trading` app: owned models + migration

Base `feat/user-data-foundation` (tracker). Depends: none. Strict TDD.

- [ ] 1.1 **RED** `tests/web/test_isolation.py`: A≠B (both models), empty-owner → `[]`, cross-user `.get()` → `DoesNotExist`.
- [ ] 1.2 **RED** same file: duplicate `(user, symbol)` → `IntegrityError`; same symbol across users persists.
- [ ] 1.3 **GREEN** `web/trading/{__init__,apps,models}.py`: abstract `UserOwnedModel` (`user` FK CASCADE, `for_user`) + `ExchangeCredential` + `Watchlist` (`related_name="watchlist"`, `UniqueConstraint`).
- [ ] 1.4 **GREEN** `web/config/settings/base.py`: `INSTALLED_APPS += "trading"`.
- [ ] 1.5 **GREEN** `web/trading/migrations/0001_initial.py` additive; `makemigrations --check` green.
- [ ] 1.6 Full suite + ruff green.
- [ ] 1.7 **Rollback**: delete `web/trading/`, revert `INSTALLED_APPS`, delete `test_isolation.py`.

## WU2 (PR2) — `set_secrets` boundary + credential scanner scope

Base WU1 branch. Depends: WU1. Strict TDD.

- [ ] 2.1 **RED** `test_credentials_mechanism.py`: save via `set_secrets` → raw column ciphertext; `decrypt` restores; empty/whitespace raises.
- [ ] 2.2 **RED** same file: no plaintext accessor on `ExchangeCredential`.
- [ ] 2.3 **GREEN** `set_secrets(api_key, api_secret)`: reject `not value or not value.strip()`; else `encrypt` from `web/credentials.py`; no `decrypt_*` method.
- [ ] 2.4 **GREEN** `REQUEST_PATH += WEB/"trading"`.
- [ ] 2.5 Full suite + ruff green.
- [ ] 2.6 **Rollback**: revert `set_secrets` + `REQUEST_PATH`; WU1 models stay.

## WU3 (PR3) — order-scanner hardening

Base WU2 branch. Depends: WU2. Strict TDD. Scope `(WEB, SRC)`.

- [ ] 3.1 **RED** `test_no_order_surface.py`: `place_tpsl_order`/`change_leverage`/`adjust_position_margin` flagged.
- [ ] 3.2 **RED** `getattr(client, "place_order")` flagged; `/trade/place_order` + `/tpsl/*` + `/account/change_*` strings flagged.
- [ ] 3.3 **RED** negative controls: `/trade/get_history_orders`, `/trade/get_history_trades`, `/position/get_pending_positions`, bare `/account` NOT flagged.
- [ ] 3.4 **GREEN** extend `ORDER_VERBS` (12 verbs); add `getattr`-Constant + mutating-only `FORBIDDEN_PATHS` Constant detection.
- [ ] 3.5 **GREEN** scope `_order_offenders` to `web/`+`src/`; self-exclude test file/`__pycache__`.
- [ ] 3.6 Full suite + `test_boundary.py` + ruff green.
- [ ] 3.7 **Rollback**: restore `test_no_order_surface.py`; `src/`/CLI untouched.

## Phase 4 — Verification

- [ ] 4.1 `python -m pytest` green under Strict TDD.
- [ ] 4.2 `ruff check . && ruff format --check .` + `makemigrations --check` green.
- [ ] 4.3 No order-execution surface; no new runtime dependency.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | WU1 ~200, WU2 ~100, WU3 ~120 → ~420–500 total |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 (each targets prior branch) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |
| Tracker branch | `feat/user-data-foundation` → merges to `develop` |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High
