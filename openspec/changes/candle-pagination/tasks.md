# Tasks: candle-pagination (issue #44)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

## Guard/Edge Matrix (every row = a test in its WU)

- [ ] `before` omitted → latest page (backward compatible) (R3)
- [ ] `before` non-int / ≤0 → 400 `{"error":...}` (R3)
- [ ] DB has full `limit+WARMUP` page → `client.kline` NOT called (R3)
- [ ] DB short → `client.kline(..., end_time=(before or now)*1000)` called (R3)
- [ ] Merge dedupe by `time`: DB row wins over upstream duplicate (R3)
- [ ] Warm-up: page first candle has non-null sma20/ema20 when ≥20 prior rows exist (R3/R4)
- [ ] Series start: leading warm-up gaps omitted, no nulls (R4)
- [ ] Degradation: DB rows + client raises → 200 degraded; DB empty + raises → 502; DB empty + ok → 200 (R3)
- [ ] Empty cursor → 200 empty `candles` + empty overlays (R3)
- [ ] Candle keys exactly `{time,open,high,low,close}`; `time` int (R3)
- [ ] `candles` ascending + unique `time` (R3)
- [ ] JS: WS live rightmost candle not clobbered by prepend (R8)
- [ ] No schema field / no migration; `Candle` read-only (R7)
- [ ] `src/` framework-free (`test_boundary.py`); `requirements.txt` unchanged (R7)
- [ ] No order surface; `/market/kline` matches no forbidden fragment (R7)

## WU1 (PR1) — backend: DB-first pagination + warm-up + degradation

Base `feat/candle-pagination` (tracker). Depends: none. Strict TDD (`python -m pytest`). Headless/curl-verifiable (~280 lines).

- [ ] 1.1 **RED** `tests/web/test_market_api.py`: `before` forwarded → page is newest `limit` with `time < before`; omitted → latest; `before=abc`/`0`/`-1` → 400.
- [ ] 1.2 **RED** same file (DB fixture): seed `Candle` full page → recording `StubClient` asserts `kline` NOT called.
- [ ] 1.3 **RED** seed short DB → client called with `end_time`; merged rows deduped, DB wins on duplicate `time`.
- [ ] 1.4 **RED** warm-up: ≥20 prior rows → first page candle sma20/ema20 non-null; series floor → leading points omitted, no nulls.
- [ ] 1.5 **RED** degradation matrix: DB rows + raise → 200 degraded; DB empty + `RequestException` → 502; DB empty + `BitunixError` → 400; DB empty + ok → 200; empty cursor → 200 empty.
- [ ] 1.6 **GREEN** `web/market/quotes.py`: `WARMUP=20`, `want=limit+WARMUP`; `_db_rows` reads `Candle.objects.filter(symbol,interval[,time__lt]).order_by("-time")[:want]` gated on `CANDLE_INTERVALS` (import from `trading.candles`); ascending.
- [ ] 1.7 **GREEN** `quotes.get_kline_payload(client, symbol, interval, limit, before=None)`: DB-first; gap-fill via `client.kline(..., want, end_time=end_ms)` only when `len(db)<want`; merge DB-wins; compute `src/indicators.py` over window, slice to newest `limit`; strip to 5 keys.
- [ ] 1.8 **GREEN** `quotes`: swallow upstream failure only when `db` non-empty (log `kline degraded`), else re-raise.
- [ ] 1.9 **GREEN** `web/market/views.py`: parse/validate `before` (positive int, after interval/symbol/limit) with same 400 shape; pass through.
- [ ] 1.10 Pin `test_endpoint_network_failure_is_502_upstream` (interval `1m`, unpersisted → DB empty) still asserts 502; add explicit names for the new degradation tests.
- [ ] 1.11 Full suite + `ruff check . && ruff format --check .` green; endpoint curl-verifiable.
- [ ] 1.12 **Rollback**: revert `quotes.py`, `views.py`, `test_market_api.py`. No migration, no data mutation.

## WU2 (PR2) — frontend: chart infinite scroll

Base PR1 branch. Depends: WU1. Strict TDD. Dev-only E2E verifies JS (outside the Python patch gate). ~120 lines.

- [ ] 2.1 **RED** `tests/web/test_market_e2e.py` (`@pytest.mark.e2e`): after left-edge scroll a `before=` request is observed and the candle series grows (DOM/evaluate, no image diffs).
- [ ] 2.2 **GREEN** `chart.js`: module arrays `allCandles/allSma/allEma`; `EDGE=5`, `loadingOlder`, `hasMore`, `oldestTime`; `subscribeVisibleLogicalRangeChange` → `loadOlder` fetching `before=oldestTime`.
- [ ] 2.3 **GREEN** `chart.js`: `mergeOlder` deduped by `time` (existing newer wins); prepend + `setData`; shift logical range by added count; `oldestTime=allCandles[0].time`; single in-flight guard; empty page → `hasMore=false`.
- [ ] 2.4 **GREEN** `chart.js`: `applyPayload` resets anchors (`oldestTime`, `hasMore=true`) after bucket-close refetch; `onPush` still `update()`s rightmost bar only.
- [ ] 2.5 Full suite green (e2e deselected); local `python -m pytest -m e2e`.
- [ ] 2.6 **Rollback**: revert `chart.js` + `test_market_e2e.py`. WU1 untouched; chart returns to single page.

## Phase 3 — Verification

- [ ] 3.1 `python -m pytest` green under Strict TDD (e2e deselected by default).
- [ ] 3.2 `ruff check . && ruff format --check .` green.
- [ ] 3.3 `tests/test_boundary.py` green; order scanner clean; `requirements.txt` unchanged; no new migration.

## Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | DB-first pagination + warm-up + degradation | PR1 | base tracker `feat/candle-pagination`; tests included |
| 2 | chart infinite scroll + E2E | PR2 | base PR1 branch; dev-only E2E |

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ~280, PR2 ~120 → ~400 total |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (backend, headless) → PR2 (frontend, browser); PR2 targets PR1 branch |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |
| Tracker branch | `feat/candle-pagination` → merges to `develop` |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium
