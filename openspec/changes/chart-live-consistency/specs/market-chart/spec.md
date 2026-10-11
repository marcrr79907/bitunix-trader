# market-chart Specification (DELTA — chart-live-consistency)

## Purpose

Delta to the existing `market-chart` capability: R5 (live candles) and R8
(infinite scroll) gain the consistency contract — no periodic `setData`, exchange
timestamps, lossless pagination.

## Requirements

### Requirement: R5 — Live candles over browser WS (MODIFIED)

The live candle path MUST use a single writer (`series.update()`). It MUST NOT
issue a periodic full-series `setData()`. The candle bucket timestamp MUST equal
the exchange candle `time` for the selected interval (1w = Monday, 1M = calendar
month); the client MUST NOT invent a divergent timeline. The chart MUST remain
consistent (no flicker, monotonic series) while pushes arrive.

#### Scenario: No periodic setData
- GIVEN the chart streaming
- WHEN pushes arrive over several buckets
- THEN `setData` is not invoked by the stream (spy), only `update`

#### Scenario: Exchange-aligned bucket
- GIVEN a WS push and the exchange candle for the same interval/instant
- WHEN both are turned into chart times
- THEN they are equal (1w and 1M included)

### Requirement: R8 — Infinite-scroll history (MODIFIED)

Loading older pages MUST use `setData` with a **merge** (never replace) so
already-loaded history and the live tip are preserved; the viewport MUST be
preserved (shifted by the prepended count). A live `setData` MUST NOT discard
paginated history.

#### Scenario: Live refetch does not lose paginated history
- GIVEN older pages loaded via scroll
- WHEN the live path advances
- THEN the previously loaded older candles are still present
