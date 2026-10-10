# Design: test-debt

## Technical Approach

Test/doc-only change. W1 extends the existing dev-only browser E2E with
`page.route_web_socket` to give R5's two live-candle scenarios real runtime
evidence. W2 adds an AST dependency guard mirroring `tests/test_boundary.py`.
SUGGESTION 3 is a `pyproject.toml` comment. **Zero `web/`/`src/` production
lines change**, so the patch-coverage gate is untouched (coverage `source =
["web", "src"]`; test files are outside it).

## W1 E2E design

Route installed **before** `goto`, never `connect_to_server()` (mocked socket =
no live network/CDN, deterministic):

```python
holder, frames = {}, []
def handler(ws_route):
    holder["route"] = ws_route
    ws_route.on_message(lambda m: frames.append(json.loads(m)))
page.route_web_socket("wss://fapi.bitunix.com/**", handler)
page.goto(f"{base_url}/market/")
```

Client frame shape is `{op, args:[{ch, symbol}]}` (verified in
`chart.js::sendSubscribe`). Assert **parsed** `op` + `args[0].ch`, never raw text.

- **Ordering**: bounded-poll until the boot `subscribe(market_kline_1min)` lands;
  `select_option("#interval", "5m")`; `wait_for_function` the 5m REST redraw;
  assert the tail two frames are exactly
  `[("unsubscribe","market_kline_1min"), ("subscribe","market_kline_5min")]`.
  `switchTo` runs synchronously on `change`, so both frames are emitted in order.
- **Bucketing**: with 5m seeded and shown, pick `t = last_time + 300` and
  `route.send({"symbol":"BTCUSDT","ts":t*1000,"data":{"o","h","l","c"}})`;
  `wait_for_function` `len == n+1`; send a second push in the **same** bucket;
  assert length unchanged and last `time` unchanged.

**Anti-flake**: every DOM/series assertion uses `wait_for_function`; the only
sleep is a bounded poll helper (`wait_for_timeout(50)` up to 2s) for the
Python-side frame list — no fixed long sleep, no timing assertion.

## Reconnect decision

**Inspection-only** (`backoff` = `min(1000·2ⁿ,60000)·(0.5+rand)`, one pure
expression). Exposing `backoff` on `window.marketChart` would edit production
`chart.js`, contradicting the test/doc-only boundary; the spec excludes
backoff-timing E2E. R5 marks reconnect inspection-verified; no in-browser timing.

## W2 guard — `tests/test_dependency_guard.py`

Mirror `test_boundary.py`: `ast.walk` roots from `Import` and `ImportFrom` with
`level == 0` (relative imports excluded). Scan `web/**/*.py` + `src/**/*.py`,
skip `__pycache__` and the scanner file.

Allowed = `sys.stdlib_module_names` ∪ declared ∪ local. Local derived: dirs
under `web/` holding `__init__.py` (`accounts`, `config`, `market`, `trading`) +
flat `web/*.py` stems (`credentials`, `manage`, `scheduler`, `worker`) + `src`.
Declared: parse `requirements.txt`, strip version/extras/markers, dist→import
map (`dj-database-url→dj_database_url`, `psycopg[binary]→psycopg`; else
identity). Dry-run against the current tree: **0 offenders**.

Tests: (1) tree passes; (2) positive control (`import django`, `import os`,
`from src...`, a relative import → not flagged); (3) negative control
(`import pandas` → offender); (4) requirements-sync (declared import-roots ==
mapped requirements → adding a requirement without a mapping fails).
`ponytail:` note documents the `TYPE_CHECKING` ceiling (none today).

## SUGGESTION 3

Keep `web/manage.py` in `omit`; add a `pyproject.toml` comment naming
`tests/web/test_manage_boot.py` as the contract. Dropping `omit` would add
uncovered import-time lines (the subprocess is not instrumented) — false
coverage, lower web %. R9 is doc-only; the existing subprocess test already
locks boot behavior. No new test.

## Architecture Decisions

| Decision | Option A | Option B | Choice + rationale |
|---|---|---|---|
| W1 evidence | `route_web_socket` (mocked, deterministic) | spec-mark-only / `page.on("websocket")` observe | **A** — real runtime evidence, no network, no prod edit |
| Reconnect | expose `backoff` on seam | inspection-only | **inspection-only** — prod `chart.js` edit prohibited; pure capped arithmetic |
| `manage.py` omit | drop from `omit` | keep + document | **keep** — dropping measures nothing (subprocess); doc names the real contract |
| Allowlist source | hardcoded roots | derive local + parse requirements | **derive** — new first-party app can't cause false positives; sync test kills drift |

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (Python) | Guard allowlist, sync map, positive/negative controls | `tests/test_dependency_guard.py` (runs in CI) |
| E2E (dev-only) | Frame order on switch; in-place bucketing | `page.route_web_socket` in `test_market_e2e.py` (`-m e2e`) |
| Inspection | Reconnect cap; R9 omit contract | spec R5/R9 wording + `test_manage_boot.py` |

## Migration / Rollout

No migration. E2E is deselected by default (`addopts = "-q -m 'not e2e'"`); CI
never downloads a browser.

## File Changes

| File | Action | Description |
|---|---|---|
| `tests/web/test_market_e2e.py` | Modify | Two `route_web_socket` E2E scenarios + frame/bounded-poll helpers |
| `tests/test_dependency_guard.py` | Create | Runtime-import guard, positive/negative controls, requirements-sync test |
| `pyproject.toml` | Modify | Comment on the `manage.py` omit naming `test_manage_boot.py` |
| `openspec/specs/market-chart/spec.md` | Modified at archive | Delta (R5/R7 wording, R9) merged by sdd-archive |

## Task Breakdown Hint

Single PR, ~150–220 changed lines (E2E ~60, guard ~90, docs ~5). No chaining
needed: `Decision needed before apply: No`; `Chained PRs recommended: No`;
`400-line budget risk: Low`.

## Open Questions

None — reconnect resolved as inspection-only, no production edit.
