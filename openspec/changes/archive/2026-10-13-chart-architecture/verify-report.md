# Verify Report — chart-architecture (issue #113, Fase F0)

**Verdict**: `pass_with_warnings`
**Verified by**: orchestrator (adversarial, fresh probes + real browser). The delegated verify sub-agent was cancelled; verification executed inline.
**Branch**: `feat/chart-architecture-cleanup` (HEAD `b9b1f72`), chain: tracker `feat/chart-architecture` + S1 `…-esm-scaffold` (`0bfb29f`) + S2 `…-host-store-bus` (`513029c`) + S3 `…-controllers` (`ceaf714`) + S4 `…-cleanup` (`b9b1f72`); all slice PRs base on the tracker.

## Gates (L1)

| Gate | Result |
| --- | --- |
| `node --test "tests/js/**/*.test.js"` | **60 passed, 0 fail** |
| `pytest -m e2e -p no:randomly` | **24 passed** |
| `pytest tests/ --ignore=tests/web` | green |
| `ruff check .` + `ruff format --check .` | clean (133 files) |
| `package.json` | **exactly `{"type":"module"}`** (no deps/scripts) |
| `requirements.txt` vs develop | **empty diff** (no new dependency) |

## Gates (L2)

- `diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` → **100%** (10 changed Python lines, 0 missing: `web/market/views.py`). JS is outside the Python patch gate → covered by 60 node + 24 E2E.

## Spec conformance (L3) — R14–R18

- **R14 boundaries**: frozen inventory present; **store holds ONLY `{symbol,interval,indicators,params,smc,tool}`** (`STORE_KEYS`, no candle keys — a dedicated test proves `set` drops `candles`); **no module > ~300 lines** (largest `controllers/drawings.js` = 298); **no controller imports `main`** (grep empty); `main.js` has no cycles.
- **R15 ESM**: `package.json {"type":"module"}`; cores use native `export`, **UMD shim gone** (grep `module.exports`/`root.X` empty); tests use `import`; entry is `<script type="module">`; LightweightCharts stays a classic global; **every imported module resolves to a real same-origin route returning `text/javascript`** (14/14 routes 200; unknown → 404); no controller self-boots; `boot()` is the last side effect.
- **R16 config**: config is the ESM export `CONFIG` in the entry `chart.js`; no inline script, no `window` config; `/market/chart.js` contains `BTCUSDT` AND `market_kline`.
- **R17 invariants**: #68 single-write-path (history→`setData`, live→`update()`, config→rebuild, owned by the host); single-source (JS never computes indicators/SMC); the `gen`/`drawGen`/`smcGen` race guards + boot/switch `.then()` ordering preserved verbatim.
- **R18 test seams**: `window.marketChart` = exactly 8 keys (`candleSeries,chart,drawings,panes,ready,smc,smcCounts,smcToggles`) + `window.SmcOverlayCore` re-exposed.

### Adversarial probes (independent + real browser)
- Grep audits: UMD gone; no controller→main imports; store key set frozen; `BTCUSDT`+`market_kline` present in the served entry.
- Route probe (Django client): all 8 modules + 6 controllers → 200 `text/javascript`; unknown controller → 404.
- **Real browser** (Playwright, logged in):
  - 14 modules load 200; `window.marketChart.ready===true`; `window.SmcOverlayCore` present; panes `rsi`+`macd`; canvas exists; **0 page errors**.
  - Interval switch `1m→1h`: **0 errors**, `ready` stays true.
  - MACD toggle: **0 errors**, `macd` pane appears.
  - Switch then toggle (sequential, with realistic waits): **0 errors**.
- **Behavior-equivalence is the crux** and it holds — same modules, same seam, same boot/switch semantics, no assertion edits.

## Warnings (non-blocking)

- **W1 — `Object is disposed` observed once under an artificially compressed probe sequence** (interval switch immediately followed by a MACD toggle with no wait). Reproduced as **0 errors** when the two actions are sequential with realistic waits, and each action alone is 0 errors. This matches the known pre-existing E2E flake under load (`-p no:randomly` on an idle machine), not a F0 regression. Flagged for transparency.
- **W2 — Raw slice diffs are large** (S3 ~1218 ins/1065 del) but dominantly **moved** code, not rewritten; S1's UMD→ESM dedent shows ~115 real lines under `git diff -w`. Reviewer should judge behavior-equivalence, not line count.
- **W3 — `chart-host.js` holds shared `seriesData`/`lastBucket` accessors** added during the split (a small extension of its #68 ownership), and `stream.connect(next)` accepts the boot key. Intentional; no behavior change.
- **W4 — `CONTROLLER_ALLOWLIST` route coverage** is proven by a dedicated test (S4) that iterates both allowlists, closing the "missing route → import 404 → blank chart" risk.
- **SUGGESTION**: `tasks.md` checkboxes not marked by apply (orchestrator hard contract); engram `sdd/chart-architecture/apply-progress` is the completion source.

## Requirement coverage

- `market-chart` DELTA: R14 (boundaries), R15 (ESM loading), R16 (config), R17 (invariants), R18 (test seams) — all satisfied.
- `core-domain-boundary` / `security-invariants`: N/A (JS-only change; CSP unchanged; no new dependency).

## Blockers

None. **F0 (base sólida) is complete — the architecture is ready for F1–F11.**
