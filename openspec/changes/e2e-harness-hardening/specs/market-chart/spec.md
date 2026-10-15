# Delta for market-chart

Issue #149 (DEBT-8) — E2E readiness note for R5's dev-only verification. No production behavior, no new dependency.

## ADDED Requirements

### Requirement: R23 — E2E readiness for the WS verification scenarios

The dev-only E2E scenarios verifying R5 (`Forming candle updates in place`, `Switch unsubscribes before subscribing`, `Stale-channel frame during switch is dropped`, `Valid-channel frame still applies`) MUST be readiness-gated: each MUST await boot readiness before switching interval or injecting frames, and MUST NOT rely on a retry. The `page.route_web_socket` mock and its frame-ordering assertions MUST be unchanged.

#### Scenario: R5 E2E scenarios wait for readiness
- GIVEN the R5 E2E scenarios in `tests/web/test_market_e2e.py`
- WHEN each test enters its switch/inject phase
- THEN it has awaited `ready` first, and the mocked frame-ordering assertions run unchanged
