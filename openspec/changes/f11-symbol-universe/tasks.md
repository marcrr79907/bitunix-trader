# Tasks: f11-symbol-universe (issue #124, Fase F11)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

> **Normative-id note.** `market-ingestion/spec.md` R7 names
> `MAX_INGEST_SYMBOLS = 50`; `design.md:61-74` decides there is **one** constant,
> `src/config.py::MAX_WATCHLIST_SYMBOLS = 50`, imported by `watchlist.py` and
> `worker.py`. The design wins: the spec's "reuse the same value" is satisfied by a
> single name. Likewise `alert-rules` R12 supersedes only R10's
> `symbol ∈ SYMBOLS` clause; the interval bound and the symbol→interval check
> order stay normative.

> **Known gotchas pinned as task notes.** (a) JS module ceiling 300: `main.js` is
> 293 → **295 after exactly +2 wiring lines**, no further growth; `toolbar.js`
> (187) is byte-untouched. (b) `git add -A` must NOT stage `openspec/` — stage
> slices and specs separately, archive only in close-out. (c) The `.pairs`
> container and `.pair[data-symbol]` buttons MUST survive; three E2E selectors
> (`test_market_e2e.py:1908,:2007,:2176`) and `toolbar.js:29-33` depend on them.
> (d) No new dependency, no new client method, no migration, no new store key or
> bus event, CSP unchanged.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | S1 ~160, S2 ~270, S3 ~220, S4 ~370 → **~1020** |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1a (catalog + `/api/symbols` + catalog tests) → PR1b (watchlist API + `_pair_error` + watchlist/alert tests) → PR2 (ingestion + `due_intervals`) → PR3 (search core + picker + markup + CSS + allowlists) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base / boundary |
|------|------|-----------|-----------------|
| A-S1 | `catalog.py` + `GET /market/api/symbols` + `test_market_catalog.py` | PR 1a | base = tracker `feat/f11-symbol-universe` |
| A-S2 | `watchlist.py` + 2 routes + `_pair_error` rewrite + `test_market_watchlist.py` + extended alert matrix | PR 1b | base = tracker; S1 merged first |
| A-S3 | `due_intervals` + `intervals=` on `fetch_closed_candles` + worker union/cap + `test_candles.py`/`test_worker_ingest.py` | PR 2 | base = tracker; S2 merged first |
| A-S4 | `symbol-search-core.js` + `controllers/symbol-picker.js` + `chart.html` + `main.js` +2 + `theme.css` + allowlists + UX/E2E | PR 3 | base = tracker; S3 merged first |

S1 ≈160 and S2 ≈270: **S1+S2 ≈430 > 400**, so PR1 is split into **PR1a**: catalog
only (~160), and **PR1b**: watchlist + alerts (~270). Each PR's own diff must be
≤400; the tracker merges to `develop` only in close-out, `main` untouched.

## Gates per slice (run before each slice's commit)

```bash
node --test "tests/js/**/*.test.js"
.venv/bin/python -m pytest -p no:randomly
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python web/manage.py makemigrations --check --dry-run
.venv/bin/diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100  # 100% patch on new lines
```

## Phase 1 — A-S1: catalog + `/api/symbols` (PR1a)

Base tracker; branch `feat/f11-symbol-universe-s1`; no deps. Rollback: delete
`catalog.py`, the route and its view; the nav still renders from `config.SYMBOLS`.

- [ ] 1.1 **RED** NEW `tests/web/test_market_catalog.py`: projection+sorted+dedup, stub gets no `symbols` arg; TTL warm (now=59, no 2nd call) / expired (now=61 refetch); failure raises and leaves the cache intact; `symbol_exists` warm-is-offline (raising stub) and unknown→False; endpoint 200/302/405/502. No network, `now` injected. Acceptance: red before 1.2.
- [ ] 1.2 **GREEN** NEW `web/market/catalog.py` (~70): `CATALOG_TTL_SECONDS=60`, `SYMBOL_RE`, `_cache`, `list_symbols(client=None,*,now=None)`, `symbol_exists()`, `reset_cache()`. stdlib + `src.client`/`src.config` only (no Django, no `trading`). Acceptance: 1.1 green.
- [ ] 1.3 **GREEN** `web/market/views.py`: `api_symbols` `@login_required` + GET-only, `502 {"error":"upstream"}` on `BitunixError`/`RequestException` (mirror `api_kline`). `web/market/urls.py`: +1 `path("market/api/symbols", ...)` after the alerts block. Acceptance: route resolves; 1.1 green.
- [ ] 1.4 **REFACTOR** gates green; `tests/test_boundary.py` and `tests/test_dependency_guard.py` unchanged and green; `requirements.txt` unchanged.

## Phase 2 — A-S2: watchlist CRUD + alert validation (PR1b)

Base tracker (S1 merged); branch `feat/f11-symbol-universe-s2`; deps S1. Rollback:
delete `watchlist.py` + 2 routes, restore `symbol not in SYMBOLS`; `Watchlist` rows
stay valid (unused).

- [ ] 2.1 **RED** NEW `tests/web/test_market_watchlist.py`: GET default→`config.SYMBOLS`+`default:true` and **0 rows written**, populated sorted+`default:false`, env change visible; POST matrix (malformed 400 always, unknown-when-warm 400, cap 400 at 50, duplicate 201 no 2nd row); DELETE idempotent 204; A≠B (B DELETE leaves A intact); body `user` ignored; CSRF 403; anonymous 302. Acceptance: red before 2.2-2.4.
- [ ] 2.2 **GREEN** NEW `web/market/watchlist.py` (~110): `api_watchlist` (GET/POST), `api_watchlist_detail` (DELETE), `Watchlist.for_user` only, validation order format→warm-membership→cap→`get_or_create`, `MAX_WATCHLIST_SYMBOLS` from `src/config.py`. Acceptance: 2.1 green.
- [ ] 2.3 **GREEN** `src/config.py`: +`MAX_WATCHLIST_SYMBOLS = 50` (one constant). `web/market/urls.py`: +2 paths. Acceptance: 2.1 green; no migration.
- [ ] 2.4 **GREEN** `web/market/alerts.py:44-55`: `_pair_error` → `SYMBOL_RE` always, `catalog.symbol_exists` warm-absent→`invalid symbol`, raise→fail-open; interval check unchanged and after symbol. **RED first**: extend `tests/web/test_market_alerts_api.py` with warm-accept, warm-reject, cold-fail-open, cold-malformed-400, 1m-unchanged, catalog-symbol-outside-`SYMBOLS`→201. Acceptance: new tests red before edit, green after.
- [ ] 2.5 **REFACTOR** gates green; existing F10 alert matrix still green; `diff-cover` 100% on `watchlist.py` and changed `alerts.py` lines.

## Phase 3 — A-S3: worker ingestion + `due_intervals` (PR2)

Base tracker (S2 merged); branch `feat/f11-symbol-universe-s3`; no deps on UI.
Rollback: revert worker union + `due_intervals` + `intervals=` param; ingestion
returns to `config.SYMBOLS`. No schema.

- [ ] 3.1 **RED** `tests/web/test_candles.py` (extend): `due_intervals` table (same bucket → omitted; boundary per interval → included; `last_poll=None` → all 8); `fetch_closed_candles(intervals=...)` requests only those; `intervals=None` back-compat; per-`(symbol,interval)` failure isolated (`continue`). Acceptance: red before 3.2.
- [ ] 3.2 **GREEN** `web/trading/candles.py` (~25 added): `due_intervals(now, last_poll)` pure; `fetch_closed_candles(..., intervals=None)` + narrow `try/except (BitunixError, RequestException): continue`. Acceptance: 3.1 green.
- [ ] 3.3 **RED** `tests/web/test_worker_ingest.py` (extend): union order defaults-first then sorted, dedup; 60 symbols → exactly 50 with all defaults present; watchlist symbol ingested; `_last_poll` advances only on success; **negative control** bypassing `due_intervals` exceeds 10 req/s arithmetic. Acceptance: red before 3.4.
- [ ] 3.4 **GREEN** `web/worker.py` (~20): `_last_poll`, `ingest_symbols()` unscoped union capped, `run_once` passes `due_intervals(now,_last_poll)` and advances `_last_poll` on success only. Acceptance: 3.3 green.
- [ ] 3.5 **REFACTOR** gates green; `test_worker_alerts.py`/`test_worker_candles.py` unchanged and green; no migration.

## Phase 4 — A-S4: search core + picker + markup + CSS + allowlists (PR3)

Base tracker (S3 merged); branch `feat/f11-symbol-universe-s4`; deps S1+S2 for the
API. Rollback: revert branch; keep `.pairs`/`.pair[data-symbol]` so nav, toolbar
and E2E keep working.

- [ ] 4.1 **RED** NEW `tests/js/symbol-search-core.test.js`: tier order exact→prefix→substring then alpha (prefix outranks substring), cap applied after sort (300→50), empty/whitespace→all capped, case-insensitive, no-match→`[]`, never throws on `null`/non-array/non-string. Acceptance: red before 4.2.
- [ ] 4.2 **GREEN** NEW `web/market/templates/market/symbol-search-core.js` (~70, zero imports): `filterSymbols(query, symbols, limit=50)`. Acceptance: 4.1 green; ≤300 lines.
- [ ] 4.3 **RED** `tests/web/test_market_ux.py` (extend): `MODULE_ALLOWLIST` 33→34 (`symbol-search-core`), `CONTROLLER_ALLOWLIST` 17→18 (`symbol-picker`), both serve 200 JS, combobox roles + ids present, no inline handler, 8-key seam / 11 store keys unchanged. `tests/web/test_market_e2e.py` (extend): search→Enter emits `config:changed`; follow issues one POST and re-renders; existing `.pair` selectors still pass. Acceptance: red before 4.4-4.7.
- [ ] 4.4 **GREEN** NEW `web/market/templates/market/controllers/symbol-picker.js` (~160): `createSymbolPicker({store,bus,config})` → `{refresh}`; fetch symbols+watchlist once, local filter, combobox ArrowUp/Down wrap + Enter + Escape, `aria-activedescendant`, live count, follow/unfollow POST/DELETE with `csrfToken()`, emits existing `config:changed`. Acceptance: 4.3 green; ≤300.
- [ ] 4.5 **GREEN** `web/market/templates/market/chart.html` (+~10): static search input + `#symbol-results` + `#symbol-status` above `<nav class="pairs" id="watchlist">`, `.pair[data-symbol]` untouched, 1 `modulepreload`. Acceptance: markup test green.
- [ ] 4.6 **GREEN** `web/market/views.py:44,76`: allowlists +1 core +1 controller. `web/market/templates/market/main.js` **exactly +2** (one import, one `createSymbolPicker` call) → ends **295**; `toolbar.js` byte-untouched. Acceptance: served 200; UX green.
- [ ] 4.7 **GREEN** `web/accounts/templates/registration/theme.css` (+~10): `.symbol-search`/`.symbol-results`/`.watchlist-row` using existing tokens only. `docs/architecture/chart-modules.md`: inventory +2. Acceptance: no literal colors; docs updated with the slice.
- [ ] 4.8 **REFACTOR** gates green; size guard empty allowlist green; CSP + `requirements.txt` + `src/` unchanged; `git diff --exit-code -- .../controllers/toolbar.js`.

## Close-out (tracker → develop)

- [ ] C.1 Run `sdd-verify` against all five delta specs; record every scenario.
- [ ] C.2 Fresh adversarial review of the full tracker diff (new session, no apply context).
- [ ] C.3 **`/impeccable` UI audit — MANDATORY** (A-S4 ships UI): combobox/keyboard/focus, contrast, tokens, responsive panel.
- [ ] C.4 Merge each slice PR into `feat/f11-symbol-universe`, then tracker → `develop`; `main` untouched.
- [ ] C.5 Archive OpenSpec change (`openspec/changes/archive/YYYY-MM-DD-f11-symbol-universe/`), sync deltas.
- [ ] C.6 Update `docs/architecture/chart-modules.md` (final counts) and `CHANGELOG.md`.
- [ ] C.7 Update issue **#124** checklist (search, watchlist, ingestion; layout templates stay open for `f11-layout-templates`).
- [ ] C.8 Save Engram memory + write the session handoff document.

## Verification

- [ ] V.1 `node --test "tests/js/**/*.test.js"` green.
- [ ] V.2 `.venv/bin/python -m pytest -p no:randomly` green; `diff-cover` vs `origin/develop` → 100% patch.
- [ ] V.3 `.venv/bin/ruff check . && .venv/bin/ruff format --check .` clean.
- [ ] V.4 `.venv/bin/python web/manage.py makemigrations --check --dry-run` clean (no model change).
- [ ] V.5 `wc -l`: every module ≤300; `main.js` == 295; `toolbar.js` byte-identical.
- [ ] V.6 Seam 8 keys, `STORE_KEYS` 11, no new bus event; CSP, `requirements.txt`, `src/` unchanged.
- [ ] V.7 `openspec/` never staged by a slice commit.

## Rollback

- **S1**: delete `catalog.py` + route/view; nav falls back to `config.SYMBOLS`.
- **S2**: delete `watchlist.py` + routes, restore `symbol not in SYMBOLS`; rows inert.
- **S3**: revert union + `due_intervals` + `intervals=`; ingestion returns to `config.SYMBOLS`.
- **S4**: revert picker/core/markup/CSS; `.pair[data-symbol]` untouched throughout.
- **Tracker**: drop `feat/f11-symbol-universe` and all slices; no migration to reverse.
