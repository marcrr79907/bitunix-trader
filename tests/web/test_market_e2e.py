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
