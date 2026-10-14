# Proposal: frontend-regression-tests

## Intent

F1 (chart-legend), F2 (chart-indicator-settings), F3 (chart-shell) shipped green, but 10
scenarios were proven **only by throwaway session probes** — no test guards them
(DEBT-2/3/4, #143/#144/#145). Commit those probes so they cannot silently regress.

## Scope

**In:** tests only — 4 node asserts, 7 E2E, 1 isolation extend, 1 size guard, mapped per
issue. Reuse existing fixtures/seams (`browser_page`, `seeded_5m_candles`,
`route_web_socket`, 8-key `window.marketChart`). Exact (not `>=1`) assertions, per #143d.

**Out:** any production file (`web/market/templates/**`, `views.py`, `quotes.py`,
`theme.css`, `requirements.txt`, CSP) — read-only boundary; any spec change; any new dep;
a 9th seam key; refactoring `chart-host.js` (DEBT-5 / #146).

## Capabilities

**New/Modified:** None. Specs already carry these scenarios; test evidence only.

## Approach

- **#143 (F1 legend):** node import-purity of `legend-core.js`; E2E re-subscribe across a
  second `chart:built`; `aria-live` idle states (not per-move); exact 3 legend rows.
- **#144 (F2 settings):** rebuild-count `== 1` wrapping the CDN global
  `LightweightCharts.createChart` (no seam key); legend style-independence by **source
  purity** (no `styles`/`priceFormat`); isolation A≠B; module-size guard.
- **#145 (F3 shell):** keyboard on `.interval-chip` + `aria-pressed`; `#chart` follows
  container resize (no re-boot); desktop >820px layout.

**W4 (locked):** guard **CEILING = 300**, allowlist exempting `chart-host.js` (326 lines),
annotated referencing DEBT-5 (#146) — fails any *other* module >300, blocks growth.

## Affected Areas

- `tests/js/legend-core.test.js` — Modified (purity LC2 + W3).
- `tests/web/test_market_e2e.py` — Modified (7 E2E).
- `tests/web/test_module_size_guard.py` — New (R14 guard, W4).
- `tests/web/test_isolation.py` — Modified (style A≠B, W5).

## Risks

- **Vacuous passes (Med):** exact counts/labels, not `>=1`.
- **Purity-grep comment false positive (Low):** imports only / strip comments.
- **E2E flake, aria-live debounce (Med):** bounded `wait_for_function`, no sleeps.
- **Frozen 8-key seam (Low):** wrapper on the global, not the seam.
- **E2E dev-only, not in CI (High):** accepted.

## Rollback Plan

Delete `test_module_size_guard.py`; restore `legend-core.test.js`, `test_market_e2e.py`,
`test_isolation.py`. Zero production impact.

## Dependencies & Read-Only Boundary

pytest-playwright 1.62 + chromium, Node 22 `node:test`; no new dep. No order execution; no
`src/` change; no production change; CSP and the 8-key seam unchanged.

## Delivery (Feature Branch Chain — 3 slices)

Base = tracker `feat/frontend-regression-tests`.
- **S1 #143** — purity + 3 legend E2E: ~125 lines.
- **S2 #144** — purity/rebuild/isolation + size guard: ~150 lines.
- **S3 #145** — 3 shell E2E: ~120 lines.
Each maps 1:1 to an issue.
Decision needed before apply: No · Chained PRs: Yes · 400-line budget risk: Low

## Success Criteria

- [ ] All 10 scenarios have a committed test with **exact** assertions.
- [ ] W4 guard passes at CEILING=300 with `chart-host.js` allowlisted; fails a synthetic
      >300 module.
- [ ] `node --test` + `pytest -m e2e -p no:randomly` green; ruff clean.
- [ ] No production file changed; `marketChart` still 8 keys; CSP unchanged.
