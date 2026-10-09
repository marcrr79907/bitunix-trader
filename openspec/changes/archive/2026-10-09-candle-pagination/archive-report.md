# Archive Report: candle-pagination

**Archived**: 2026-10-09
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 criticals) — 4/4 requirements, 21/28 scenarios at verify + R8 closed post-verify, 310/310 tests
**Delivery**: 2-PR feature-branch-chain — PR1 #52 (backend) → PR2 #53 (frontend) → tracker #51 (`feat/candle-pagination`) → `develop`
**Merged commit range**: `430dd25`…`dd1dd1f` on `develop` (tracker merge `dd1dd1f`, PR #51; child merges `0732787` #52, `52d47ce` #53)

## What Shipped

Issue #44 turns `/market/api/kline` into a DB-first cursor page and the chart into
an infinite-scroll surface. The endpoint gained an optional `before` (UNIX-seconds,
exclusive) param: it reads the durable `Candle` table (`time < before`, newest-first,
`LIMIT limit + WARMUP`), falls back to BitUnix only when the DB cannot fill the range
or the interval is unpersisted (`client.kline(..., end_time=...)`), merges DB-wins, and
computes `src/indicators.py` overlays over the warm window before slicing to the page.
BitUnix failure never 5xx's when DB rows exist. `chart.js` detects the left logical
edge, fetches `before=<oldestTime>`, prepends deduped older candles+overlays and shifts
the visible range to hold the viewport. No schema, no migration, no new dependency; the
WS live path and `src/` boundary are untouched.

| Area | Delivered |
|------|-----------|
| Endpoint | `web/market/views.py` — parse/validate optional `before` (positive int, after interval/symbol/limit, same 400 shape); pass through; BitunixError→400 / RequestException→502 mapping preserved |
| Payload | `web/market/quotes.py` — `WARMUP=20`, `want=limit+WARMUP`; `_db_rows` gated on `CANDLE_INTERVALS`; gap-fill `client.kline(..., end_time=(before or now)*1000)` only when DB short; merge DB-wins; slice candles+overlays to newest `limit`; degradation swallow (rows survive → 200, empty DB re-raises → 502/400) |
| Chart | `web/market/templates/market/chart.js` — `allCandles/allSma/allEma` arrays, `EDGE=5`/`loadingOlder`/`hasMore`/`oldestTime`, `subscribeVisibleLogicalRangeChange` → `loadOlder`, `mergeOlder` dedupe (existing newer wins), viewport shift by prepended count, single in-flight guard, empty-page → `hasMore=false`, `applyPayload` resets anchors, `onPush` still rightmost-only |
| Tests | `tests/web/test_market_api.py` — pagination/DB-first/warm-up/floor/degradation matrix (13 new tests); `tests/web/test_market_e2e.py::test_chart_infinite_scroll_loads_older_page` — DOM E2E that scrolls left, asserts a `before=` request and series growth (added in `d7a14ae`, closing WARNING 2) |
| Reused as-is | `src/client.py::kline`/`BitunixError`, `src/indicators.py`, `trading/candles.py::CANDLE_INTERVALS`, `trading/models.py::Candle`; `requirements.txt` byte-identical to develop |

## Requirement Outcomes

| Req | Domain | Outcome | Notes |
|-----|--------|---------|-------|
| R3 | market-chart | ✅ Green | `before` optional/exclusive; DB-first (`Candle` `time < before`, `-time[:want]`); BitUnix gap-fill only when DB short/unpersisted; merge DB-wins; ascending unique `time`, 5 exact keys; 400 invalid before/symbol/interval; 200 empty; degradation matrix (200 rows / 502 both-fail / 400 BitunixError); anonymous → 302 |
| R4 | market-chart | ✅ Green | `limit+WARMUP(20)` window computed, then sliced; page-edge first candle has non-null sma20/ema20 (rsi where defined); genuine floor gaps omitted, no nulls; overlays only from `src/indicators.py` |
| R7 | market-chart | ⚠️ Partial | Boundary green (4), order scanner clean (36), `requirements.txt` diff empty, `makemigrations` no changes; "runtime deps unchanged" verified by `git diff` only — no covering guard test (SUGGESTION 1) |
| R8 | market-chart | ✅ Green | Infinite scroll implemented in `chart.js`; 5 invariants inspection-verified; runtime proven by E2E; the committed scroll assertion (task 2.1) was delivered post-verify in `d7a14ae` |

**Legend**: ✅ green · ⚠️ partial (invariant holds; test-coverage gap).

## Carry-Forward Items

1. **6 non-persisted intervals are BitUnix-only** — 1m/30m/6h/8h/12h/3d are not in
   the `Candle` dataset (`trading/candles.py::CANDLE_INTERVALS`), so `/market/api/kline`
   always gap-fills them live. The endpoint serves them correctly, but history stops at
   BitUnix's ~3y depth and they get no degradation benefit. Backfilling them (extend
   `candle-store`) is a future change, not this one.
2. **Retention/prune and cron are separate changes and already done** — `#45` (prune)
   and `#48` (cron) shipped in the `cron-jobs` change (`b2f2d66`→`8d0a56a`, PR #49),
   and the backfill budget in `0f177ae`. Nothing here depends on them.
3. **ETH/SOL/PEPE backfill is in progress** — the durable dataset currently covers BTC
   history fully; the other symbols are still being backfilled by the worker. Until they
   finish, older pages for those symbols arrive via BitUnix gap-fill.
4. **R7 dependency-freeze has no guard test (SUGGESTION 1)** — verified by an empty
   `git diff`; add a runtime-import guard test if the freeze must be mechanically enforced.
5. **Degraded 200 for a `BitunixError` with stale DB rows is by design (SUGGESTION 2)** —
   DB rows win per spec; a symbol the upstream rejects still returns 200 if stale rows
   exist. Noted so future readers do not mistake it for a mapping bug.
6. **`chart.js` line-budget drift (SUGGESTION 3)** — 295 lines vs the design's ~120–140
   estimate; the extra is pre-existing WS/channel/backoff code plus ~45 new scroll lines,
   no business math. Correct the design estimate if reused as a template.

## Verify Findings (non-blocking)

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| W1 | Low | `tasks.md` was 0/36 checked; completion was not readable from the artifact (hard contract temporarily forbade editing `openspec/**` during apply) | ✅ **Closed at archive** — tasks.md is 36/36 `[x]` (verified in the archived copy); marks were restored in `1766c66` and confirmed here |
| W2 | Medium | R8's only declared verification (DOM E2E) was not delivered: committed E2E did not scroll or observe `before=`; behavior proven only by a throwaway verifier probe | ✅ **Closed post-verify** — `d7a14ae` added `test_chart_infinite_scroll_loads_older_page` (forces `setVisibleLogicalRange`, asserts `before=` observed + series grows, 34 insertions) |
| W3 | Low | No WU2/PR2 apply-progress artifact; frontend Strict-TDD RED→GREEN evidence unrecorded (only `#1385` for WU1) | Noted — pipeline-evidence gap, not a code defect; not reopened |
| S1 | Suggestion | R7 "runtime dependencies unchanged" has no covering test (empty `git diff` only) | Open — mirrors archived market-chart W2 |
| S2 | Suggestion | Degraded path returns 200 for a `BitunixError` (invalid symbol) when DB rows exist | By design (DB rows win); documented in Carry-Forward 5 |
| S3 | Suggestion | `chart.js` is 295 lines vs the ~120–140 design forecast | Documented — pre-existing WS/channel code, no business logic |

## SDD Cycle Complete

Planned (`3f3a469`) → implemented (`6dc5c10`, `8e997b8`) → verified
(`pass_with_warnings`, 0 blockers, 0 criticals; `1766c66`) → E2E warning closed
(`d7a14ae`) → merged (PR #52 → #53 → tracker #51 → `develop`) → archived.

Delta spec merged into the main spec store (source of truth):

- `openspec/specs/market-chart/spec.md` — R3, R4, R7 **replaced** with the delta text;
  R8 **added**; R1, R2, R5, R6 **preserved** unchanged. Result: 8 requirements,
  37 scenarios, coherent, nothing dropped.

No new capability was created (`market-chart` was modified in place). Merge was
non-destructive — verified by heading inventory before/after.

Archive audit trail: `openspec/changes/archive/2026-10-09-candle-pagination/`
(explore, proposal, specs, design, tasks, verify-report, archive-report).

## Traceability — Engram Observation IDs

| Artifact | Observation ID |
|----------|----------------|
| `sdd/candle-pagination/explore` | 1380 |
| `sdd/candle-pagination/proposal` | 1381 |
| `sdd/candle-pagination/spec` | 1382 |
| `sdd/candle-pagination/design` | 1383 |
| `sdd/candle-pagination/tasks` | 1384 |
| `sdd/candle-pagination/apply-progress` (WU1 only) | 1385 |
| `sdd/candle-pagination/verify-report` | 1387 |
| `sdd/candle-pagination/archive-report` | 1388 |

Merged specs have no standalone Engram observations — they live in the OpenSpec
file store (`openspec/specs/market-chart/spec.md`).
