# symbol-catalog Specification

## Purpose

Exchange-wide symbol universe for `/market/` (issue #124, F11). Today the chart only
knows `config.SYMBOLS` (`src/config.py:47-49`) and `client.tickers()` with no argument
already returns every pair (`src/client.py:118-120`). This capability projects that
payload down to symbol strings, caches it process-locally, and serves it read-only.
New capability — no prior spec. It MUST NOT add a dependency, an order path, or a
Django import under `src/`.

## Requirements

### Requirement: R1 — Symbol universe fetch

`web/market/catalog.py` MUST provide `list_symbols(client=None, *, now=None)` returning
a `sorted` list of unique symbol strings from `client.tickers()` called with NO
arguments (`client.py:118-120`). It MUST project only the `symbol` field, MUST NOT
cache or return the full ticker payload, and MUST NOT add a dependency.

#### Scenario: Universe is projected and sorted

- GIVEN a stub client returning tickers for `ETHUSDT`, `BTCUSDT`, `BTCUSDT`
- WHEN `list_symbols(client=stub, now=0)` runs
- THEN it returns `["BTCUSDT", "ETHUSDT"]` and the stub received no `symbols` argument

#### Scenario: Framework boundary holds

- GIVEN `web/market/catalog.py`
- WHEN its imports are inspected
- THEN it imports only the stdlib plus `src.client`/`src.config` — no Django model, no `trading`, no `market.views`
- AND `tests/test_boundary.py` stays green (`src/` still imports no Django)

#### Scenario: No dependency added

- GIVEN the change
- WHEN `requirements.txt` is inspected
- THEN it is unchanged

### Requirement: R2 — Process-local TTL cache

The catalog MUST cache the projected list for `CATALOG_TTL_SECONDS = 60` in a
module-level entry keyed by fetch time, with `now` injectable so tests never sleep.
A call within the TTL MUST NOT call upstream. An expired entry MUST refetch. An
upstream failure MUST raise and MUST NOT poison, clear, or replace a previously cached
value.

#### Scenario: Warm cache does not call upstream

- GIVEN a successful fetch at `now=0`
- WHEN `list_symbols(now=59)` is called
- THEN the result is served from cache and the client is not called again

#### Scenario: Expired entry refetches

- GIVEN a cached entry fetched at `now=0`
- WHEN `list_symbols(now=61)` is called with a client returning a new symbol
- THEN upstream is called once and the new list is returned

#### Scenario: Failure does not poison the cache

- GIVEN a list cached at `now=0` and a client that raises `BitunixError`
- WHEN `list_symbols(now=61)` is called
- THEN the error propagates
- AND the cached list is neither cleared nor replaced by the failure

### Requirement: R3 — Read-only endpoint

The system MUST expose `GET /market/api/symbols`, `@login_required` (anonymous → 302
login), GET-only (another verb → 405). Success MUST be `200 {"symbols": [...]}`.
An upstream `BitunixError` or `requests.RequestException` MUST map to `502
{"error": "upstream"}`, mirroring `api_kline` (`views.py:201-204`).

#### Scenario: Authenticated GET returns the universe

- GIVEN a warm catalog and an authenticated session
- WHEN `GET /market/api/symbols` is called
- THEN `200 {"symbols": [...]}` is returned in sorted order

#### Scenario: Anonymous is redirected

- GIVEN an anonymous session
- WHEN the endpoint is called
- THEN a 302 to login is returned

#### Scenario: POST is rejected

- GIVEN an authenticated session
- WHEN `POST /market/api/symbols` is called
- THEN 405 is returned

#### Scenario: Upstream failure is 502

- GIVEN a cold catalog and a client raising `requests.RequestException`
- WHEN the endpoint is called
- THEN `502 {"error": "upstream"}` is returned

### Requirement: R4 — Warm membership check

`symbol_exists(symbol, *, client=None) -> bool` MUST answer from the cached set. When
the cache is warm it MUST NOT perform a network call, so the alerts request path can
use it without adding latency. On a cold cache it MAY fetch.

#### Scenario: Warm check is offline

- GIVEN a warm catalog containing `BTCUSDT`
- WHEN `symbol_exists("BTCUSDT", client=raising_stub)` is called
- THEN it returns `True` and the client is never invoked

#### Scenario: Unknown symbol is false

- GIVEN a warm catalog without `DOGEUSDT`
- WHEN `symbol_exists("DOGEUSDT")` is called
- THEN it returns `False`
