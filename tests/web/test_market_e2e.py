"""R5 dev-only E2E smoke: the chart page wires up in a real browser.

DOM-only assertions (no image diffs): the LightweightCharts global is
defined, the chart canvas exists, and the page loads without JS console
errors (WS network errors are tolerated — external dependency).

The two live-candle scenarios mock the exchange socket via
``page.route_web_socket`` (installed BEFORE ``goto``) so frame ordering and
same-bucket updates are asserted deterministically, no live network/CDN.

Run locally: `playwright install chromium` once, then `python -m pytest -m e2e`.
Deselected by default via addopts; CI never downloads a browser.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api", reason="pytest-playwright not installed")

p = pytest.mark.e2e


@pytest.fixture
def seeded_5m_candles(db):
    """Seed persisted 5m candles before any Playwright (sync) context starts."""
    from datetime import UTC, datetime

    from trading.models import Candle

    base = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
    for i in range(250):
        Candle.objects.create(
            symbol="BTCUSDT",
            interval="5m",
            time=base + i * 300,
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
        )


@pytest.fixture
def browser_page(live_server, client, db):
    """A Playwright page carrying the Django session cookie."""
    from django.contrib.auth import get_user_model
    from playwright.sync_api import sync_playwright

    user = get_user_model().objects.create_user(
        email="e2e@example.com", password="pw-123456"
    )
    client.force_login(user)
    cookie = client.cookies["sessionid"]

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": cookie.value,
                    "domain": "localhost",
                    "path": "/",
                }
            ]
        )
        page = context.new_page()
        yield page, live_server.url
        browser.close()


@p
def test_chart_page_wires_up(browser_page):
    page, base_url = browser_page
    errors = []
    page.on(
        "console",
        lambda msg: errors.append(msg.text) if msg.type == "error" else None,
    )

    page.goto(f"{base_url}/market/")
    page.wait_for_timeout(1500)

    chart_global = page.evaluate("() => typeof LightweightCharts")
    assert chart_global == "object"
    canvas_count = page.locator("#chart canvas").count()
    assert canvas_count >= 1
    # Script errors only; failed WS/CSP-network fetches are external noise.
    script_errors = [e for e in errors if "net::" not in e and "WebSocket" not in e]
    assert script_errors == [], f"console errors: {script_errors}"


@p
def test_chart_renders_seeded_candles(seeded_5m_candles, browser_page):
    # R3/R8: with candles in the DB the chart shows them (DB-first payload).
    # Candles are seeded by the fixture (before the Playwright context) because
    # Playwright's sync API runs an event loop that forbids sync ORM calls.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    # Switch the page's interval selector to the persisted interval (DB-first).
    page.select_option("#interval", "5m")
    # The page's JS exposes the series for DOM-only assertions (no image diff).
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    n = page.evaluate("() => window.marketChart.candleSeries.data().length")
    assert n >= 30


@p
def test_chart_infinite_scroll_loads_older_page(seeded_5m_candles, browser_page):
    # R8: reaching the left edge fetches an older page (`before=`) and prepends
    # it, growing the series. DOM/network assertions only (no image diff).
    page, base_url = browser_page
    before_requests = []
    page.on(
        "request",
        lambda r: before_requests.append(r.url) if "before=" in r.url else None,
    )

    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    initial = page.evaluate("() => window.marketChart.candleSeries.data().length")

    # Drive the visible range to the left edge to trigger loadOlder().
    page.evaluate(
        "() => window.marketChart.chart.timeScale().setVisibleLogicalRange("
        "{ from: -1, to: 20 })"
    )
    page.wait_for_function(
        f"() => window.marketChart.candleSeries.data().length > {initial}",
        timeout=10000,
    )
    grown = page.evaluate("() => window.marketChart.candleSeries.data().length")
    assert grown > initial
    assert any("before=" in u for u in before_requests), before_requests


def _poll(page, predicate, timeout_ms=2000, step_ms=50):
    """Bounded poll for a Python-side condition (no fixed long sleep)."""
    waited = 0
    while waited <= timeout_ms:
        if predicate():
            return True
        page.wait_for_timeout(step_ms)
        waited += step_ms
    return predicate()


@p
def test_ws_switch_unsubscribes_before_subscribing(seeded_5m_candles, browser_page):
    # R5: on interval switch the client sends unsubscribe(old) strictly before
    # subscribe(new). Frames are captured from a mocked socket and parsed as
    # JSON — raw-text matching would be brittle and miss field reordering.
    page, base_url = browser_page
    frames = []

    def handler(ws_route):
        ws_route.on_message(lambda m: frames.append(json.loads(m)))

    # Install the route BEFORE goto so the boot socket is intercepted too.
    page.route_web_socket("wss://fapi.bitunix.com/**", handler)
    page.goto(f"{base_url}/market/")

    # Boot: the page subscribes the default 1m channel over the mocked socket.
    booted = _poll(
        page,
        lambda: any(
            f.get("op") == "subscribe" and f["args"][0]["ch"] == "market_kline_1min"
            for f in frames
        ),
    )
    assert booted, f"boot subscribe never arrived: {frames}"

    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )

    ops = [(f["op"], f["args"][0]["ch"]) for f in frames]
    assert ops[-2:] == [
        ("unsubscribe", "market_kline_1min"),
        ("subscribe", "market_kline_5min"),
    ], ops


@p
def test_ws_same_bucket_updates_in_place(seeded_5m_candles, browser_page):
    # R5: two pushes inside one bucket update the FORMING candle in place —
    # the series grows by exactly one bar and the second push does not add a
    # duplicate time.
    page, base_url = browser_page
    holder = {}

    def handler(ws_route):
        holder["route"] = ws_route

    page.route_web_socket("wss://fapi.bitunix.com/**", handler)
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )

    n = page.evaluate("() => window.marketChart.candleSeries.data().length")
    last_time = page.evaluate(
        "() => window.marketChart.candleSeries.data().slice(-1)[0].time"
    )
    t = last_time + 300  # next 5m bucket

    push = {
        "symbol": "BTCUSDT",
        "ts": t * 1000,
        "data": {"o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5},
    }
    holder["route"].send(json.dumps(push))
    page.wait_for_function(
        f"() => window.marketChart.candleSeries.data().length === {n + 1}",
        timeout=5000,
    )

    # Second push in the SAME bucket: replace the forming bar, no new time.
    holder["route"].send(
        json.dumps({**push, "data": {"o": 1.0, "h": 3.0, "l": 0.5, "c": 2.5}})
    )
    page.wait_for_timeout(200)
    after = page.evaluate("() => window.marketChart.candleSeries.data().length")
    last_after = page.evaluate(
        "() => window.marketChart.candleSeries.data().slice(-1)[0].time"
    )
    assert after == n + 1
    assert last_after == t


@p
def test_ws_stream_never_calls_setdata(seeded_5m_candles, browser_page):
    # R5 (fix #68): during the live stream the adapter MUST use update() only.
    # A periodic setData was the root cause of the flicker/phantom candles.
    page, base_url = browser_page
    holder = {}

    def handler(ws_route):
        holder["route"] = ws_route

    page.route_web_socket("wss://fapi.bitunix.com/**", handler)
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )

    # Spy on setData AFTER the initial history load, then drive several pushes.
    page.evaluate(
        "() => { const s = window.marketChart.candleSeries;"
        " window.__setDataCalls = 0; const orig = s.setData.bind(s);"
        " s.setData = function(){ window.__setDataCalls++;"
        " return orig.apply(s, arguments); }; }"
    )
    n = page.evaluate("() => window.marketChart.candleSeries.data().length")
    last_time = page.evaluate(
        "() => window.marketChart.candleSeries.data().slice(-1)[0].time"
    )
    for i in range(1, 5):
        t = last_time + 300 * i
        holder["route"].send(
            json.dumps(
                {
                    "symbol": "BTCUSDT",
                    "ts": t * 1000,
                    "data": {"o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5},
                }
            )
        )
        page.wait_for_function(
            f"() => window.marketChart.candleSeries.data().length === {n + i}",
            timeout=5000,
        )

    calls = page.evaluate("() => window.__setDataCalls")
    assert calls == 0, f"setData called {calls} times during the live stream"
