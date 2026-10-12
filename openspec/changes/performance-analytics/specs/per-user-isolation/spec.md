# Delta for per-user-isolation

E1 adds the `/analytics/` read surface and the R14 scoping of its trade reads.
R14.1–R14.4 are unchanged; this delta adds one owned-surface scenario proving the
analytics view honors the contract.

## ADDED Requirements

### Requirement: R14.5 — Analytics view is scoped

The `/analytics/` view MUST read trades ONLY through `Trade.for_user(request.user)`
and MUST NOT use unscoped `<OwnedModel>.objects.<verb>()` queries on any owned
model, including `Trade`. Global market data (`Candle`, `TickerSnapshot`) MAY be
read unscoped, but user trades MUST be scoped before any join; the R14.3 scanner
MUST stay green on `web/trading/`.

#### Scenario: Analytics reads only the caller's trades

- GIVEN user A owns trades and user B owns none
- WHEN B GETs `/analytics/`
- THEN no owned-model query outside `for_user` occurs and B sees no trade data

#### Scenario: Unscoped analytics fixture is flagged

- GIVEN a fixture under the request path calling `Trade.objects.all()` in an analytics-style view
- WHEN the R14.3 guard scans it
- THEN the scanner reports the offender
