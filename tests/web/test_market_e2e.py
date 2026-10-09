"""R5 dev-only E2E smoke: the chart page wires up in a real browser.

DOM-only assertions (no image diffs): the LightweightCharts global is
defined, the chart canvas exists, and the page loads without JS console
errors (WS network errors are tolerated — external dependency).

Run locally: `playwright install chromium` once, then `python -m pytest -m e2e`.
Deselected by default via addopts; CI never downloads a browser.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api", reason="pytest-playwright not installed")

p = pytest.mark.e2e


@pytest.fixture
def seeded_5m_candles(db):
    """Seed persisted 5m candles before any Playwright (sync) context starts."""
    from datetime import UTC, datetime

    from trading.models import Candle

    base = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
    for i in range(30):
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
