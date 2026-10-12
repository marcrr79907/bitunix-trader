# Delta for chart-live-stream

Issue #70 (Fase A1): the candle-close overlay refresh generalizes from the
SMA/EMA pair to EVERY active overlay/pane series. The single-write-path rule is
unchanged: the stream uses `update()` only, never a mid-stream `setData`; a
toggle/param change is a config change and legitimately uses `setData` (same class
as a symbol/interval switch). R6 is MODIFIED.

## MODIFIED Requirements

### Requirement: R6 — Active series reflect the forming/closed candle without deformation

At each bucket close the adapter MUST refresh EVERY active indicator series — the
price overlays (SMA, EMA, Bollinger, VWAP, …) AND the sub-pane series (RSI, MACD,
Stochastic, ATR, Volume) — so their points stay aligned to the candles. The refresh
MUST advance each active series via `update()` of its LAST point and MUST NOT
realign any series via a full-series `setData` that shifts existing points. A
toggle or per-indicator param change is a CONFIG change: it MUST rebuild the request
set and refetch via the history path (`setData`), exactly like a symbol/interval
switch — that is not a mid-stream write. (Previously: refreshed only the SMA/EMA
overlay pair; panes did not exist.)

#### Scenario: Every active series advances on close

- GIVEN the chart with multiple overlays and panes active
- WHEN a candle closes
- THEN each active series' last point is updated via `update()` to time T (aligned)

#### Scenario: No mid-stream setData

- GIVEN the chart streaming with panes active
- WHEN several candles close
- THEN `setData` is not invoked by the close refresh (spy); only `update` is

#### Scenario: Toggle uses the history path

- GIVEN an active chart
- WHEN an indicator toggle or param changes
- THEN the adapter refetches history and applies it via `setData` (allowed config path), with no incremental pane surgery

#### Scenario: No series deforms on refresh

- GIVEN a closed candle at time T
- WHEN overlays/pane series are refreshed
- THEN no existing point moves between bars (only the last point advances)
