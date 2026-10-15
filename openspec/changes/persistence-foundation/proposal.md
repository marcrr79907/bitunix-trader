# Proposal: persistence-foundation

## Intent

Two persistence seams are inconsistent before F4 (drawing-interaction) lands.
`Drawing` is keyed `(user, symbol, interval)`, so drawings vanish on every
interval change — not TradingView-style. SMC toggles are session-only and reset
on reload. Fix both before F4 pays migration + rework. Carries the **first
destructive migration** in the tree (a real data migration on prod).

## Scope

### In Scope
- Drawings **per symbol**: `Drawing` key drops `interval`; index `(user, symbol)`;
  migration `0012`; GET filters `(user, symbol)`; POST accept-and-ignores
  `interval`; JS loads per symbol, clears on SYMBOL change only.
- SMC toggles user-global on `ChartPreference` (`smc` JSONField, migration `0013`)
  + partial-PUT + boot restore.

### Out of Scope
- `LayoutTemplate` / templates → **Ola 5** (no UI consumer = dead data).
- Symbol search; per-interval SMC; order execution (HARD); new runtime deps; CSP
  relaxation; `src/` framework-free boundary unchanged.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `chart-drawings`: key drops `interval` → `(user, symbol)`; GET/POST contract; adapter clears on symbol only.
- `smc-overlay`: R7 **inverts** — toggles MUST persist; "not persisted" scenario replaced.
- `chart-config`: `ChartPreference` gains `smc`; R9 preference API carries it end-to-end.
- `per-user-isolation`: R14.2 Drawing index evidence moves to `(user, symbol)`.

## Approach

**Drawings**: DROP `interval` (no legacy-ignored column). `0012` order matters on
SQLite — `RemoveIndex(ix_drawing_user_sym_interval)` → `RemoveField(interval)` →
`AddIndex((user, symbol))`. **Keep ALL rows, no dedupe**: no unique constraint means
nothing collides; dedupe would silently destroy user data. No `RunPython` (the drop
*is* the merge). **Reverse is lossy** — re-adds `interval="1m"` for every row.

**SMC**: reuse the existing user-global `ChartPreference` partial-PUT verbatim —
per-interval toggles would reset on the exact interval switch this change fixes.
`smc.js` reads/writes `state.smc`; `main.js` boot restores. No new dep.## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/models.py` | Modified | `Drawing` drop `interval`+index; `ChartPreference.smc` |
| `web/trading/migrations/0012_drawing_per_symbol.py` | New | destructive (first in tree) |
| `web/trading/migrations/0013_chartpreference_smc.py` | New | additive |
| `web/market/views.py` | Modified | `api_drawings` GET/POST; `api_preference` `smc` |
| `.../controllers/drawings.js` | Modified | per-symbol load; **at 300-line ceiling** |
| `web/market/templates/market/main.js` | Modified | `switchTo` clears on symbol only; boot; **touches `gen` + DEBT-8** |
| `.../controllers/smc.js` | Modified | persist/restore toggles |
| `tests/web/*.py` | Modified | drawings-interval assertions are a **spec delta, not a regression** |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Destructive migration on non-empty prod | **High** | no-dedupe (nothing collides); index-before-column order; `makemigrations --check` green |
| Lossy reverse (per-interval split unrecoverable) | **High** | documented rollback contract; archive "warn before destructive deltas" |
| First `RemoveField` in tree — no precedent | Med | hand-written, SQLite-order-tested |
| `drawings.js` at 300-line ceiling | High | net additions offset / kept in `main.js` (256) |
| `main.js::switchTo` regresses `gen` guard / DEBT-8 | Med | preserve guard ordering; no `stream.subscribe` touch |
| Frozen 8-key `window.marketChart` seam | Med | no new key; vocabulary frozen |
| Patch coverage 100% (`diff-cover`) | High | every migration op + endpoint branch exercised |

## Rollback Plan

- **S2 (SMC)**: revert PR — drop `0013`, remove `smc` field + endpoint + `smc.js`
  writes. Additive; zero data loss.
- **S1 (drawings)**: `migrate trading 0011` runs the **lossy** reverse (re-add
  `interval` default `1m`) — original per-interval split is NOT recoverable.
  Forward path never destroyed rows (keep-all). Rollback MUST be a deliberate,
  warned decision, never an accident; each chained PR is independently revertible.

## Dependencies

- `chart-drawings` (A3) merged: `Drawing`, `0006`, `api_drawings`, JS adapter.
- `chart-config` (A2) / `chart-theme` / `chart-scales`: `ChartPreference` + partial-PUT.
- `smc-overlay` (C1) merged: `smc.js`, `state.smc`.
- `pytest` + Playwright + `node --test`. **No new runtime dep.**

## Success Criteria

- [ ] Drawings are per `(user, symbol)`; visible across intervals; clear on symbol only; A≠B isolated.
- [ ] POST without `interval` succeeds; stale `interval` key accepted-and-ignored (no 400).
- [ ] SMC toggles survive reload; boot restores from `ChartPreference`.
- [ ] `pytest` + `node --test` green; `makemigrations --check` green; patch gate 100%; ruff clean.
- [ ] No new runtime dep; CSP unchanged; `window.marketChart` still 8 keys; order scanner clean.

## Delivery (Feature Branch Chain)

All slices base on tracker `feat/persistence-foundation`.

- **S1 — drawings per symbol** (~220–280 lines): model + `0012` + endpoint + JS + tests.
- **S2 — SMC toggles** (~130–170 lines): `ChartPreference.smc` + `0013` + endpoint + `smc.js` + tests.

- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High (S1 alone approaches budget)

## Read-Only Boundary

Drawings and SMC toggles are visual persistence only. This change MUST NOT place,
modify, or cancel orders, MUST NOT expose order-execution endpoints, and MUST NOT
relax the read-only invariant. `src/` stays framework-free; `requirements.txt`
unchanged; no new dependency; no CSP relaxation.
