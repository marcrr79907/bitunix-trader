# Archive Report: f11-symbol-universe

**Change**: `f11-symbol-universe` (issue #124, Fase F11 — part A of two)
**Archived**: 2026-10-19
**Delivered on**: `develop` via PR #246 (tracker `feat/f11-symbol-universe`), after
a 6-PR review chain (#239–#245)
**Verdict**: PASS_WITH_WARNINGS — 12/12 requirements compliant, 0 CRITICAL, 0 blockers

## What shipped

| Slice | Delivered |
|---|---|
| A-S1 | `web/market/catalog.py` (exchange-wide universe, 60s TTL cache, `symbol_exists`) + `GET /market/api/symbols` |
| A-S2a | `web/market/watchlist.py` (`GET/POST /market/api/watchlist`, `DELETE /<symbol>`), virtual `config.SYMBOLS` fallback, shared 50-symbol cap |
| A-S2b | `alerts._pair_error` validates against the catalog (warm → reject; cold → fail open on a well-formed symbol) |
| A-S3 | `candles.due_intervals` + `intervals=` on `fetch_closed_candles`; worker ingests the union of defaults + all watchlists, capped, with per-(symbol, interval) failure isolation |
| A-S4 | `symbol-search-core.js` (pure ranking) + `controllers/symbol-picker.js` (ARIA combobox, follow/unfollow) |
| A-S5 | Review slice: 6 findings fixed, `/impeccable` audit applied, verify report written |

## Specs synced

| Canonical spec | Action |
|---|---|
| `openspec/specs/symbol-catalog/spec.md` | **CREATED** (4 requirements, 12 scenarios) |
| `openspec/specs/market-watchlist/spec.md` | **APPENDED** R14.8–R14.10 (now 6 requirements, 18 scenarios) |
| `openspec/specs/alert-rules/spec.md` | **APPENDED** R12 (now 13 requirements, 48 scenarios) |
| `openspec/specs/market-ingestion/spec.md` | **APPENDED** R7–R9 (now 11 requirements, 27 scenarios) |
| `openspec/specs/market-chart/spec.md` | **APPENDED** R19–R20 (now 25 requirements, 137 scenarios) |

No destructive deltas: every change was additive. No migration was required —
`Watchlist` already existed with its `(user, symbol)` constraint.

## Bugs found and fixed before merge

| Severity | Finding |
|---|---|
| **CRITICAL** | `ingest_symbols()` was written but `run_loop` still used `config.SYMBOLS`, so the entire watchlist ingestion path was inert. Caught by a wiring test, not by the unit tests of `ingest_symbols` itself. |
| **HIGH** | The follow button was `disabled` once a symbol was followed, making **unfollow impossible** — a direct violation of spec R19. Now an `aria-pressed` toggle issuing POST or DELETE. |
| **MEDIUM** | `except Exception` on the cold-catalog path would have swallowed programming errors and silently degraded both endpoints to fail-open. Narrowed to `BitunixError`/`RequestException`. |
| **MEDIUM (a11y)** | The followed state used `--up`, which is **4.36:1** on the light surface (below AA). Now `--text` + bold weight, with the glyph carrying the state. |
| **MEDIUM (UX)** | A failed catalog fetch left the search silently unusable. Now an explanatory empty state with a disabled input. |
| **LOW** | `filterSymbols(…, limit<=0)` could invert the slice; `_last_poll` module-global leaked between tests. |

## Process notes

- **Four of the five SDD sub-agents timed out** on network during this session
  (`explore`, `design`, `review`, and an early `proposal` attempt). The artifacts
  were produced inline by the orchestrator using direct code evidence. This is
  gotcha #12 of the handoff, now confirmed across a second session.
- **`gh pr merge --delete-branch` on a stacked chain is destructive.** It deletes
  the merged PR's **base** branch, which auto-closes every downstream PR that
  targeted it. Three PRs (#240/#242/#244) were closed this way. Recovery: the
  linear slice chain was preserved on `feat/f11-symbol-universe-review`, verified
  byte-identical to the gated tree, and landed as PR #245. **Never pass
  `--delete-branch` until the whole chain has landed.**
- The 400-line review budget was enforced by splitting S2 into S2a (watchlist) and
  S2b (alerts) after measuring 445 lines; every final slice is under 400
  (S1 263, S2a 337, S2b 108, S3 260, S4 371, review 225).

## Accepted warnings (documented in the verify report)

- **W2** — `DELETE /market/api/watchlist/<symbol>` does not format-validate the
  symbol; deletion is scoped by `for_user` and idempotent by spec, so a malformed
  name is a harmless no-op.
- **W3** — `_last_poll` is process-global and does not survive a restart; a
  restart re-issues every interval once, absorbed by the cycle throttle.
- **W4** — The picker E2E was not executed (dev-only, flaky #149); behaviour is
  covered by the node controller test plus markup/allowlist tests.

## Remaining work (part B)

`f11-layout-templates`: `ChartTemplate` model + migration 0017, `/market/api/templates`
CRUD, and the save/apply/delete UI. Independent of everything above; issue #124
stays open for it.
