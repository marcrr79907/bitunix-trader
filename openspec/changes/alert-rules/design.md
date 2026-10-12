# Design: alert-rules (issue #76, Fase D1)

## Technical Approach

Split along the existing architectural seam — exactly like B1/B2/C1:

- **Pure engine** `src/alert_rules.py` (joins `PURE_MODULES`): framework-free,
  stdlib-only, imports the frozen `src/smc/*` + `src/indicators` compute chain,
  never reads a clock. Turns a validated `condition` + a window of OHLC rows
  into a `bool` **state** and, over the latest two closed bars, a `bool` **edge**.
- **Django/worker wiring**: `AlertRule(UserOwnedModel)` + additive migration +
  `worker.run_alert_rules()` (trusted-zone unscoped read, R14.4) called as an
  isolated broad-`except` step in `run_once`, mirroring the candle/private steps.

**Edge = Option B** (recomputed, stateless): `edge_fired = matches(-1) and not
matches(-2)`. Deterministic and restart-safe; the fired bar's time is stamped into
`last_fired_at`, which doubles as the dedup key. No extra state field.

Read-only fence: no order/execution path, no `client` in the engine, no new dep.

    Candle (global) ─→ window rows ─→ alert_rules.edge_fired(condition, candles)
                                              │ bool
    AlertRule (owned) ─→ run_alert_rules ─────┤ on true: last_fired_at dedup
                                              └→ on_fired(rule, detail)  → D2

## Architecture Decisions

| Decision | Choice | Alternative | Rationale |
|---|---|---|---|
| Prior-state source | Recomputed over last 2 bars (B) | persisted bool field (A) | stateless, restart-safe, deterministic; honors issue's field list |
| Dedup key | `last_fired_at` == fired bar time | separate `last_state` field | one field is both observable timestamp and idempotency guard |
| `last_fired_at` type | `DateTimeField(null=True)` | `BigIntegerField` epoch | `USE_TZ=True` native aware datetime, admin-readable, ORM-comparable; epoch kept only where it mirrors the exchange (`Candle.time`) |
| Engine unit | `candles: list[dict]` rows | 5 positional OHLC lists | one arg, matches DB/`_db_rows` shape, trivially sliceable by bar index |
| Config errors | `parse_condition` raises `ValueError` | return False | malformed config is a skip-rule signal (worker logs); D2 write-validation owns prevention |
| Data shortfall | returns `False` | raise | warm-up/empty window is expected market state, never an error |
| Uniqueness | none (collection) | unique `(user,symbol,interval)` | a symbol may hold many rules, like `Drawing` |
| Interval set | constrained to `CANDLE_INTERVALS` | any | only persisted closed candles are deterministic; `1m` excluded |
| Read source | DB `Candle` only | DB-first + upstream | worker already persists closed candles; no `client` needed |
| Sink | module-level `on_fired(rule, detail)` | events table / Django Signal | thin D2 seam, YAGNI on persistence |

## Interfaces / Contracts (FROZEN)

```python
# src/alert_rules.py — pure, stdlib-only, no clock
def parse_condition(condition) -> dict:
    """Validate + normalize; raise ValueError on any structural breach."""

def matches(condition: dict, candles: list[dict], *, index: int = -1) -> bool:
    """State at bar ``index`` (negative from the end). Raises ValueError only
    from parse_condition; valid conditions are total (never raise)."""

def edge_fired(condition: dict, candles: list[dict]) -> bool:
    """True iff state flips false->true across the latest two closed bars.
    Fewer than 2 rows -> False (no edge is determinable)."""
```

`candles` rows carry `time` (epoch s), `open`, `high`, `low`, `close`,
`quote_vol` (nullable). `index` slices the window (`-1` = all, `-2` = all but
the last), so `matches(-2)` is the state as of the previous closed bar.

### `condition` schema (frozen) + validation

```jsonc
{"type":"price",     "op":"above"|"below", "level": <number>}
{"type":"indicator", "name":"rsi"|"sma"|"ema"|"atr"|"vwap",
                     "op":"above"|"below", "level": <number>,
                     "params": {"rsi_len":14, "sma_len":20, "ema_len":20, "atr_len":14}}
{"type":"smc_setup", "direction":"long"|"short"|"any", "min_score": <int, default MIN_CONFLUENCE=3>}
```

- `price`: `state = close[-1] > level` / `< level` (strict).
- `indicator`: scalar series only (`rsi/sma/ema/atr/vwap` → `src.indicators`);
  `state = series[-1] > / < level`; `None` (warm-up) ⇒ `False`. Params default
  from the pure-function defaults; the vocabulary reuses the chart registry keys.
- `smc_setup`: run `find_swings → label_swings → find_structure →
  find_order_blocks → find_fvg → dealing_range → find_setups` over the window
  (one pass, same as `get_smc_payload`); `state = any(setup.direction match and
  setup.score >= min_score)`. Empty chain ⇒ `False`.

`parse_condition` raises `ValueError` for: non-object, unknown/missing `type`,
unknown `op`/`name`/`direction`, non-numeric `level`/`min_score`, tuple
indicators (`macd/bollinger/stochastic`) or unknown params. Tuple indicators are
**out of v1 scope** (additive later via a sub-selector key).

## Worker wiring (`web/worker.py`)

The unscoped `AlertRule.objects.filter(is_active=True)` read lives in
`worker.py`, **outside** `REQUEST_PATH` (R14.4, same latitude as
`ExchangeCredential`). Putting it in `web/trading/` would fail the owned-model
guard. `Candle` is global (non-owned) — no guard interaction.

```python
ALERT_CANDLE_WINDOW = 100   # ponytail: >= RANGE_LOOKBACK(50)+swing warm-up+2 bars

def on_fired(rule, detail: dict) -> None:      # frozen D2 seam; D2 re-binds this
    logger.info("alert fired rule=%s user=%s symbol=%s", rule.pk, rule.user_id, rule.symbol)

def run_alert_rules(on_fired_sink=None) -> int:
    # 1. read active rules unscoped; 2. group by (symbol, interval);
    #    skip intervals not in CANDLE_INTERVALS;
    # 3. ONE Candle window per group (newest ALERT_CANDLE_WINDOW, ascending);
    # 4. per rule, own try/except: edge = alert_rules.edge_fired(rule.condition, rows)
    #    on edge -> dedup vs last_fired_at, save(update_fields=["last_fired_at"]), emit
    # 5. return fired count; a failing rule is logged and skipped (peers continue)
```

Dedup (idempotent per bar): `edge_time = rows[-1]["time"]`; fire only when
`rule.last_fired_at is None or int(rule.last_fired_at.timestamp()) < edge_time`;
then `rule.last_fired_at = datetime.fromtimestamp(edge_time, tz=UTC)`.

`run_once` gains one isolated step AFTER private sync; the `(funding, ticker)`
return contract is unchanged:

```python
try:
    n = run_alert_rules()
    logger.info("alert rules ok fired=%d", n)
except Exception as exc:  # ponytail: broad by spec — a rule bug must never kill ticks
    logger.warning("alert rules failed: %s", exc)
```

`detail` (frozen): `{"symbol", "interval", "edge_time": <epoch int>,
"condition": <rule JSON>}`.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/alert_rules.py` | Create | pure engine: `parse_condition`, `matches`, `edge_fired` |
| `tests/test_alert_rules.py` | Create | engine edge battery + clock-free guard |
| `web/trading/models.py` | Modify | `+ AlertRule(UserOwnedModel)` |
| `web/trading/migrations/0007_alertrule.py` | Create | additive (depends 0006) |
| `web/worker.py` | Modify | `+ run_alert_rules`, `on_fired`, `run_once` step |
| `tests/web/test_worker_alerts.py` | Create | seeded-candle integration + isolation |
| `tests/test_boundary.py` | Modify | `PURE_MODULES += "alert_rules.py"` |
| `tests/web/test_owned_model_guard.py` | Modify | `OWNED_MODELS += AlertRule` + cases |
| `tests/web/test_isolation.py` | Modify | `AlertRule` A≠B + collection + owner |
| `openspec/changes/alert-rules/specs/per-user-isolation/` | Create | R14.2/R14.3 delta (`AlertRule`) |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit — engine | price/indicator/smc_setup fire + no-fire; strict ops; warm-up `None`→False; unknown type/op/name raises; short/empty/mismatched→False; `index` slicing; edge false→true fires, true→true/true→false do not; <2 bars→False; same input→identical output; no `time`/`datetime`/`random` import | literal OHLC fixtures, `assert`-style (mirror `test_alerts.py` + SMC matrices) |
| Integration — worker | `django_db` seeded `Candle`; fires once per edge; same bar twice = one fire; bad-condition rule logged+skipped, peers continue; `run_once` `(funding,ticker)` preserved; `on_fired` called once; unscoped read across users | mirror `test_worker_private_sync`/`test_worker_candles` |
| Boundary/guard | no Django in `src/`; pure stdlib; `AlertRule` in `OWNED_MODELS`; cross-user deny | extend `test_boundary`/`test_owned_model_guard`/`test_isolation` |

`strict_tdd: true` — RED before GREEN; patch 100%; `ruff` clean. No E2E (no UI);
worker integration covers the only user-visible behavior.

## Guard / Edge Matrix

| Guard / Edge | Handling |
|---|---|
| `PURE_MODULES` | `alert_rules.py` added; stdlib-only enforced |
| Clock-free determinism | no `time`/`datetime`/`random` in engine; explicit test |
| `OWNED_MODELS` | `AlertRule` added; request-path unscoped query flagged |
| R14.4 unscoped read | only in `web/worker.py`; never in `web/trading/` |
| Dedup | `last_fired_at.timestamp() >= edge_time` → skip; same bar = one fire |
| Per-rule isolation | own `try/except Exception`; one bad rule never aborts peers |
| Rule isolation from loop | `run_once` broad-`except`; ticks/private unaffected |
| Empty / short window | `matches` → `False`; `edge_fired` needs 2 bars → `False` |
| Indicator warm-up `None` | `False`, never raise |
| Bad condition config | `parse_condition` raises → worker logs + skips rule |
| Unknown interval (`1m`) | skipped before evaluation |
| Read-only fence | no order/execution/`client` in engine; R11 scanner stays clean |

## Delivery — Chained 3 slices (Feature Branch Chain)

Base = `feat/alert-rules` tracker; each child PR targets the **immediate previous
slice**; retarget/rebase if a child diff shows prior slices. ~830 lines total →
`400-line budget risk: High`. `Decision needed before apply: Yes` ·
`Chained PRs recommended: Yes`.

| Slice | Content | ~Lines | Depends on | Rollback boundary |
|---|---|---|---|---|
| 1 — model + guard | `AlertRule` + `migrations/0007` + `OWNED_MODELS` + `test_isolation` + per-user-isolation delta | ~200 | — | drop migration row + `AlertRule`, revert `OWNED_MODELS`/isolation tests |
| 2 — pure engine | `src/alert_rules.py` + `PURE_MODULES` + `tests/test_alert_rules.py` | ~410 | frozen `src/smc`/`src/indicators` only | delete module + tests, revert one `PURE_MODULES` line |
| 3 — worker wiring | `run_alert_rules` + `on_fired` + `run_once` step + `tests/web/test_worker_alerts.py` | ~220 | slices 1 & 2 | revert `worker.py` hunks, delete worker tests |

Slices 1 and 2 share no code (model vs pure engine) and are independently
verifiable; slice 3 is the only dependent one. Slice 2 alone is at the ~400
budget edge; if the reviewer prefers, split its test battery.

## Migration / Rollout

Additive, no destructive data. `0007_alertrule` creates one table; `last_fired_at`
nullable. Inert until `run_once` calls the step. `USE_TZ=True`/`TIME_ZONE="UTC"` —
`fromtimestamp(edge_time, tz=UTC)` is the only conversion. No backfill.

## Resolved Decisions / Open Questions

- **Q-EDGE** → B (recomputed edge). **Q-LASTFIRED** → `DateTimeField(null=True)`,
  holds the edge bar time, doubles as dedup key. **Q-COND/Q-COND2** → three types,
  scalar indicators only. **Q-INTERVAL** → `CANDLE_INTERVALS`. **Q-CAD** → every
  cycle (dedup makes it idempotent). **Q-FIRED** → `on_fired` seam, no events
  table. **Q-UNIQUE** → none; index `(user, is_active)`.
- **Open**: `ALERT_CANDLE_WINDOW=100` is a conservative constant; revisit only if
  a condition needs deeper context. No blocking questions.
