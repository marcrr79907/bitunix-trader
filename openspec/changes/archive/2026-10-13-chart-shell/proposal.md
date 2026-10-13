# Proposal: chart-shell (Fase F3, issue #116 — Ola 1)

## Intent

The chart is pinned at 480px (JS) / 460px (CSS), the interval control is a bare `<select>`, the sidebar stacks (never collapses) on small screens, and the last interval is not remembered. F3 delivers a TradingView-style shell — full-height responsive chart, `aria-pressed` interval chips, collapsible sidebar — plus last-interval persistence. All on the MERGED F0/F1 layered ESM: CSS + template + small JS, no `src/` change, no new dep, CSP strict.

## Scope

**In:** full-height chart (`autoSize:true`, drop `height:480`; `#chart` `dvh` height); interval chips from the 14 existing `<option>`s; `<select id="interval">` kept **visually hidden (`clip`, not `display:none`)** so the 15 E2E `select_option` calls stay green (R18, no assertion edits); `<button aria-expanded aria-controls>` collapse ≤820px; `ChartPreference` (UserOwned, OneToOne) + `GET/PUT /market/api/preference` + one additive migration.

**Out:** viewport *width* (keep `max-width:1200px`); a 9th `window.marketChart` key or any `SmcOverlayCore` change; roving-tabindex chips; legend/indicator UI; order surface; `src/`.

## Capabilities

**New:** `chart-shell` — full-height chart, chip group with preserved select, collapsible sidebar.
**Modified:** `market-chart` (R14 host: autoSize); `chart-config` (user-global last-interval preference, distinct from the per-`(user,symbol,interval)` layout).

## Approach

`#chart{height:calc(100dvh - …); min-height:460px}` with a flex-column/`--topbar-h` context. `toolbar.js` chip listener emits the SAME `config:changed` and syncs `select.value` bidirectionally, plus a 3-line toggle. Chips are template-driven; the server still validates via `quotes.INTERVALS`. Persistence mirrors `ChartLayout` (`for_user` + GET/PUT); the no-migration sentinel-symbol alternative is rejected as a design smell — flagged, not defaulted.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `market/chart.html`, `theme.css` | Modified | Chips, hidden select, toggle, `dvh` height, `.panel-collapsed` |
| `market/chart-host.js`, `controllers/toolbar.js`, `main.js` | Modified | `autoSize`; chip↔select sync + toggle; boot pref read/save |
| `trading/models.py` + `migrations/0009_*`; `market/views.py`+`urls.py` | New/Modified | `ChartPreference` (additive) + `/market/api/preference` |
| `tests/web/test_market_api.py`, `test_market_e2e.py` | Modified | Preference contract; ADD-ONLY E2E |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| E2E breakage — 15 `select_option("#interval")` | High | Keep select in DOM (`clip`); chips drive it |
| v5 `autoSize` vs `height:480` / zero-height box | Med-High | Remove option; resolved height; assert canvas bbox |
| Frozen seams (8 keys, `SmcOverlayCore`) | Med | No new key; E2E asserts count = 8 |
| Migration additivity; JS patch coverage | Med | Additive `0009` + `makemigrations --check` + `OWNED_MODELS`; `node --test` + endpoint tests |
| Boot ordering (pref before `start()`) | Med | Default `"1m"` on failure; keep `gen` guard |

## Rollback Plan

**Slice 1:** revert shell commit — restore `height:480`, drop chips/`autoSize`/toggle + added E2E. **Slice 2:** revert persistence + reverse migration; boot falls back to `"1m"`. Isolated, no data/config loss.

## Read-Only Boundary

No order execution; no `src/` change; no new runtime dep; CSP unchanged; no new `window` global; `marketChart` stays 8 keys; `Candle` read-only. Only schema change is the additive `ChartPreference`.

## Dependencies

F0 layered ESM + F1 legend (MERGED); Lightweight Charts v5.2.0 (`autoSize` verified); Node 22 + Playwright.

## Delivery (Feature Branch Chain — 2 slices)

Base = tracker `feat/chart-shell`; child PRs target the tracker.
1. **Shell** — CSS + template + chips + collapse + `autoSize`: ~150 lines, no migration. PR #1 → tracker.
2. **Interval persistence** — model + migration + endpoint + boot read/save + API tests: ~160 lines. PR #2 → PR #1.

- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: Medium

## Success Criteria

- [ ] Chart fills height (bbox asserted); chips toggle `aria-pressed` + switch interval; panel collapses ≤820px; no 375px overflow.
- [ ] `<select>` stays action-able; 15 existing `select_option` calls green, NO assertion edits.
- [ ] Persisted interval restores; failure defaults `"1m"`; per-user isolation enforced.
- [ ] `0009` additive + `makemigrations --check` green; `node --test` + `pytest` green; 8 keys; no `src/` change, no new dep, CSP unchanged.
