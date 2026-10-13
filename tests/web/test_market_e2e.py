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
import math
from datetime import UTC, datetime

import pytest

pytest.importorskip("playwright.sync_api", reason="pytest-playwright not installed")

p = pytest.mark.e2e

# Boot key is (SYMBOLS[0], "1m") = (BTCUSDT, "1m"); 1m is NOT persisted, so
# pinning a deterministic window requires switching to a persisted interval.
_SEED_BASE = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())


def _seed_5m(symbol: str, *, amp: float = 4.0, phase: float = 0.0) -> None:
    """Persist 250 deterministic VARIED 5m candles for ``symbol``.

    Varied OHLC (not a constant close) is required so the RSI/MACD panes and
    the SMC chain have real signal to compute over the DB window — a constant
    series yields an all-``None`` RSI and no swings/structure/zones. Seeding
    happens BEFORE any Playwright context (sync ORM rule).
    """
    from trading.models import Candle

    for i in range(250):
        close = 100.0 + amp * math.sin(i / 3.0 + phase) + 3.0 * math.sin(i / 23.0)
        open_ = close - 0.6 * math.cos(i / 3.0 + phase)
        high = max(open_, close) + 1.0
        low = min(open_, close) - 1.0
        Candle.objects.create(
            symbol=symbol,
            interval="5m",
            time=_SEED_BASE + i * 300,
            open=round(open_, 4),
            high=round(high, 4),
            low=round(low, 4),
            close=round(close, 4),
        )


@pytest.fixture
def seeded_5m_candles(db):
    """Seed persisted, VARIED 5m candles before any Playwright context starts."""
    _seed_5m("BTCUSDT")


@pytest.fixture
def seeded_eth_5m_candles(db):
    """Seed a distinct persisted 5m window for the switch target (ETHUSDT)."""
    _seed_5m("ETHUSDT", phase=1.0)


@pytest.fixture
def e2e_user(db):
    """The Playwright session user (shared so layout seeds target the same row)."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="e2e@example.com", password="pw-123456"
    )


@pytest.fixture
def browser_page(live_server, client, e2e_user):
    """A Playwright page carrying the Django session cookie."""
    from playwright.sync_api import sync_playwright

    client.force_login(e2e_user)
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


@pytest.fixture
def saved_layout(e2e_user):
    """Seed a persisted layout BEFORE any Playwright context starts.

    Boot uses ``(SYMBOLS[0], "1m")`` = ``(BTCUSDT, "1m")``. A non-default set
    (SMA len 50 + MACD, EMA/RSI off) makes the restore observable in the DOM.
    """
    from trading.models import ChartLayout

    ChartLayout.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        interval="1m",
        indicators=[{"token": "sma", "params": {"sma_len": 50}}, {"token": "macd"}],
    )
    return e2e_user


@pytest.fixture
def per_interval_layouts(e2e_user):
    """Two distinct layouts for the SAME symbol, different intervals.

    Proves ``switchTo`` loads the target chart's layout: 1m = SMA only,
    5m = RSI only. Seeded before the Playwright context (sync ORM rule).
    """
    from trading.models import ChartLayout

    ChartLayout.objects.create(
        user=e2e_user, symbol="BTCUSDT", interval="1m", indicators=[{"token": "sma"}]
    )
    ChartLayout.objects.create(
        user=e2e_user, symbol="BTCUSDT", interval="5m", indicators=[{"token": "rsi"}]
    )
    return e2e_user


# --- /analytics/ E2E (AS3/AS4) ----------------------------------------------
#
# DOM-only assertions (no image diffs). Trades are seeded for user A BEFORE any
# Playwright context (sync ORM rule). User B owns nothing: A sees the inline
# SVG charts + breakdown/calibration sections, B sees the empty state and none
# of A's symbols. Self-contained contexts (cookies are per-context) so A and B
# are exercised in one test with no shared session.


@pytest.fixture
def analytics_trades(db):
    """Seed a real trade set for the E2E session user BEFORE the browser opens."""
    from django.contrib.auth import get_user_model
    from trading.models import Trade

    user = get_user_model().objects.create_user(
        email="e2e-analytics@example.com", password="pw-123456"
    )
    Trade.objects.create(
        user=user,
        trade_id="AN1",
        symbol="BTCUSDT",
        side="BUY",
        qty=1.0,
        realized_pnl=10.0,
        fee=0.0,
        ctime=1_700_000_000_000,
    )
    Trade.objects.create(
        user=user,
        trade_id="AN2",
        symbol="ETHUSDT",
        side="SELL",
        qty=2.0,
        realized_pnl=-5.0,
        fee=0.0,
        ctime=1_700_003_600_000,
    )
    return user


def _analytics_cookie(user):
    """A fresh session cookie for ``user`` (its own client — no clobbering)."""
    from django.test import Client

    client = Client()
    client.force_login(user)
    return {
        "name": "sessionid",
        "value": client.cookies["sessionid"].value,
        "domain": "localhost",
        "path": "/",
    }


@p
def test_analytics_e2e_charts_and_isolation(
    live_server, analytics_trades, user_b, monkeypatch
):
    # Signals come from the network seam; stub it (no upstream in E2E).
    from trading import views

    monkeypatch.setattr(views, "extract_signals", lambda symbol, ctimes: [])

    cookie_a = _analytics_cookie(analytics_trades)
    cookie_b = _analytics_cookie(user_b)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            # User A: charts + breakdown + calibration render.
            ctx_a = browser.new_context()
            ctx_a.add_cookies([cookie_a])
            page_a = ctx_a.new_page()
            page_a.goto(f"{live_server.url}/analytics/")
            assert page_a.locator("svg[role='img']").count() >= 2
            assert page_a.locator("table").count() >= 3  # hour/symbol/calibration
            body_a = page_a.content()
            assert "BTCUSDT" in body_a
            assert "Calibration" in body_a

            # User B: empty state, none of A's data.
            ctx_b = browser.new_context()
            ctx_b.add_cookies([cookie_b])
            page_b = ctx_b.new_page()
            page_b.goto(f"{live_server.url}/analytics/")
            body_b = page_b.content()
            assert "No trades yet" in body_b
            assert "BTCUSDT" not in body_b
            assert page_b.locator("table").count() == 0
        finally:
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


def _wait_ready(page):
    """Wait for boot to finish: layout applied + chart built (DOM seam)."""
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )


@p
def test_boot_restores_saved_layout(saved_layout, browser_page):
    # R4 (issue #71): a persisted layout wins over the DOM defaults on boot —
    # the toggle panel reflects the saved set AND the chart rebuilds to match.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    # Saved: SMA on (len 50), MACD on; EMA/RSI off (defaults are on).
    assert page.locator('.indicator-toggle[value="sma"]').is_checked()
    assert page.locator('.indicator-toggle[value="macd"]').is_checked()
    assert not page.locator('.indicator-toggle[value="ema"]').is_checked()
    assert not page.locator('.indicator-toggle[value="rsi"]').is_checked()
    # The saved param restores into its editable input.
    assert page.locator('.indicator-param[data-token="sma"]').input_value() == "50"
    # The MACD pane only exists if the saved layout drove the rebuild.
    assert page.evaluate(
        "() => !!(window.marketChart.panes && window.marketChart.panes.macd)"
    )


@pytest.fixture
def saved_token_layout(e2e_user, request):
    """Seed a single param-driven overlay BEFORE the Playwright context."""
    from trading.models import ChartLayout

    token, param = request.param
    ChartLayout.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        interval="1m",
        indicators=[{"token": token, "params": {param: 50}}],
    )
    return token, param


@pytest.mark.parametrize(
    "saved_token_layout",
    [("sma", "sma_len"), ("ema", "ema_len")],
    indirect=True,
)
@p
def test_saved_sma_ema_length_uses_server_token(saved_token_layout, browser_page):
    # R6: the adapter's REGISTRY keys the param-driven server tokens ``sma``/
    # ``ema`` (not ``sma20``/``ema20``) so a saved length is actually requested.
    token, param = saved_token_layout
    page, base_url = browser_page
    klines = []
    page.on(
        "request",
        lambda r: klines.append(r.url) if "/market/api/kline" in r.url else None,
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    requested = any(f"indicators={token}" in u and f"{param}=50" in u for u in klines)
    assert requested, klines


@p
def test_fetch_failure_falls_back_to_dom_defaults(browser_page):
    # R4: a failing layout fetch MUST fall back to the DOM defaults — never a
    # blank chart. The preset checkboxes stay the source of truth.
    page, base_url = browser_page
    page.route("**/market/api/layout?*", lambda route: route.abort())
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    assert page.locator('.indicator-toggle[value="sma"]').is_checked()
    assert page.locator('.indicator-toggle[value="ema"]').is_checked()
    assert page.locator('.indicator-toggle[value="rsi"]').is_checked()


@p
def test_toggle_fires_one_debounced_put(saved_layout, browser_page):
    # R5: a toggle change debounce-saves exactly one PUT carrying the active
    # symbol+interval, and the saved payload reflects the new selection.
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if r.method == "PUT" and "/market/api/layout" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    puts.clear()  # ignore any boot-time traffic
    page.locator('.indicator-toggle[value="rsi"]').check()
    # Debounce (~500 ms) then one PUT; a second quick toggle must not add one.
    page.wait_for_timeout(1200)
    assert len(puts) == 1, [p.url for p in puts]
    body = json.loads(puts[0].post_data or "{}")
    assert body["symbol"] == "BTCUSDT"
    assert body["interval"] == "1m"
    tokens = [i["token"] for i in body["indicators"]]
    assert "rsi" in tokens


@p
def test_switch_loads_target_layout(per_interval_layouts, browser_page):
    # R4: switching interval loads THAT chart's layout before history — 1m is
    # SMA-only, 5m is RSI-only, same symbol.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    assert page.locator('.indicator-toggle[value="sma"]').is_checked()
    assert not page.locator('.indicator-toggle[value="rsi"]').is_checked()

    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.panes"
        " && window.marketChart.panes.rsi"
        " && window.marketChart.panes.rsi.rsi.data().length > 0",
        timeout=10000,
    )
    assert page.locator('.indicator-toggle[value="rsi"]').is_checked()
    assert not page.locator('.indicator-toggle[value="sma"]').is_checked()


@p
def test_selected_indicator_renders_a_pane(seeded_5m_candles, browser_page):
    # R3/R6: the default active set includes the RSI pane, so a sub-pane series
    # exists with data (DOM-only, no image diff).
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.wait_for_function(
        "() => window.marketChart.panes && window.marketChart.panes.rsi "
        "&& window.marketChart.panes.rsi.rsi.data().length > 0",
        timeout=10000,
    )
    # A sub-pane adds at least one more canvas than the price pane alone.
    assert page.locator("#chart canvas").count() >= 2


@p
def test_toggle_adds_and_removes_panes(seeded_5m_candles, browser_page):
    # R6: a toggle is a config change -> rebuild + refetch (setData path allowed).
    # Unchecking the RSI pane removes it; checking MACD adds it back as a new pane.
    page, base_url = browser_page
    kline_requests = []
    page.on(
        "request",
        lambda r: (
            kline_requests.append(r.url) if "/market/api/kline" in r.url else None
        ),
    )
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.panes "
        "&& window.marketChart.panes.rsi "
        "&& window.marketChart.panes.rsi.rsi.data().length > 0",
        timeout=10000,
    )
    with_pane = page.locator("#chart canvas").count()

    # Toggle the default RSI pane OFF: its series disappears (clean rebuild).
    page.locator('.indicator-toggle[value="rsi"]').uncheck()
    page.wait_for_function(
        "() => !(window.marketChart.panes && window.marketChart.panes.rsi)",
        timeout=10000,
    )
    assert page.locator("#chart canvas").count() < with_pane

    # Toggle MACD ON: a new pane renders and history refetches with it in the set.
    page.locator('.indicator-toggle[value="macd"]').check()
    page.wait_for_function(
        "() => window.marketChart.panes && window.marketChart.panes.macd "
        "&& window.marketChart.panes.macd.macd.data().length > 0",
        timeout=10000,
    )
    assert any("indicators=" in u and "macd" in u for u in kline_requests), (
        kline_requests
    )


@pytest.fixture
def seeded_drawings(e2e_user):
    """Seed drawings for the boot key (BTCUSDT, 1m) BEFORE the browser context.

    One hline + one rect (a full-width primitive with autoscaleInfo). Boot uses
    ``(SYMBOLS[0], "1m")`` = ``(BTCUSDT, "1m")``.
    """
    from trading.models import Drawing

    Drawing.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        interval="1m",
        kind="hline",
        points={"price": 50000.0},
        style={"color": "#2962ff", "lineWidth": 1},
    )
    Drawing.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        interval="1m",
        kind="rect",
        points={"p1": {"time": 1, "price": 1.0}, "p2": {"time": 2, "price": 2.0}},
        style={"color": "#26a69a", "fill": True},
    )
    return e2e_user


@pytest.fixture
def per_interval_drawings(e2e_user):
    """Drawings on (BTCUSDT,1m) and (BTCUSDT,5m): a switch must clear + reload."""
    from trading.models import Drawing

    Drawing.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        interval="1m",
        kind="hline",
        points={"price": 1.0},
        style={},
    )
    Drawing.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        interval="5m",
        kind="hline",
        points={"price": 2.0},
        style={},
    )
    return e2e_user


@p
def test_boot_restores_saved_drawings(seeded_drawings, browser_page):
    # R7: saved drawings for the active key attach on boot and the seam lists them.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 2",
        timeout=10000,
    )
    kinds = page.evaluate("() => window.marketChart.drawings.map((d) => d.kind)")
    assert sorted(kinds) == ["hline", "rect"]


@p
def test_click_with_tool_fires_post(seeded_5m_candles, browser_page):
    # R7: with a tool active, a chart click converts to a point and POSTs the shape.
    # Candles are seeded so the price scale has a range (else coordinateToPrice
    # returns null and the create is correctly skipped).
    page, base_url = browser_page
    posts = []
    page.on(
        "request",
        lambda r: (
            posts.append(r)
            if r.method == "POST" and "/market/api/drawings" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.locator('.draw-tool[data-kind="hline"]').click()
    canvas = page.locator("#chart canvas").first
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    assert len(posts) == 1, [r.url for r in posts]
    body = json.loads(posts[0].post_data or "{}")
    assert body["kind"] == "hline"
    assert body["symbol"] == "BTCUSDT"
    assert body["interval"] == "5m"
    assert "price" in body["points"]


@p
def test_delete_from_panel_fires_delete(seeded_drawings, browser_page):
    # R7: the panel list deletes by id -> DELETE /market/api/drawings/<id>.
    page, base_url = browser_page
    deletes = []
    page.on(
        "request",
        lambda r: (
            deletes.append(r)
            if r.method == "DELETE" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 2",
        timeout=10000,
    )
    page.locator("#drawing-list .drawing-del").first.click()
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    assert len(deletes) == 1, [r.url for r in deletes]


@p
def test_switch_clears_then_loads_drawings(per_interval_drawings, browser_page):
    # R7: switching interval clears the previous key's shapes and loads the new.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    assert page.evaluate("() => window.marketChart.drawings.length") == 1
    assert page.evaluate("() => window.marketChart.drawings[0].points.price") == 1.0

    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.drawings.length === 1"
        " && window.marketChart.drawings[0].points.price === 2.0",
        timeout=10000,
    )


@p
def test_failed_drawings_fetch_is_non_fatal(browser_page):
    # R7: a failing drawings fetch renders the chart with no drawings, no error.
    page, base_url = browser_page
    page.route("**/market/api/drawings?*", lambda route: route.abort())
    errors = []
    page.on(
        "console",
        lambda msg: errors.append(msg.text) if msg.type == "error" else None,
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    assert page.evaluate("() => window.marketChart.drawings") == []
    script_errors = [e for e in errors if "net::" not in e and "WebSocket" not in e]
    assert script_errors == [], f"console errors: {script_errors}"


# --- SMC overlay (R6/R7/R8/R9) ----------------------------------------------
#
# DOM/network assertions only (no image diffs). The read-only seam
# ``window.marketChart.smc`` holds the raw fetched payload (R9 parity), and
# ``window.marketChart.smcCounts`` holds the per-family drawn-record counts.
# VariedOHLC 5m candles are seeded BEFORE the Playwright context so the frozen
# chain has real swings/structure/zones/range/setups to compute (a constant
# series yields empty families). Boot key (BTCUSDT, "1m") is not persisted, so
# every deterministic assertion runs on the persisted "5m" key.


def _smc_bodies(page):
    """Collect /market/api/smc response bodies keyed by query string."""
    bodies: dict[str, dict] = {}

    def handler(response):
        if "/market/api/smc" not in response.url:
            return
        try:
            bodies[response.url.split("?", 1)[1]] = response.json()
        except Exception:  # noqa: BLE001 - a non-JSON body is simply not recorded
            pass

    page.on("response", handler)
    return bodies


@p
def test_smc_boot_fetches_overlay_once(seeded_5m_candles, browser_page):
    # R6/R8: boot issues exactly ONE smc request for the boot key, sharing the
    # history window (limit=HISTORY_LIMIT=200), before ``ready`` flips.
    page, base_url = browser_page
    smc_requests = []
    page.on(
        "request",
        lambda r: smc_requests.append(r.url) if "/market/api/smc" in r.url else None,
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    assert len(smc_requests) == 1, smc_requests
    assert "symbol=BTCUSDT" in smc_requests[0]
    assert "interval=1m" in smc_requests[0]
    assert "limit=200" in smc_requests[0]


@p
def test_smc_renders_all_six_families_and_seam_matches_payload(
    seeded_5m_candles, browser_page
):
    # R6/R9: over the seeded 5m window all six families draw (seam counts > 0)
    # and ``window.marketChart.smc`` deep-equals the fetched response body.
    page, base_url = browser_page
    bodies = _smc_bodies(page)
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.smc && window.marketChart.smc.interval === '5m'",
        timeout=10000,
    )
    seam = page.evaluate("() => window.marketChart.smc")
    fetched = bodies["symbol=BTCUSDT&interval=5m&limit=200"]
    # Payload <-> drawn parity (R9): the seam IS the fetched body.
    assert seam == fetched

    counts = page.evaluate("() => window.marketChart.smcCounts")
    for family in ("swings", "structure", "order_blocks", "fvg", "range", "setups"):
        assert counts[family] > 0, (family, counts)
    # The pure core maps the seam payload to setup markers (R6 render contract).
    markers = page.evaluate(
        "() => window.SmcOverlayCore.setupMarkers(window.marketChart.smc,"
        " window.marketChart.smcToggles).length"
    )
    assert markers == counts["setups"]


@p
def test_smc_toggle_hides_family_without_refetch(seeded_5m_candles, browser_page):
    # R7: unchecking a family re-renders from the fetched payload (seam counts
    # change) and MUST NOT issue a new smc request (no refetch).
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.smc && window.marketChart.smc.interval === '5m'",
        timeout=10000,
    )
    before = page.evaluate("() => window.marketChart.smcCounts")
    requests = []
    page.on(
        "request",
        lambda r: requests.append(r.url) if "/market/api/smc" in r.url else None,
    )
    page.locator('.smc-toggle[data-family="swings"]').uncheck()
    page.wait_for_function(
        "() => window.marketChart.smcCounts.swings === 0",
        timeout=5000,
    )
    after = page.evaluate("() => window.marketChart.smcCounts")
    assert requests == [], f"toggle triggered an smc refetch: {requests}"
    # Only the toggled family changed; the payload itself is untouched.
    assert after["swings"] == 0
    for family in ("structure", "order_blocks", "fvg", "range", "setups"):
        assert after[family] == before[family], (family, before, after)

    # Toggling setups off empties the marker array without a refetch.
    page.locator('.smc-toggle[data-family="setups"]').uncheck()
    page.wait_for_function(
        "() => window.marketChart.smcCounts.setups === 0",
        timeout=5000,
    )
    markers = page.evaluate(
        "() => window.SmcOverlayCore.setupMarkers(window.marketChart.smc,"
        " window.marketChart.smcToggles).length"
    )
    assert markers == 0
    assert requests == []


@p
def test_smc_switch_refetches_for_new_key(
    seeded_5m_candles, seeded_eth_5m_candles, browser_page
):
    # R8: switchTo(symbol, interval) refetches smc for the NEW key and the seam
    # reflects it (markers re-created from the new payload), with no JS errors.
    # A symbol switch keeps the boot interval ("1m", unpersisted → upstream);
    # immediately selecting "5m" leaves the persisted (ETHUSDT, 5m) as the last
    # generation, so the assertion is deterministic and DB-backed.
    page, base_url = browser_page
    errors = []
    page.on(
        "console",
        lambda msg: errors.append(msg.text) if msg.type == "error" else None,
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    assert page.evaluate("() => window.marketChart.smc.symbol") == "BTCUSDT"

    smc_requests = []
    page.on(
        "request",
        lambda r: smc_requests.append(r.url) if "/market/api/smc" in r.url else None,
    )
    page.locator('.pair[data-symbol="ETHUSDT"]').click()
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.smc && window.marketChart.smc.symbol === 'ETHUSDT'"
        " && window.marketChart.smc.interval === '5m'",
        timeout=10000,
    )
    # A fresh fetch for the new key was issued (not a reused old payload).
    assert any("symbol=ETHUSDT" in u and "interval=5m" in u for u in smc_requests), (
        smc_requests
    )
    counts = page.evaluate("() => window.marketChart.smcCounts")
    assert counts["swings"] > 0 and counts["setups"] > 0, counts
    script_errors = [e for e in errors if "net::" not in e and "WebSocket" not in e]
    assert script_errors == [], f"console errors: {script_errors}"


# --- chart legend overlay (LC1-LC6) -----------------------------------------
#
# DOM/computed-style assertions only (no image diffs, no new seam key). The
# legend is injected by controllers/legend.js into #chart on boot; a synthetic
# crosshair move over the chart drives the hover readout and moving the mouse
# OUT of the chart leaves the last values. The frozen seam must still be 8 keys.


@p
def test_legend_overlay_shows_ohlc_and_updates_on_crosshair(
    seeded_5m_candles, browser_page
):
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )

    legend = page.locator("#chart .chart-legend")
    assert legend.count() == 1
    # a11y policy: role=status, idle live region, present by boot.
    assert legend.get_attribute("role") == "status"
    assert legend.get_attribute("aria-label") == "Chart legend"

    # Idle: at least one row per active series and an OHLC read-out.
    page.wait_for_function(
        "() => document.querySelectorAll('#chart .chart-legend .lg-row').length > 0",
        timeout=10000,
    )
    rows_idle = page.locator("#chart .chart-legend .lg-row").count()
    assert rows_idle >= 1
    ohlc_before = page.locator("#chart .chart-legend .lg-ohlc").inner_text()
    assert "O " in ohlc_before and "C " in ohlc_before

    # Synthetic crosshair move over the chart canvas -> hover readout updates.
    canvas = page.locator("#chart canvas").first
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.4)
    page.wait_for_function(
        "() => document.querySelector('#chart .chart-legend .lg-ohlc')"
        " && document.querySelector('#chart .chart-legend .lg-ohlc')"
        ".textContent.includes('H ')",
        timeout=5000,
    )
    live = legend.get_attribute("aria-live")
    assert live == "off", live  # never announce per mousemove (LC5)
    # Values under the cursor are real (not the placeholder-only idle skeleton).
    hover_text = page.locator("#chart .chart-legend .lg-ohlc").inner_text()
    assert "O " in hover_text and "C " in hover_text

    # Leave the chart -> last-value fallback renders (no crash, rows remain).
    page.mouse.move(0, 0)
    page.wait_for_function(
        "() => document.querySelectorAll('#chart .chart-legend .lg-row').length > 0",
        timeout=5000,
    )
    assert page.locator("#chart .chart-legend .lg-row").count() >= 1

    # Seam frozen (R18): the legend writes DOM only, never a 9th key.
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8


@p
def test_legend_overlay_styling_and_375px_fit(seeded_5m_candles, browser_page):
    # LC5/LC6: the overlay is anchored/absolute, never eats chart pointer input,
    # and stays within #chart bounds at 375px (no horizontal overflow).
    page, base_url = browser_page
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )

    styles = page.evaluate(
        "() => { const l = document.querySelector('#chart .chart-legend');"
        " const c = document.querySelector('#chart');"
        " const ls = getComputedStyle(l), cs = getComputedStyle(c);"
        " return { pos: ls.position, pe: ls.pointerEvents, live: ls.ariaLive,"
        "   cpos: cs.position,"
        "   lw: l.getBoundingClientRect().width, cw: c.getBoundingClientRect().width,"
        "   lr: l.getBoundingClientRect().right, cr: c.getBoundingClientRect().right };"
        " }"
    )
    assert styles["pos"] == "absolute"
    assert styles["pe"] == "none"
    assert styles["cpos"] == "relative"
    # Fits inside #chart at 375px: no horizontal overflow past the right edge.
    assert styles["lw"] <= styles["cw"]
    assert styles["lr"] <= styles["cr"] + 1


# --- chart shell (Slice 1: full-height + chips + sidebar collapse) -----------
#
# DOM/computed-style assertions only. The chips are DERIVED from the retained
# ``<select id="interval">`` (kept in the DOM, visually hidden via clip) so the
# 15 existing ``select_option("#interval", …)`` calls above stay green with no
# edits. The frozen seam stays 8 keys.


@p
def test_chart_fills_height_and_canvas_tracks_container(
    seeded_5m_candles, browser_page
):
    # R20: autoSize:true + a flex-resolved #chart make the canvas taller than the
    # old fixed 480 and track #chart's box (no zero-height collapse).
    page, base_url = browser_page
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    # autoSize sizes the LightweightCharts root to its container via a
    # ResizeObserver (async). Wait until the root fills #chart, then read boxes.
    page.wait_for_function(
        "() => { const c = document.querySelector('#chart');"
        " const root = document.querySelector('#chart .tv-lightweight-charts');"
        " if (!c || !root) return false;"
        " return Math.abs(root.getBoundingClientRect().height"
        " - c.getBoundingClientRect().height) <= 2; }",
        timeout=10000,
    )
    boxes = page.evaluate(
        "() => { const c = document.querySelector('#chart');"
        " const root = document.querySelector('#chart .tv-lightweight-charts');"
        " const cv = document.querySelector('#chart canvas');"
        " return { chartH: c.getBoundingClientRect().height,"
        "   rootH: root.getBoundingClientRect().height,"
        "   canvasH: cv.getBoundingClientRect().height }; }"
    )
    # Resolved by the flex chain, not the removed `height:480` option.
    assert boxes["chartH"] > 480, boxes
    # The price-pane canvas is taller than the old fixed 480 box.
    assert boxes["canvasH"] > 480, boxes
    # The chart root tracks #chart exactly (autoSize ResizeObserver).
    assert abs(boxes["rootH"] - boxes["chartH"]) <= 2, boxes


@p
def test_chart_host_has_no_fixed_height_and_autosize():
    # R20: the construction options carry autoSize and never a numeric height.
    import re

    host = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "web/market/templates/market/chart-host.js"
    ).read_text()
    assert "autoSize: true" in host or "autoSize:true" in host
    assert not re.search(r"\bheight\s*:\s*\d", host), "fixed numeric height remains"


@p
def test_interval_chips_switch_and_reflect_store(seeded_5m_candles, browser_page):
    # R21: chips render from the select options; activating one moves
    # aria-pressed and switches the chart to that interval.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )

    chips = page.locator(".interval-chips .interval-chip")
    assert chips.count() == 14
    assert (
        page.locator('.interval-chip[data-interval="1m"]').get_attribute("aria-pressed")
        == "true"
    )

    page.locator('.interval-chip[data-interval="5m"]').click()
    page.wait_for_function(
        "() => window.marketChart.candleSeries.data().length > 0"
        " && document.querySelector('.interval-chip[data-interval=\"5m\"]')"
        ".getAttribute('aria-pressed') === 'true'",
        timeout=10000,
    )
    assert (
        page.locator('.interval-chip[data-interval="1m"]').get_attribute("aria-pressed")
        == "false"
    )
    # One command path: the retained select reflects the chip choice.
    assert page.locator("#interval").input_value() == "5m"


@p
def test_hidden_select_stays_selectable_and_syncs_chips(
    seeded_5m_candles, browser_page
):
    # R21/R18 invariant: the select stays in the DOM (clipped, not display:none),
    # select_option still works, and the chips follow it.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    clipped = page.evaluate(
        "() => { const s = document.getElementById('interval');"
        " const cs = getComputedStyle(s);"
        " return { display: cs.display, visibility: cs.visibility,"
        "   clip: cs.clipPath || cs.clip }; }"
    )
    assert clipped["display"] != "none", clipped
    assert clipped["visibility"] != "hidden", clipped

    # The pre-existing E2E interaction still works (no assertion edits needed).
    page.select_option("#interval", "1h")
    page.wait_for_function(
        "() => document.querySelector('.interval-chip[data-interval=\"1h\"]')"
        ".getAttribute('aria-pressed') === 'true'",
        timeout=10000,
    )
    assert (
        page.locator('.interval-chip[data-interval="5m"]').get_attribute("aria-pressed")
        == "false"
    )


@p
def test_panel_toggle_collapses_and_expands_at_375(seeded_5m_candles, browser_page):
    # R23: the toggle is visible ≤820px, flips aria-expanded and hides the panel.
    page, base_url = browser_page
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    toggle = page.locator(".panel-toggle")
    assert toggle.is_visible()
    assert toggle.get_attribute("aria-expanded") == "true"
    assert toggle.get_attribute("aria-controls") == "panel"

    toggle.click()
    page.wait_for_function(
        "() => document.querySelector('.panel-toggle')"
        ".getAttribute('aria-expanded') === 'false'",
        timeout=5000,
    )
    assert page.locator("#panel").is_visible() is False

    toggle.click()
    page.wait_for_function(
        "() => document.querySelector('.panel-toggle')"
        ".getAttribute('aria-expanded') === 'true'",
        timeout=5000,
    )
    assert page.locator("#panel").is_visible()


@p
def test_no_horizontal_overflow_at_375(seeded_5m_candles, browser_page):
    # R24: at 375px the page must not scroll horizontally; chips wrap.
    page, base_url = browser_page
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth"
        " - document.documentElement.clientWidth"
    )
    assert overflow <= 1, overflow
    wrap = page.evaluate(
        "() => getComputedStyle(document.querySelector('.interval-chips')).flexWrap"
    )
    assert wrap == "wrap"


@p
def test_shell_keeps_seam_at_eight_keys(seeded_5m_candles, browser_page):
    # R20 (market-chart): the shell writes no new global; seam stays 8 keys.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8
    assert page.evaluate("() => typeof window.SmcOverlayCore") == "object"


@pytest.fixture
def saved_interval_preference(e2e_user):
    """Seed a user-global last-interval preference BEFORE the Playwright context.

    Boot fetches this preference before the first chart build (R10); a saved
    ``5m`` makes the restore observable on the chip row + select.
    """
    from trading.models import ChartPreference

    ChartPreference.objects.create(user=e2e_user, last_interval="5m")
    return e2e_user


@p
def test_boot_restores_saved_interval_preference(
    seeded_5m_candles, saved_interval_preference, browser_page
):
    # R10: a persisted last-interval wins on boot — the 5m chip is active and
    # the retained select reflects it (the chart builds at 5m, not the 1m default).
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    assert (
        page.locator('.interval-chip[data-interval="5m"]').get_attribute("aria-pressed")
        == "true"
    )
    assert (
        page.locator('.interval-chip[data-interval="1m"]').get_attribute("aria-pressed")
        == "false"
    )
    assert page.locator("#interval").input_value() == "5m"


@p
def test_boot_preference_fetch_failure_defaults_to_1m(seeded_5m_candles, browser_page):
    # R10: a failed preference GET MUST NOT blank the chart — boot falls back to
    # "1m" and still reaches ready.
    page, base_url = browser_page
    page.route("**/market/api/preference*", lambda route: route.abort())
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    assert (
        page.locator('.interval-chip[data-interval="1m"]').get_attribute("aria-pressed")
        == "true"
    )
    assert page.locator("#interval").input_value() == "1m"
    # The chart still built (never blank): the candle series seam exists.
    assert page.evaluate("() => typeof window.marketChart.candleSeries") == "object"


@p
def test_interval_change_debounce_saves_preference(seeded_5m_candles, browser_page):
    # R10: an interval change debounce-PUTs the preference carrying the new value.
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if "/market/api/preference" in r.url and r.method == "PUT"
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    page.locator('.interval-chip[data-interval="5m"]').click()
    page.wait_for_function(
        "() => document.querySelector('.interval-chip[data-interval=\"5m\"]')"
        ".getAttribute('aria-pressed') === 'true'",
        timeout=10000,
    )
    page.wait_for_function(
        "() => window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    # Debounce is 500ms; wait for exactly one PUT to have fired.
    page.wait_for_timeout(1200)
    assert len(puts) == 1, [r.url for r in puts]
    assert json.loads(puts[0].post_data) == {"interval": "5m"}
