# Proposal: setup-ledger

Issue **#260** — first link of the measurable-baseline chain (#261 outcomes later).

## Intent

Persist every SMC setup **as it stood at emission** so today's policy becomes
measurable. `find_setups` runs on demand and is discarded, and
`analytics.calibrate` rebuilds history from live upstream with today's code —
not reproducible. Without a baseline, every SL/R:R argument is opinion.

## Scope

### In scope

1. **`Setup` model** (global, `web/trading/models.py`): `symbol`, `interval`,
   `anchor_time` (BigInt, candle OPEN s), `direction`, `entry`, `stop`,
   `take_profit`, `rr`, `score`, `atr`* (nullable), `engine_version`,
   `created_at` (*nullable); `UniqueConstraint(symbol, interval, anchor_time,
   engine_version)` + index; additive `0018`.
2. **`SMC_ENGINE_VERSION`** in `src/smc/config.py`, hand-bumped.
3. **Enriched capture seam**: `find_setups` yields `index`, not `time`, and no
   ATR. Resolved: an additive pure helper in `src/smc/signals.py`
   (`capture_setups`) returning the enriched record, leaving the frozen `Setup`
   and its two callers byte-identical. The Django layer never reimplements the
   chain.
4. **Worker capture** in `run_once`: own `try/except`, candles from `_db_rows`
   (no extra network), `SETUP_CAPTURE_INTERVALS` (env, default `1h`),
   `bulk_create(ignore_conflicts=True)`.

### Out of scope

- **Outcomes** (#261) — separate, recomputable table.
- **Backfill** — none; reconstructed rows break point-in-time.
- **Changing `find_setups`** thresholds or replacing `analytics.calibrate` —
  separate, untouched.
- **Order execution — never.** Read-only repo: no order surface or verbs;
  `test_no_order_surface.py` stays green. A `Setup` records an observation.
- No new dependency, no `src/`→Django import, no UI.

## Capabilities

- **New** `smc-setup-ledger`.
- **Modified** `smc-signals`: version constant + additive helper; scoring and
  frozen `Setup` unchanged.

## Approach

Run the same chain `get_smc_payload` runs over `_db_rows(symbol, interval, None,
N)`. `anchor_time = times[setup.index]`; ATR is `atr(...)[index]`, null when
short. One setup per anchor holds: the latest structure event needs a new closed
candle.

## Affected Areas

`web/trading/models.py` (+`Setup`), `migrations/0018_setup.py` (new, additive),
`src/smc/config.py`, `src/config.py`, `src/smc/signals.py` (helper),
`web/trading/setups.py` (new capture seam), `web/worker.py` (isolated step),
`tests/*`.

## Risks

Ownership leak (Low — global by design, guard green); capture cost (Med — `1h`
default, cap 50); mixed engines (Med — `engine_version`); capture killing
ingestion (Low — own `try/except`); helper drift (Med — one shared chain call).

## Rollback Plan

Revert the worker step first (capture stops, ingestion untouched), then
`setups.py`, the version constant, and the helper. Reversing `0018` drops only
`Setup`; nothing else references it. Never destructive: no existing column, row,
or constraint changes.

## Success Criteria (#260)

- [ ] One cycle persists one `Setup` per `(symbol, interval, anchor)` matching
      the SMC payload; a repeat cycle inserts nothing.
- [ ] A bumped `SMC_ENGINE_VERSION` writes new rows; old rows intact.
- [ ] `atr` matches `src.indicators.atr(...)` at the anchor; `None` when short.
- [ ] `[]` inserts nothing and does not break the cycle.
- [ ] A forced capture exception leaves funding, ticker, candles, private sync,
      and alerts intact.
- [ ] No user FK; `OWNED_MODELS` green; migration tests use `>=`;
      `makemigrations --check` green.

## Changed-lines forecast

~230–270 lines. Single PR — `400-line budget risk: Low`.
