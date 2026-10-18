"""E2E for the F10 alert layer (bell + dialog + markers).

Readiness-gated DOM + captured-network assertions only — no pixels (#149).
The bell is JS-built into ``#chart``; the dialog, ``#alert-status`` and the
interval reason are static markup. Markers are canvas, so their count/state is
asserted through the accessible ``#alert-status[aria-live]`` summary that the
controller derives from the same rule list the marker core projects, plus the
captured GET for the active pair. The marker payload itself is pinned by the
node tests (``alert-markers-core.test.js``, ``alerts-controller.test.js``).
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import pytest

pytest.importorskip("playwright.sync_api", reason="pytest-playwright not installed")

p = pytest.mark.e2e


_SEED_BASE = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
_FIRED = datetime(2025, 1, 1, 1, 0, tzinfo=UTC)


def _seed_5m(symbol: str, *, phase: float = 0.0) -> None:
    """250 varied 5m candles so the crosshair has a real price coordinate."""
    from trading.models import Candle

    for i in range(250):
        close = 100.0 + 4.0 * math.sin(i / 3.0 + phase) + 3.0 * math.sin(i / 23.0)
        open_ = close - 0.6 * math.cos(i / 3.0 + phase)
        Candle.objects.create(
            symbol=symbol,
            interval="5m",
            time=_SEED_BASE + i * 300,
            open=round(open_, 4),
            high=round(max(open_, close) + 1.0, 4),
            low=round(min(open_, close) - 1.0, 4),
            close=round(close, 4),
        )


@pytest.fixture
def seeded_5m_alert(db):
    """250 varied 5m candles on the pair the tests switch to (no rules)."""
    _seed_5m("BTCUSDT")


@pytest.fixture
def seeded_alerts(e2e_user, db):
    """One fired + two armed price rules on the pair the test switches to."""
    from trading.models import AlertRule

    _seed_5m("BTCUSDT")
    AlertRule.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        interval="5m",
        condition={"type": "price", "op": "above", "level": 200.0},
        is_active=True,
        last_fired_at=_FIRED,
    )
    for level in (150.0, 50.0):
        AlertRule.objects.create(
            user=e2e_user,
            symbol="BTCUSDT",
            interval="5m",
            condition={"type": "price", "op": "below", "level": level},
            is_active=True,
        )
    return e2e_user


def _wait_ready(page):
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true", timeout=10000
    )


def _wait_candles(page):
    page.wait_for_function(
        "() => window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )


def _begin(page, url, interval="5m"):
    page.goto(url)
    _wait_ready(page)
    page.select_option("#interval", interval)
    _wait_candles(page)


def _hover_plot(page):
    """Move the pointer over the plot until the bell is visible."""
    canvas = page.locator("#chart canvas").first
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
    page.wait_for_function(
        "() => { const b = document.getElementById('chart-alert-bell');"
        " return b && !b.hidden; }",
        timeout=5000,
    )
    return page.locator("#chart-alert-bell")


@p
def test_bell_apply_posts_one_price_alert(seeded_5m_alert, browser_page):
    page, base_url = browser_page
    posts = []
    page.on(
        "request",
        lambda r: (
            posts.append(r)
            if r.method == "POST" and "/market/api/alerts" in r.url
            else None
        ),
    )
    _begin(page, f"{base_url}/market/")

    bell = _hover_plot(page)
    assert bell.get_attribute("aria-label").startswith("Create price alert at ")
    bell.click()

    page.wait_for_function(
        "() => document.getElementById('alert-dialog').open === true", timeout=5000
    )
    level = page.locator("#alert-level").input_value()
    assert float(level) > 0
    op = page.locator("#alert-op").input_value()
    assert op in ("above", "below")

    page.locator('#alert-dialog button[value="ok"]').click()
    page.wait_for_function(
        "() => document.getElementById('alert-dialog').open === false", timeout=5000
    )
    page.wait_for_timeout(500)

    assert len(posts) == 1, [r.url for r in posts]
    body = json.loads(posts[0].post_data or "{}")
    assert body["symbol"] == "BTCUSDT"
    assert body["interval"] == "5m"
    assert body["condition"] == {"type": "price", "op": op, "level": float(level)}
    # The summary reflects the created rule (canvas markers are not inspectable).
    page.wait_for_function(
        "() => /\\d+ alerts?:.*armed/.test("
        "document.getElementById('alert-status').textContent)",
        timeout=5000,
    )
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8


@p
def test_cancel_writes_nothing_and_returns_focus(seeded_5m_alert, browser_page):
    page, base_url = browser_page
    writes = []
    page.on(
        "request",
        lambda r: (
            writes.append(r)
            if r.method in ("POST", "PUT") and "/market/api/alerts" in r.url
            else None
        ),
    )
    _begin(page, f"{base_url}/market/")
    _hover_plot(page).click()
    page.wait_for_function(
        "() => document.getElementById('alert-dialog').open === true", timeout=5000
    )
    page.keyboard.press("Escape")
    page.wait_for_function(
        "() => document.getElementById('alert-dialog').open === false", timeout=5000
    )
    page.wait_for_timeout(300)
    assert writes == [], [r.url for r in writes]
    assert page.evaluate("() => document.activeElement.id") == "chart"


@p
def test_markers_summary_and_get_for_the_active_pair(seeded_alerts, browser_page):
    page, base_url = browser_page
    gets = []
    page.on(
        "request",
        lambda r: (
            gets.append(r.url)
            if "GET" == r.method and "/market/api/alerts" in r.url
            else None
        ),
    )
    _begin(page, f"{base_url}/market/")

    page.wait_for_function(
        "() => document.getElementById('alert-status').textContent"
        " === '3 alerts: 1 fired, 2 armed'",
        timeout=10000,
    )
    assert any("symbol=BTCUSDT" in u and "interval=5m" in u for u in gets), gets
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8


@p
def test_bell_is_disabled_on_a_non_evaluable_interval(seeded_5m_alert, browser_page):
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.select_option("#interval", "3d")
    page.wait_for_function(
        "() => window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    bell = _hover_plot(page)
    assert bell.is_disabled()
    assert bell.get_attribute("aria-describedby") == "alert-interval-reason"
    reason = page.locator("#alert-interval-reason").inner_text()
    assert "3d" in reason
