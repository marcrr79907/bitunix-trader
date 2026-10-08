# Exploration: user-data-foundation (Phase 2)

**Change**: `user-data-foundation`
**Date**: 2026-10-07
**Mode**: investigation only. No code written.

## Executive Summary

Phase 2 makes the Phase-0 security *mechanisms* real: it stores per-user
exchange credentials as Fernet ciphertext (R13) and flips the Phase-0
`user_a`/`user_b` isolation harness from "ready" to "enforced" (R14). The lazy,
evidence-backed slice is **two owned models** — `ExchangeCredential` and
`Watchlist` — behind one small ownership contract (deep module), plus migration,
encryption wiring, and scanner hardening. `AlertRule`, `Trade`,
`PositionSnapshot`, `AccountSnapshot` need ingestion/worker/alerts that do not
exist yet (worker is a boot-only stub) → Phase 3+.

Two carry-forward findings were re-verified and one is **stale**: the Fernet
confinement scanner already catches `getattr`/wildcard/alias (commit `c9f89df`);
the order scanner still does not catch `getattr` or endpoint-path strings.

---

## Current State (read, not guessed)

| Area | Fact | Source |
|---|---|---|
| Core CLI | Flat `src/` modules; `src/db.py` defines SQLite `funding_snapshots`, `price_snapshots`, `trades` (global, no user) | `src/db.py:11-46` |
| Core client | Read-only. Private methods: `positions`, `account`, `history_trades`, `history_orders` — no order calls | `src/client.py:126-152` |
| Django app | Single app `accounts` holds `User` (email id, `role` member/admin) + `Invite` | `web/accounts/models.py:31-72` |
| AUTH_USER_MODEL | `accounts.User`, migrations 0001/0002 exist | `web/config/settings/base.py:75`, `web/accounts/migrations/*.py` |
| Fernet | `web/credentials.py`: `encrypt`/`decrypt`, key from `CREDENTIALS_FERNET_KEY`, fail-closed. **No model persists anything yet** | `web/credentials.py:18-32` |
| Worker zone | `worker.py`/`scheduler.py` ping Redis then idle — no credential use | `web/worker.py:22-44`, `web/scheduler.py` |
| Isolation harness | `user_a`/`user_b` fixtures exist; comment says no owned rows yet | `tests/web/conftest.py:1-27` |
| Order scanner | `ORDER_VERBS` (11 verbs) via `ast.Attribute`/`ast.Name` only — no `getattr`, no path strings, scans `web/` only | `tests/web/test_no_order_surface.py:15-49` |
| Fernet scanner | Reaches `decrypt` via import, attribute, bare name, **and `getattr`**; `REQUEST_PATH = (web/config, web/accounts)` | `tests/web/test_credentials_mechanism.py:20,31-62` |
| No per-user data models exist | grep for `Watchlist|ExchangeCredential|AlertRule|PositionSnapshot|AccountSnapshot` → none | repo-wide |

**Verified probe** (in `/tmp`, no repo writes): `client.post("/api/v1/futures/trade/place_order", body)` and `getattr(client, "place_order")(...)` are **missed** by the order scanner. `from credentials import *; decrypt(t)`, `getattr(credentials,"decrypt")(t)`, and aliased import are **caught** by the credential scanner.

---

## 1. Models in Phase 2 vs later

### Recommendation: two owned models now

**`ExchangeCredential`** (owning reqs: **R13** storage + **R14** isolation)
- `user` → `AUTH_USER_MODEL`, `on_delete=CASCADE`, `related_name="exchange_credentials"`
- `label` `CharField(max_length=64, blank=True)` — human name ("Main", "Hedge")
- `api_key_encrypted` `TextField` — Fernet ciphertext (never plaintext)
- `api_secret_encrypted` `TextField` — Fernet ciphertext
- `is_active` `BooleanField(default=True)`
- `created_at` `auto_now_add`, `updated_at` `auto_now`
- index on `user` (FK gives it automatically)

**`Watchlist`** (owning req: **R14**; recommended, droppable)
- `user` → `AUTH_USER_MODEL`, `CASCADE`, `related_name="watchlist"`
- `symbol` `CharField(max_length=32)` (e.g. `BTCUSDT`, `1000PEPEUSDT`)
- `created_at` `auto_now_add`
- `UniqueConstraint(user, symbol)`

**Why two, not fewer/more** (codebase-design: *one adapter = hypothetical seam, two = real*): the ownership contract is a deep module — small interface (`for_user(user)` / FK to owner), hidden scoping. A single model makes the pattern hypothetical; two concrete models justify it and prove R14 generalises beyond the secret table. `Watchlist` is the next phase's input with zero added risk; `ExchangeCredential` alone is the true minimum if scope must shrink.

### Must wait (Phase 3+)
| Model | Blocked by |
|---|---|
| `PositionSnapshot`, `AccountSnapshot`, `Trade` | No ingestion. Worker is a boot-only stub (`web/worker.py`); `src/monitor.py`+`src/client.py` poll, but nothing persists per-user. Reusing the name `Trade` also risks confusion with `src/db.py` `trades` (different DB). |
| `AlertRule` | No alert semantics/notifier; `src/alerts.py` is CLI-only, untouched by web. |
| Global `Candle`/`FundingSnapshot`/`TickerSnapshot` | Out of scope by decision. |

> App placement: `accounts` is currently identity+invite (`web/accounts/models.py`). Put the per-user data models in **one new app** (e.g. `trading`, name TBD in design) rather than growing `accounts` — Phase 3 adds 4 more models, so a data app is justified now. **Consequence:** the credential scanner's `REQUEST_PATH` (below) must be extended to include it, or it silently stops protecting the new code.

---

## 2. Fernet design (R13)

Current mechanism (`web/credentials.py`) has no persistence. Proposed seam:

- **Ciphertext lives in the DB**: `ExchangeCredential.api_key_encrypted` / `api_secret_encrypted` as `TextField`. Fernet tokens for short secrets are ~150–250 chars → `TextField` avoids per-field `max_length` guesswork.
- **Encrypt at the boundary**: a model/boundary `set_secrets(api_key, api_secret)` calls `credentials.encrypt`. Encryption in the request path is **allowed** — R13 forbids only *decryption* there (`security-invariants/spec.md` R13).
- **Decrypt stays worker-only**: callers do `credentials.decrypt(cred.api_secret_encrypted)` from worker code. Do **not** put a `decrypt_*` method on the model if the model lives in a request-serving app — the scanner would flag it (and it would be a real leak surface).
- **Model stays dumb**: the model stores ciphertext; it does not know the key.

**Gaps to close**
1. No persistence, no round-trip-through-DB test. Add: save → reload raw → assert not plaintext → `credentials.decrypt` restores (worker zone).
2. `decrypt` confinement is *convention + scanner only*; there is no structural worker boundary. Keep the scanner approach (lazy) and extend `REQUEST_PATH`.
3. Key rotation: `_fernet()` reads a single key. Rotating `CREDENTIALS_FERNET_KEY` makes all ciphertext undecryptable (already warned in `.env.example`). `MultiFernet` rotation is **out of scope** unless the design decides otherwise (open question).
4. Default `TextField` allows accidental plaintext writes — consider a tiny guard in `set_secrets` (assert non-empty, strip) and never expose a plaintext field.

---

## 3. R14 isolation enforcement (what flips the harness)

**What flips**: Phase 0 has fixtures but no owned rows (`tests/web/conftest.py:3-4`). "Enforced" = owned rows exist AND every read routes through an owner-scoped accessor that makes cross-user reads fail.

**Mechanism**: a small ownership contract — either an abstract `UserOwnedModel` (FK `user` + `for_user(user)` queryset) shared by both models, or per-model managers with the same method. Interface is one method (`for_user`); implementation hides scoping. This is the deep module.

**Concrete tests** (Strict TDD, new `tests/web/test_isolation.py`), using existing `user_a`/`user_b`:
- `Watchlist.objects.create(user=user_a, symbol="BTCUSDT")` → `for_user(user_a)` sees 1, `for_user(user_b)` sees 0.
- `ExchangeCredential` owned by A → `for_user(user_b).get(pk=a.pk)` raises `DoesNotExist`; same for Watchlist.
- Negative/guard: assert both models' default manager is owner-scoped (or that a scanner forbids unscoped `.objects.all()/.get()` on owned models in request-serving code).

**Honest limitation (must be stated in the proposal)**: Django has no row-level security. R14 "denied" holds only if all access uses the scoped accessor. The test proves the mechanism; it does not prove every future caller uses it. A guard (manager default-scoping or a scanner) is the real enforcement — decide in design. The **worker** legitimately reads *all* users' credentials; that is a trusted zone, not a cross-tenant user read — define this boundary explicitly.

---

## 4. Scanner hardening (exact)

Evidence: `FuturesPath.java` (BitunixOfficial/open-api) lists the real paths. Mutating endpoints:
`/trade/place_order`, `/trade/batch_order`, `/trade/cancel_all_orders`, `/trade/cancel_orders`, `/trade/modify_order`, `/trade/close_all_position`, `/trade/flash_close_position`, `/tpsl/place_order`, `/tpsl/cancel_order`, `/tpsl/modify_order`, `/tpsl/position/place_order`, `/tpsl/position/modify_order`, `/account/change_leverage`, `/account/change_margin_mode`, `/account/change_position_mode`, `/account/adjust_position_margin`.
Read endpoints (must NOT match): `/trade/get_history_orders`, `/trade/get_history_trades`, `/trade/get_order_detail`, `/trade/get_pending_orders`, `/position/get_*`, `/account`, `/account/get_leverage_margin_mode`.

### Order scanner (`tests/web/test_no_order_surface.py`)
1. **Extend `ORDER_VERBS`** with tpsl/account write verbs: `place_tpsl_order`, `place_position_tpsl_order`, `modify_tpsl_order`, `modify_position_tpsl_order`, `cancel_tpsl_order`, `change_leverage`, `change_margin_mode`, `change_position_mode`, `adjust_position_margin`, `batch_place_order`, `create_market_order`, `create_limit_order`. (Current set lacks `create_market_order`/`create_limit_order`; current set *does* already include `create_order`/`submit_order`/`modify_order`/`cancel_all_orders`, so the archive's WARNING-1 verb list is partly stale.)
2. **`getattr` blind spot**: flag `ast.Call(getattr, (x, Constant("verb")))` exactly as the credential scanner already does (`test_credentials_mechanism.py:50-58`). Probe-confirmed missed today.
3. **Path-string blind spot (strongest fix)**: flag `ast.Constant` strings containing a forbidden mutating endpoint fragment from the list above. Probe-confirmed `client.post("/api/v1/futures/trade/place_order", …)` is missed today.
4. **Scope**: consider scanning `web/` **and** `src/` (the invariant covers "the system"); exclude this scanner file itself (it contains the verb strings as data) and `tests/`.

### Fernet confinement scanner (`tests/web/test_credentials_mechanism.py`)
- `getattr`, wildcard-import bare call, and aliased import are **already handled** (`:41-58`, probe-confirmed) — the archive's WARNING-2 is stale; do not re-fix.
- **Real gap**: `REQUEST_PATH = (WEB/"config", WEB/"accounts")` (`:20`). When the new data app lands, add it (e.g. `WEB/"trading"`), or decryption in the new app's request-serving views goes unscanned.
- Optional: also flag a request-path import of the worker-zone module's `decrypt` re-exported elsewhere.

---

## 5. Migration strategy

- `AUTH_USER_MODEL = "accounts.User"` is already set with committed 0001/0002 — **no data migration** needed; Phase 2 is purely additive (new tables) → new app migrations.
- FKs to `settings.AUTH_USER_MODEL` emit the correct dependency automatically; no hand-written dependency needed.
- **CI gate**: `python web/manage.py makemigrations --check --dry-run` runs in `ci.yml`. Every new model MUST ship a committed migration or CI fails. Lock the schema in the design before apply.
- Portable fields only (`TextField`, `CharField`, `UniqueConstraint`, FK) so Postgres (prod) and SQLite (dev/tests) agree.
- `web/db.sqlite3` is gitignored and empty; dev/tests build from migrations — no drift.
- Risk: later field edits each need a migration. Keep `ExchangeCredential` fields minimal and stable.

---

## 6. Scope boundaries

**In**
- New app with `ExchangeCredential` + `Watchlist` behind one ownership contract; migrations.
- Fernet-backed ciphertext storage (`api_key_encrypted`/`api_secret_encrypted`), encrypt-at-boundary, decrypt worker-only.
- R14 enforcement: owner-scoped accessor + `tests/web/test_isolation.py` (flips `user_a`/`user_b` red→green).
- Scanner hardening: order scanner (verbs + `getattr` + path strings), credential scanner (`REQUEST_PATH` extended to the new app).
- Tests under Strict TDD; `python -m pytest` green; ruff clean.

**Out (Phase 3+)**
- `AlertRule`, `Trade`, `PositionSnapshot`, `AccountSnapshot` and global market snapshots (need ingestion/worker/alerts).
- Worker sync loop, JSON API/DRF, alerts/notifications.
- Any UI for managing credentials/watchlist (unless design decides a minimal masked read view is needed to make R14 an end-to-end test).
- Order execution — HARD invariant, never.
- Fernet key rotation (`MultiFernet`).

---

## 7. Risks & open questions

| # | Risk / question | Note |
|---|---|---|
| R1 | **R14 is mechanism, not kernel-enforced.** Django lacks row-level security; "denied" holds only if all access uses `for_user`. | Decide manager-default-scoping vs scanner guard. State the limitation in the proposal. |
| R2 | **New app desyncs the credential scanner.** If `REQUEST_PATH` isn't extended, decryption in the new app's request views is unscanned. | Must be a task in apply. |
| R3 | **Worker vs R14 boundary.** Worker reads all users' credentials by design. | Define trusted-zone boundary explicitly so it is not mistaken for cross-tenant access. |
| R4 | **App name / placement** (`trading` vs `portfolio` vs grow `accounts`). | Design decision; affects R2 and migration names. |
| R5 | **Order-scanner scope** (`web/` only vs `web/`+`src/`) and read-path false positives (`get_history_orders`). | Prefer precise mutating-path fragments over bare `order` matching. |
| R6 | **Fernet key rotation** unhandled; rotating the env key bricks all ciphertext. | Document; decide if MultiFernet is in scope. |
| R7 | **`Watchlist` is arguably YAGNI** for a pure "foundation" phase. | Keep as recommended-but-droppable; `ExchangeCredential` alone satisfies R13+R14. |
| R8 | **Encryption seam** — model method vs service. A model `decrypt_*` in a request app would trip the scanner. | Keep model ciphertext-only; decrypt in worker code. |
| R9 | **Plaintext write footgun** — `TextField` accepts plaintext silently. | Add a minimal guard in `set_secrets`; test that persisted values are ciphertext. |
| R10 | **UI or not** — R14 "A attempts to read B's data" is more meaningful with an endpoint, but Phase 2 is foundation. | Design decision; model-level test is the lazy default. |

---

## Affected Areas

- `web/<new-app>/models.py`, `migrations/`, `apps.py` — new owned models (create)
- `web/config/settings/base.py` — add app to `INSTALLED_APPS`
- `web/credentials.py` — unchanged mechanism; used by new boundary code
- `tests/web/test_isolation.py` — new R14 enforcement (create)
- `tests/web/test_credentials_mechanism.py` — `REQUEST_PATH` extension + DB round-trip test (modify)
- `tests/web/test_no_order_surface.py` — verbs + `getattr` + path strings (modify)
- `tests/web/conftest.py` — `user_a`/`user_b` reused as-is

## Recommendation

Proceed to **proposal → spec → design** with In-scope = {`ExchangeCredential`, `Watchlist`} behind one ownership contract, Fernet ciphertext storage, R14 enforcement tests, and the two scanner hardenings. Resolve the app-name/scope and R14-enforcement-mechanism questions in design.

## Ready for Proposal

**Yes** — with two decisions to settle in design: (a) app name/placement, (b) whether R14 enforcement is manager-default-scoping or scanner-guarded, and whether `Watchlist` stays in.
