# Verify Report — smc-overlay (issue #75, Fase C1)

**Verdict**: `pass_with_warnings`
**Verified by**: orchestrator (adversarial, fresh probes + browser). The delegated verify sub-agent timed out without output (same `general`-agent failure seen in A3/B2); verification was executed inline.
**Branch**: `feat/smc-overlay-e2e` (HEAD `bfa2425`), chain: tracker `feat/smc-overlay` + Slice1 `…-endpoint` (`4c31166`) + Slice2 `…-render` (`574fe12`) + Slice3 `…-e2e` (`bfa2425`); all slice PRs base on the tracker.

## Gates (L1)

| Gate | Result |
| --- | --- |
| `python -m pytest tests/ --ignore=tests/web` | green |
| `pytest -m e2e -p no:randomly` | **23 passed** (baseline 19 + 4 SMC) |
| `node --test "tests/js/**/*.test.js"` | **45 passed, 0 fail** (26 baseline + 19 new) |
| `ruff check .` | clean |
| `ruff format --check .` | clean |
| `requirements.txt` vs develop | **empty diff** (no new dependency) |
| `src/smc/` untouched | yes (C1 changes are web-only) |

## Gates (L2)

- `diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` → **100%** (75 changed Python lines, 0 missing: `web/market/quotes.py`, `web/market/views.py`). The JS layers (`smc-overlay-core.js`, `chart.js`) are outside the Python patch gate → covered by `node --test` (19 tests) + E2E (4 tests), per design.

## Spec conformance (L3)

- **Endpoint** `GET /market/api/smc?symbol=&interval=&limit=` (`@login_required`, GET-only): runs the frozen `src/smc/` chain server-side over the candle window; payload `{symbol, interval, swings:[{kind,time,price,label}], structure:[{kind,time,price,direction,trend}], order_blocks:[{kind,time,top,bottom,anchor_time}], fvgs:[{kind,time,top,bottom}], range:{high,low,equilibrium,time}|null, setups:[{direction,time,entry,stop,take_profit,rr,score}]}`; **no bar `index` leaks** (probe: `"index"` absent); server resolves index→time.
- **`limit`** default 200, valid `1..200`, else **400** (probe: `limit=99999` → 400).
- **Scoping**: market-global (no `for_user`) — SMC is market data. Probe: unknown symbol `zzz` interval → 400; empty/no-candles → 200 with empty arrays + `range:null`; anonymous → 302.
- **`label:null`** for the first swing of each kind (probe confirmed).
- **Render**: one canvas primitive (swings/structure/OB/FVG/premium-discount bands) + one `createSeriesMarkers` handle (setups) with `detach()` teardown/re-create on rebuild/switch; session-only toggles (6 families); reload on boot/`switchTo`; `window.marketChart.smc` parity seam.
- **Single-source**: `smc-overlay-core.js` only reshapes the payload (camelCase, descriptors, markers) — NO SMC recomputation (verified: no `find_*`/confluence/geometry math).
- **Single-write-path #68**: overlay draws on the primitive/markers layer; `setData` only on history/config (unchanged).
- CSP unchanged; no inline handlers; `smc-overlay-core.js` served same-origin via a view (mirror A3).

### Adversarial probes (independent, throwaway + browser)
- Endpoint: anon → 302; bad interval → 400; empty window → 200 + empty arrays + `range:null`; `"index"` absent from the serialized payload; `anchor_time` present.
- Browser (real): 6 toggle checkboxes present; `window.marketChart.smc` seam populated (50 swings); exactly **1** `/market/api/smc` request on boot; toggling a family does **not** refetch (payload unchanged — it filters the DRAWING, not the data); 0 page errors.

## Warnings (non-blocking)

- **W1 — White chart canvas vs dark app chrome** (pre-existing, chart-wide): the LightweightCharts canvas renders white while the app chrome is dark. Out of C1 scope; recorded as a follow-up.
- **W2 — Slice 3 touched a pre-existing RSI-pane E2E fixture**: two RSI-pane tests failed on a stale constant-close fixture; Slice 3 fixed the fixture at its root (varied-OHLC seed helper). Not an SMC regression; flagged for reviewer awareness.
- **W3 — `SL` a11y fix**: swing connector color `#9e9e9e` (2.7:1 on white) → `#616161` (6.2:1) for WCAG 1.4.11. Applied in `chart.js`.
- **W4 — Pre-existing WS-route E2E flake** (`test_ws_stream_never_calls_setdata`) surfaces occasionally under load; passes in isolation/re-runs. Run `-m e2e -p no:randomly` on an idle machine.
- **SUGGESTION**: `tasks.md` checkboxes not marked by apply (orchestrator hard contract); engram `sdd/smc-overlay/apply-progress` is the completion source.

## Requirement coverage

- New `smc-overlay` capability (11 reqs / 27 scenarios): satisfied (with W1–W4 notes).
- `market-chart` DELTA R12: satisfied.

## Blockers

None.
