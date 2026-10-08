# Design: user-data-foundation

## Technical Approach

New Django app `trading` owns both user-scoped models behind one ownership deep module.
`UserOwnedModel` (abstract) is the interface — a `user` FK plus `for_user(user)`; scoping is hidden
behind that one classmethod. `ExchangeCredential` reuses `web/credentials.py` unchanged: encrypt at
the model boundary, ciphertext-only columns, no decrypt method. `Watchlist` is the second adapter
that makes the seam real. R14 is enforced by `for_user` at the call site plus a scanner flagging
unscoped `.objects` on owned models in request-serving code. `src/`/`accounts` untouched; order
scanner widened to `web/`+`src/`. Strictly read-only.

## Data Model

```python
class UserOwnedModel(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )
    class Meta:
        abstract = True
    @classmethod
    def for_user(cls, user):          # fail-closed: empty when nothing owned
        return cls.objects.filter(user=user)

class ExchangeCredential(UserOwnedModel):        # R13/R14
    label = models.CharField(max_length=64, blank=True)
    api_key_encrypted = models.TextField()
    api_secret_encrypted = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Watchlist(UserOwnedModel):                 # R14; overrides FK only for related_name
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name="watchlist"
    )
    symbol = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "symbol"], name="uniq_user_symbol")]
```

`Watchlist` redeclares `user` solely to satisfy the spec's `related_name="watchlist"` (the
abstract base cannot interpolate snake_case). FK `related_name` for credentials is
`trading_exchangecredential_set`. FK auto-indexes `user`; no extra indexes (YAGNI).
**Migration**: one additive `web/trading/migrations/0001_initial.py`; `AUTH_USER_MODEL` already set,
no data migration; `makemigrations --check` stays green (CI gate at `ci.yml:61`). Portable fields
only (Postgres prod / SQLite dev agree).

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|----------|--------|--------------|-----------|
| D1 | App placement | New app `trading` | Grow `accounts`; name `portfolio` | `accounts` is identity+invite; mixing ownership in breaks the seam and Phase 3 adds 4 models. `portfolio` misnames credentials/watchlist. Cost: `REQUEST_PATH` must add `trading` or the scanner silently stops protecting it. |
| D2 | R14 mechanism | `for_user` + scanner guard | Contextvar "current user" default manager | A contextvar manager fails **open** when unset → silent cross-tenant leak. `for_user` fails **closed** at the call site; the scanner catches the bypass. Rejected: it needs new machinery and its failure mode is a leak, not an error. |
| D3 | `Watchlist` kept | Stays | Drop (ExchangeCredential alone) | One adapter = hypothetical seam; two make it real and prove R14 generalises past the secret table. Zero new risk, feeds Phase 3. |
| D4 | Masked staff view | Model-level proof only | Minimal masked read view | No UI in Phase 2; a view adds urls/templates/tests for a property that is a *data-access* guarantee, proven at the model seam. Add when UI lands. |

## Secrets Design

    request  → set_secrets(pk, sk) → encrypt → DB (ciphertext)
    worker   → row.api_secret_encrypted → credentials.decrypt → plaintext (trusted zone)
    request  → Watchlist.for_user(u) → owner-scoped rows only

`set_secrets(api_key, api_secret)` is the encryption boundary: reject `not value or not value.strip()`
with `ValueError`, else `self.api_key_encrypted = encrypt(...)`, importing `encrypt` from
`web/credentials.py` (encryption in the request path is permitted by R13.2). The model has **no**
`decrypt_*` method — it would trip the credential scanner and is a real leak surface. Worker code
reads the column and calls `credentials.decrypt(...)` itself; the model stays key-unaware. Key
rotation (`MultiFernet`) stays out of scope.

## Scanner Hardening

**Order scanner** (`tests/web/test_no_order_surface.py`), scope `(WEB, SRC)`:
- Extend `ORDER_VERBS` with `place_tpsl_order`, `place_position_tpsl_order`, `modify_tpsl_order`,
  `modify_position_tpsl_order`, `cancel_tpsl_order`, `change_leverage`, `change_margin_mode`,
  `change_position_mode`, `adjust_position_margin`, `batch_place_order`, `create_market_order`,
  `create_limit_order`.
- `getattr` detection: `ast.Call(func=Name("getattr"), args∋Constant∈ORDER_VERBS)` (mirrors
  `test_credentials_mechanism.py:50`).
- `FORBIDDEN_PATHS` = mutating fragments only: `/trade/{place,batch,cancel,cancel_all,modify,close_all,flash_close}*`,
  `/tpsl/{place,cancel,modify}_order`, `/tpsl/position/{place,modify}_order`,
  `/account/{change_leverage,change_margin_mode,change_position_mode,adjust_position_margin}`;
  flag any `ast.Constant` containing one.
- **Read-path exclusions are by construction**: mutating-only fragments mean `src/client.py` read
  literals (`/trade/get_history_orders`, `/trade/get_history_trades`,
  `/position/get_pending_positions`, bare `/account`) never match. A negative-control test freezes
  these four as non-offenders.
- Self-exclusion: skip this file / `__pycache__`; `tests/` out of scope.

**Credential scanner** (`tests/web/test_credentials_mechanism.py`):
`REQUEST_PATH = (WEB/"config", WEB/"accounts", WEB/"trading")`. `getattr`/wildcard/alias already
covered — not re-fixed.

## ADRs

**(a) `for_user`+scanner vs manager-default-scoping.** See D2 — fail-closed vs fail-open. Stated
limitation: Django has no RLS, so R14 holds only while access routes through `for_user`; the test
proves the mechanism, not every future caller. **(b) App-per-domain vs growing `accounts`.** See D1.
**(c) Model-level R14 proof vs endpoint.** See D4. **(d) `Watchlist` inclusion.** See D3.

## Testing Strategy (Strict TDD, `python -m pytest`)

| Layer | What | Approach |
|-------|------|----------|
| Unit | `for_user(A)` sees A only, empty for B (both models); empty-owner returns `[]`; `for_user(B).get(pk=a.pk)` → `DoesNotExist` | `tests/web/test_isolation.py` (RED first) |
| Unit | Duplicate `(user, symbol)` → `IntegrityError`; same symbol across users persists | same |
| Unit | `set_secrets` ciphertext round-trip: reload raw ≠ plaintext, `decrypt` restores; empty rejects | `test_credentials_mechanism.py` |
| Unit | Scanner negative controls: `getattr` verb + path fragment flagged; four read literals not | `test_no_order_surface.py` |

## Boundary Note

`src/` stays framework-free (`tests/test_boundary.py` green); `web/credentials.py` mechanism
unchanged; `accounts` untouched; `conftest.py` `user_a`/`user_b` reused as-is. **Worker trusted
zone**: `worker.py` may read all users' credentials — that is a trusted-zone read, explicitly not
cross-tenant access (R14.4), so it is exempt from the isolation scanner.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/trading/{__init__,apps,models}.py` | Create | `UserOwnedModel`, `ExchangeCredential`, `Watchlist`, `set_secrets` |
| `web/trading/migrations/0001_initial.py` | Create | Additive schema |
| `web/config/settings/base.py` | Modify | `INSTALLED_APPS += "trading"` |
| `tests/web/test_isolation.py` | Create | R14 A≠B, empty-owner, IntegrityError |
| `tests/web/test_credentials_mechanism.py` | Modify | `REQUEST_PATH` += `trading`; round-trip + empty-guard |
| `tests/web/test_no_order_surface.py` | Modify | verbs + `getattr` + path fragments; scope `web/`+`src/` |
| `src/`, `web/accounts/`, `web/credentials.py` | Unchanged | boundary preserved |

## Task Breakdown Hint

~400–500 lines, High risk > 400 budget → **3 chained PRs** (ask-on-risk, orchestrator confirms):
**PR1** `trading` models + migration + `INSTALLED_APPS` + `test_isolation.py` (~200); **PR2**
`set_secrets` + credential round-trip + `REQUEST_PATH` (~100); **PR3** order-scanner hardening
(~120). Reverted together if R14 later needs a different mechanism.

## Open Questions

None blocking. Resolved here: app = `trading`; R14 = `for_user`+scanner; `Watchlist` stays;
masked view deferred; scanner scope `web/`+`src/` with mutating-only fragments.
