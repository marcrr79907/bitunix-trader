# Design: persistence-foundation (Ola 3 / F11 / #124)

## Technical Approach

Drawings drop `interval` from key, index, endpoint, and adapter → per **symbol**
(TradingView-style). SMC toggles persist **user-global** on `ChartPreference` via
the existing partial-PUT endpoint. Read-only; no new dep; `window.marketChart`
keeps its 8 frozen keys. First destructive migration in the tree.

## Architecture Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Drawings key | `(user, symbol)` | TradingView semantics; a legacy column/index is dead weight. |
| `0012` ops | `RemoveIndex(old)` → `AlterField(default)` → `RemoveField` → `AddIndex(new)` | SQLite MUST drop the index before the column; the `AlterField(default="1m")` is load-bearing — without it the reverse inserts `NULL` and fails on a populated table. |
| Duplicates | keep ALL, no dedupe | no unique constraint ⇒ nothing collides; dedupe silently destroys data. |
| Reverse | lossy (`interval="1m"` for all) | documented rollback contract. |
| POST `interval` | accept-and-ignore | stale clients/tests live; zero cost. |
| SMC home | `ChartPreference.smc` JSONField | user-global; reuses partial-PUT; a per-chart toggle would reset on the very interval switch this fixes. |
| SMC validation | `parse_smc` (dict, keys ∈ six families, bool values) | frozen vocabulary; thin view; patch-covered. |
| Clear on switch | only on **symbol** change | the bug being fixed. |
| `drawings.js` extract | none | the diff is net-negative; stays ≤300. |

## Data Model

```python
class Drawing(UserOwnedModel):           # interval REMOVED
    class Kind(models.TextChoices): ...  # unchanged
    symbol = models.CharField(max_length=32)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    points = models.JSONField(default=dict)
    style = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=["user", "symbol"],
                                name="ix_drawing_user_symbol")]   # no unique constraint

class ChartPreference(UserOwnedModel):
    ...
    smc = models.JSONField(default=dict)   # {family: bool}; {} ⇒ all ON
```

## Migration `0012_drawing_per_symbol` (+ `0013_chartpreference_smc`)

```
0012  dependencies = [("trading", "0011_chartpreference_theme")]
  RemoveIndex(model_name="drawing", name="ix_drawing_user_sym_interval")  # 28 chars
  AlterField(model_name="drawing", name="interval",
             field=CharField(max_length=8, default="1m"))                 # sets reverse default
  RemoveField(model_name="drawing", name="interval")
  AddIndex(model_name="drawing", fields=["user","symbol"],
           name="ix_drawing_user_symbol")                                 # 22 chars
```

The `AlterField` is **load-bearing** (verified: Django 5.2.18 + SQLite, populated
table): it puts `default="1m"` in state so the auto-reverse re-adds the column WITH
that default; without it the reverse emits `… SELECT …, NULL` and dies on `NOT NULL`
for any existing row. `.sqlmigrate` (verified): forward = `DROP INDEX old` →
rebuilding `AlterField` (rows preserved) → `ALTER TABLE … DROP COLUMN interval` →
`CREATE INDEX new`; reverse rebuilds inserting literal `'1m'` per row. A populated
round-trip keeps both rows forward, all-`"1m"` reverse. Both names ≤30 chars (no
E034); `makemigrations --check` green.```
0013  dependencies = [("trading", "0012_drawing_per_symbol")]
  AddField(model_name="chartpreference", name="smc", JSONField(default=dict))  # additive
```

## Data Flow

    switchTo(sym, int): symbolChanged = sym !== state.symbol
      [symbolChanged] drawings.clearForSwitch() ; smc.clearForSwitch()
      loadLayout ─→ buildChart (re-attach currentDrawings) ─→ [symbolChanged] refreshDrawings() ─→ loadSmc
    boot: loadPreference ─→ smc.applyToggles(pref.smc) ─→ build ─→ refreshDrawings ─→ loadSmc
    toggle → refreshSmc → emit smc:toggles → savePreference({smc}) (debounced PUT)

## Interfaces / Contracts

- **GET `/market/api/drawings?symbol=`**: login-required; `symbol` required → 400;
  `Drawing.for_user(u).filter(symbol=symbol)` **only**; `200 {"symbol","drawings":
  [{id,kind,points,style}]}`, never 404; stray `interval` ignored.
- **POST `/market/api/drawings`**: login + CSRF; validate `symbol` + `parse_drawing`
  BEFORE write (400, no row); `interval` **ignored**; `create(user=request.user,
  symbol, kind, points, style)` → `201 {id,kind,points,style}`. `parse_drawing`
  unchanged.
- **DELETE `<id>`**: unchanged (`for_user` scope, miss → 404).
- **`api_preference` GET/PUT**: body gains `smc`; GET default `smc:{}`; PUT partial
  validates `parse_smc(body["smc"])` → 400/no-write on breach; `_preference_body`
  adds `"smc": pref.smc`.
- **JS**: `createDrawings` URL/body drop `interval`; `refreshDrawings()` →
  `loadDrawings(state.symbol)`. `createSmc` gains `applyToggles(saved)` (sets
  checkbox `checked`, renders, no emit). `main` adds `bus.on("smc:toggles", p =>
  savePreference({smc: p.families}))` + `smc.applyToggles(pref.smc)` at boot.
  `gen` guards and DEBT-8 `stream.subscribe` untouched.

## Testing Strategy

Existing assertions updated as a **sanctioned spec delta** (behavior change, not
regression). New: `parse_smc` matrix; migration asserts `Drawing._meta.indexes ==
{ix_drawing_user_symbol}` and no `interval` field; GET ignores interval; POST stale
interval → 201; SMC PUT partial round-trip; A≠B. E2E: drawing survives an interval
switch (no refetch), cleared+reloaded on symbol switch, SMC toggle survives reload +
interval switch (readiness-gated). Rewritten: `per_interval_drawings` → per-symbol,
`test_switch_clears_then_loads_drawings` → interval-keeps/symbol-clears,
`test_click_with_tool_fires_post` drops the `interval` assert,
`test_drawing_index_and_no_unique_constraint` + interval-keyed isolation tests;
`test_drawing_distinct_intervals_coexist` retired.

## Migration / Rollout

Chained, 2 slices; all slice PRs base on tracker `feat/persistence-foundation`.

| Slice | Scope | Est. |
|---|---|---|
| **S1 — drawings per symbol** | model + `0012` + `api_drawings` + `drawings.js`/`main.js` + tests | 220–280 |
| **S2 — SMC toggles** | `ChartPreference.smc` + `0013` + `parse_smc` + `api_preference` + `smc.js`/`main.js` + tests | 130–170 |

- **S1 rollback**: `migrate trading 0011` runs the lossy reverse; forward never
  destroyed rows. Deliberate, warned revert only.
- **S2 rollback**: revert PR; `0013` additive, zero data loss; independent of S1.
- **Order**: S2 bases on S1 (both touch `main.js`).

Decision needed before apply: Yes
Chained PRs recommended: Yes
400-line budget risk: High (S1 alone approaches budget)

## Guard / Edge Matrix

| Edge | Handling |
|---|---|
| SQLite index-before-column | `0012` removes the index first; `.sqlmigrate` asserted. |
| Non-empty prod drop | keep-all/no-dedupe ⇒ no collision; reverse default via `AlterField`. |
| `drawings.js` 300 ceiling | diff net-negative; `test_module_size_guard` green. |
| `gen` / DEBT-8 | keep guard order; no `stream.subscribe` touch. |
| Seam vocabulary | no new `marketChart` key; 8 keys held. |
| Patch gate 100% | every new branch (interval-ignored, `parse_smc`, migration ops) tested. |

## Open Questions

None blocking. Locked: SMC home = `ChartPreference`; templates → Ola 5;
keep-all/no-dedupe; accept-and-ignore POST `interval`; interval-only switch keeps
drawings and skips the refetch.
