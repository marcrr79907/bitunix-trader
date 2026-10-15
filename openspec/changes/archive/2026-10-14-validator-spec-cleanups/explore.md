# Explore: validator-spec-cleanups (issue #147, DEBT-6 — P2)

## Purpose

Reconcile four deferred, non-blocking warnings left by three archived changes
(chart-config W3/W4, smc-range W2, alert-rules W1, smc-zones W4). Read-only,
no new runtime deps, no observable behavior change (except possibly one explicit
new 400). Mostly spec/doc; the only possible code lives in `web/market/quotes.py`.

## Current State

### W3/W4 — chart-config, `parse_layout_indicators`

`web/market/quotes.py::parse_layout_indicators` (L288) validates a layout's
JSON list: each `{token, params?, style?}` entry. Token MUST be in `REGISTRY`;
`params` is validated key-by-key by `_validate_layout_params` (L319);
`style` by `_validate_layout_style`. Duplicate tokens are silently dropped.

Two holes, both confirmed by the chart-config verify report probes:

- **W3 — cross-token params accepted.** `_validate_layout_params(token, params)`
  validates each key against the **global** `_INT_PARAMS`/`_FLOAT_PARAMS` sets
  (L324-333), never against the *token's* relevant keys. So
  `[{"token":"ema","params":{"sma_len":9}}]` is **accepted and stored verbatim**.
  The `ema` builder reads `ema_len` (default 20) and ignores `sma_len` →
  rendering unaffected; the stored JSON merely carries a meaningless key.
- **W4 — legacy tokens accepted.** `sma20`/`ema20`/`rsi14` remain in the server
  `REGISTRY` for kline back-compat, so `[{"token":"sma20"}]` is **accepted**. But
  the JS adapter's `REGISTRY` (`web/market/templates/market/chart-host.js` L15-55)
  and the toggles (`chart.html` L42-60) only know `sma`/`ema`/`rsi` (+ others).
  A stored legacy token returns 200 on GET, but `applyLayout` unchecks every
  toggle and `buildChart` renders no indicator series — **candles still render**
  (degraded, not blank). No current UI path stores legacy tokens (toggles emit
  `sma`/`ema`; the debounced PUT builds from `state.indicators`).

Both are reachable only via a **hand-crafted PUT** (or a layout stored by a
pre-A2 client). No UI path emits either shape today.

Downstream trace of a stored legacy/cross-token layout:
`GET /market/api/layout` → 200 verbatim → `controllers/indicators.js::applyLayout`
→ toggles driven by `token` only (legacy token matches no toggle → all unchecked);
`params` only applied to matching `data-token` inputs (cross-token key has no
matching input → ignored). `history.js` adds query params from `state.params`
for selected tokens only. Net: no crash, candles render, the indicator is dropped.

### W2 — smc-range, `classify_price(price, None)`

`src/smc/range.py::classify_price` (L47) returns `"equilibrium"` when `range_ is
None` (L53-54). Confirmed. The canonical `openspec/specs/smc-range/spec.md` R2
documents only the three comparison cases; the `None` case is absent from the
requirement, its scenarios, and the edge-case matrix. `tests/test_smc_range.py`
L73-75 already asserts the behavior (`classify_price(101.0, None) ==
"equilibrium"`). Doc-only gap.

### W1 — alert-rules, `direction` prose

`openspec/changes/archive/2026-10-12-alert-rules/design.md` L68 documents the
`smc_setup` schema with `direction":"long"|"short"|"any"` and lists `direction`
under `parse_condition` raises (L80-83), but the code and the canonical spec
disagree on whether `direction` is REQUIRED:

- Canonical spec `openspec/specs/alert-rules/spec.md` R2 (L56): `smc_setup`
  requires `direction` (`long|short|any`); the table's Required-keys column
  implies it is mandatory. Note: R2's "Required keys" column lists
  `direction`; `min_score` defaults.
- Implementation `src/alert_rules.py::_parse_smc_setup` (L91-98): `direction =
  condition.get("direction")`; `if direction not in _DIRECTIONS: raise
  ValueError`. **Explicit `direction` is required** — absent → `ValueError`.
- `tests/test_alert_rules.py` L166 asserts `{"type":"smc_setup"}` (no direction)
  **raises**; L107 asserts explicit `direction:"any"` parses.

So spec + code agree: explicit `direction` is required. The **design prose is
stale** — it reads as if `direction` were optional with a default, which is what
the alert-rules W1 warning flagged. The archived `design.md` is the only
mismatched artifact; canonical spec and code are already coherent.

**Archive immutability caveat:** `openspec-convention.md` L103 states "The
archive is an AUDIT TRAIL — never delete or modify archived changes." Editing
`archive/2026-10-12-alert-rules/design.md` contradicts that convention. The
`archive-report.md` carry-forward already says "design.md prose is stale and
unreconciled — fix only if the design is reused." So the reconciliation belongs
in the **canonical spec** (a clarifying note in `alert-rules` R2), NOT in the
archived design. This is a decision to confirm with the user (see Open Questions).

### W4 — smc-zones, sweep look-ahead

`src/smc/zones.py::find_liquidity_sweeps` (L148) consumes **confirmed** B1
swings. `src/smc/swings.py::find_swings` already stops the scan at `n - right`
(L43) so trailing unconfirmed pivots are never emitted — a swing at index `s`
is only confirmed `right` (=2) bars later. `find_liquidity_sweeps` iterates
`t` and considers any `s` with `s.index <= t` and `t - s.index <= lookback`
(L174). Because B1 only ever hands back **confirmed** swings, a bar `t` can in
principle "see" a swing whose confirmation bar (`s.index + right`) is *after*
`t` only when `t` itself lies within `right` bars before confirmation — i.e. a
≤2-bar edge effect. There is no explicit `s.index + right <= t` guard; the
simplification is intentional (documented in the verify/archive reports).

Canonical `openspec/specs/smc-zones/spec.md` R4 (L112-121) documents the sweep
condition, the lookback window, most-recent-per-side, and ordering, but says
nothing about the confirmation/look-ahead nuance. `tests/test_smc_zones.py`
L233+ covers empty/mismatched/stale/recent but not the confirmation edge.
Doc-only gap (the behavior is a documented simplification, not a defect).

## Affected Areas

- `web/market/quotes.py` — `parse_layout_indicators` (L288), `_validate_layout_params` (L319); the only possible code change.
- `openspec/specs/smc-range/spec.md` — R2: add the `None → "equilibrium"` case (doc).
- `openspec/specs/alert-rules/spec.md` — R2: reinforcing note that `direction` is explicitly required (doc), OR archive design edit (see decision).
- `openspec/specs/smc-zones/spec.md` — R4: document the ≤2-bar confirmation/look-ahead nuance (doc).
- `openspec/specs/chart-config/spec.md` — R2: if the W3/W4 choice is DOCUMENT, add the accept-and-ignore clause; if REJECT, add the 400 clause.
- `tests/web/test_market_api.py` — `parse_layout_indicators` unit tests (L1050+); extend only if code changes.
- `tests/test_smc_range.py`, `tests/test_smc_zones.py` — already cover the runtime behavior; no test change required for doc-only points.

## W3/W4 Decision — REJECT vs DOCUMENT

### Option A — REJECT (tighten the validator, 400)

- **W3:** key cross-check — only accept params the token's builder reads
  (`sma→{sma_len}`, `ema→{ema_len}`, `rsi→{rsi_len}`, `bollinger→{bb_len,bb_std}`,
  `macd→{macd_fast,macd_slow,macd_signal}`, `stochastic→{stoch_k,stoch_d}`,
  `atr→{atr_len}`, `vwap/volume→∅`).
- **W4:** restrict layout tokens to the adapter vocabulary (`sma/ema/rsi/bollinger/
  vwap/macd/stochastic/atr/volume`) — exclude `sma20/ema20/rsi14`.
- Pros: closes both holes; stored data becomes self-consistent; no silent
  no-op params.
- Cons: **breaking on previously-accepted input.** Any hand-crafted PUT now
  400s; a layout already stored with a legacy token still GETs 200 (GET does not
  re-validate) but any subsequent PUT of that same set 400s. Behavior change.

### Option B — DOCUMENT (accept-and-ignore, no code)

- Keep `parse_layout_indicators` as-is; add an explicit clause to chart-config
  R2 stating that a cross-token param key and a legacy token are accepted and
  stored verbatim; unknown param *keys* still 400; a legacy token renders
  degraded (candles only, no indicator series).
- Pros: **zero behavior change**, no existing layout breaks, smallest diff.
- Cons: the API contract tolerates meaningless data; "silently ignore" stays.

### Option C — silently-drop (reject-free normalization)

- Strip unknown/cross-token param keys and drop legacy tokens on parse.
- Cons: **behavior change** to stored JSON (round-trip no longer verbatim —
  contradicts R2's "stored verbatim (no defaults injected)" and the R1
  JSON-round-trip scenario). Rejected.

### Recommendation — **Option B (DOCUMENT), no code change**

Rationale: the issue explicitly offers "reject (400) **or** document that they
are ignored." Both holes are reachable only via hand-crafted input; no UI path
emits them. A 400 on previously-accepted input is a real behavior change with
data-migration risk (already-stored layouts) for a non-defect. The change is
scoped "sin cambio funcional". DOCUMENT keeps patch 100% trivially (no code),
preserves stored-data compatibility, and closes the warning by making the
contract explicit. **Recommend Option B; REJECT is available if the user wants
to harden the boundary now** (see Open Questions).

## Per-Point Plan

| Point | Decision | Code? | Test? | Target |
|-------|----------|-------|-------|--------|
| **W3** cross-token params | DOCUMENT (recommended) | No | No | chart-config R2 prose: cross-token param accepted+ignored |
| **W4** legacy tokens | DOCUMENT (recommended) | No | No | chart-config R2 prose: legacy token accepted, renders degraded |
| **W2** `classify_price(price, None)` | Doc-only | No | Already covered (`test_smc_range.py` L73) | smc-range R2: add the `None → "equilibrium"` case + edge-matrix row |
| **W1** `direction` prose | Doc-only reconciliation | No | Already covered (`test_alert_rules.py` L166) | Prefer: note in canonical `alert-rules` R2 (archive design is frozen) |
| **W4** sweep look-ahead | Doc-only | No | Already covered | smc-zones R4: document the ≤2-bar confirmation nuance |

If the user picks REJECT for W3/W4, the plan for those two rows becomes:
code in `quotes.py` (`_validate_layout_params` token-scoped key set +
`parse_layout_indicators` token allow-list), plus unit tests and chart-config
R2 prose updated to the 400 contract; patch must be 100%.

## Test Needs

- **Doc-only points (current recommendation):** none. The runtime behavior is
  already asserted: `test_smc_range.py::test_classify_price_none_range_is_equilibrium`
  (W2), `test_alert_rules.py` L166 (W1), `test_smc_zones.py` empty/stale/most-recent
  (W4). Patch gate is unaffected (no code lines changed).
- **If REJECT chosen (W3/W4):** new `pytest.raises(ValueError)` cases in
  `tests/web/test_market_api.py` (cross-token key on `ema`/`rsi`; legacy token
  `sma20`) added to the existing `test_parse_layout_indicators_rejects_bad_input`
  parametrization, plus patch 100% on `quotes.py`.

## Open Questions / Decisions

1. **W3/W4: REJECT or DOCUMENT?** (THE decision.) Recommendation: DOCUMENT
   (Option B) — non-breaking, no code, matches "sin cambio funcional". Confirm.
2. **W1: edit the archived `design.md`, or add a note to the canonical spec?**
   Recommendation: **canonical spec** — the archive is an audit trail
   (`openspec-convention.md` L103) and the archive-report itself says to fix the
   design "only if reused". Confirm.
3. **W4 sweeps doc scope:** a one-line R4 note + edge-matrix row is enough, or
   should R4 gain an explicit "confirmed-swings-only, ≤2-bar edge" requirement
   clause? Recommendation: note + edge row.
4. **Package as one change or split?** All four points are small and share the
   same read-only/doc nature. Recommendation: single change, single PR.

## Risks

- **Breaking 400** if REJECT is chosen: an existing stored layout (or a
  hand-crafted PUT) that previously returned 200 starts returning 400. No UI
  path emits such input, but the contract changes. (Avoided by DOCUMENT.)
- **Archived-doc edit** (W1): editing `archive/` violates the audit-trail
  convention; prefer the canonical spec note.
- **Patch coverage:** if `quotes.py` changes, diff-cover `--fail-under=100`
  forces a test for every new line. Doc-only keeps the gate trivially green.
- **Scope creep:** "document the cross-token/legacy tolerance" is close to
  blessing a hole; keep the prose explicitly framed as "reachable only via
  hand-crafted input; no UI path emits it".

## Proposed PR Shape + Size

**Single PR, small, mixed docs (+ optional tiny code).** Confirmed.
- Doc-only (recommended): 4 spec files edited (chart-config R2, smc-range R2,
  alert-rules R2, smc-zones R4) — well under the 400-line review budget
  (`~40-80` added lines, 0 code). One PR.
- If REJECT chosen: adds a ~15-line `quotes.py` change + ~4 test cases +
  chart-config R2 rewrite → still one PR, still far under budget.
- No chain needed (`Chained PRs recommended: No`, `400-line budget risk: Low`).

## Ready for Proposal

**Yes.** The one sub-decision needing a user call is W3/W4 REJECT-vs-DOCUMENT;
the recommendation (DOCUMENT) is safe and default-able. W1's archive-vs-canonical
question also needs a one-line confirmation.

## Skill Resolution

`paths-injected` — 3 skills loaded (`sdd-explore`, `_shared/sdd-phase-common`,
`_shared/openspec-convention`).
