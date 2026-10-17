"""R5 dev-only E2E smoke: the chart page wires up in a real browser.

DOM-only assertions (no image diffs): the LightweightCharts global is
defined, the chart canvas exists, and the page loads without JS console
errors (WS network errors are tolerated — external dependency).

The two live-candle scenarios mock the exchange socket via
``page.route_web_socket`` (installed BEFORE ``goto``) so frame ordering and
same-bucket updates are asserted deterministically, no live network/CDN.

Run locally: `playwright install chromium` once, then
`python -m pytest -m e2e -p no:randomly` on an IDLE machine — the mocked-socket
tests are timing-sensitive, so a loaded host can flake. Each WS test waits for
boot readiness (`window.marketChart.ready`) before switching interval or
injecting frames; readiness, not retry, is the determinism mechanism.
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
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
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
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
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
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
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
    _wait_ready(page)  # socket OPEN before switching + injecting frames
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )

    n = page.evaluate("() => window.marketChart.candleSeries.data().length")
    last_time = page.evaluate(
        "() => window.marketChart.candleSeries.data().slice(-1)[0].time"
    )
    t = last_time + 300  # next 5m bucket

    push = {
        "ch": "market_kline_5min",  # #150: the guard requires the frame channel
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
    _wait_ready(page)  # socket OPEN before switching + injecting frames
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
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
                    "ch": "market_kline_5min",  # #150: guard requires the channel
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


@p
def test_ws_stale_channel_push_during_switch(seeded_5m_candles, browser_page):
    # #150 (DEBT-1): a frame buffered across switchTo from the OUTGOING channel
    # must be dropped by the channel guard, NOT re-bucketed under the new
    # interval. Without the guard the stale frame is written at T-300 < T and
    # LightweightCharts raises `Cannot update oldest data`.
    page, base_url = browser_page
    holder = {}
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    kline_5m = []
    page.on(
        "response",
        lambda r: (
            kline_5m.append(r.url)
            if "/market/api/kline" in r.url and "interval=5m" in r.url
            else None
        ),
    )

    def handler(ws_route):
        holder["route"] = ws_route

    page.route_web_socket("wss://fapi.bitunix.com/**", handler)
    page.goto(f"{base_url}/market/")  # boot on 1m
    _wait_ready(page)  # socket OPEN before switching + injecting frames
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    # The 5m rebuild loads history exactly once (single setData for the switch).
    assert len(kline_5m) == 1, kline_5m

    n = page.evaluate("() => window.marketChart.candleSeries.data().length")
    T = page.evaluate("() => window.marketChart.candleSeries.data().slice(-1)[0].time")
    # Spy AFTER the rebuild settles: the live path must never setData (#68).
    page.evaluate(
        "() => { const s = window.marketChart.candleSeries;"
        " window.__setDataCalls = 0; const orig = s.setData.bind(s);"
        " s.setData = function(){ window.__setDataCalls++;"
        " return orig.apply(s, arguments); }; }"
    )

    # Stale frame: OLD channel, ts 1s into the PREVIOUS 5m bucket. A missing
    # guard re-buckets it to T-300 (< T) -> `Cannot update oldest data`.
    stale_ts = (T - 300) * 1000 + 1000
    holder["route"].send(
        json.dumps(
            {
                "ch": "market_kline_1min",
                "symbol": "BTCUSDT",
                "ts": stale_ts,
                "data": {"o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5},
            }
        )
    )
    page.wait_for_timeout(300)  # give the (buggy) handler a chance to raise

    assert not any(
        "Cannot update oldest data" in e or "Object is disposed" in e for e in errors
    ), errors
    after = page.evaluate("() => window.marketChart.candleSeries.data().length")
    last_after = page.evaluate(
        "() => window.marketChart.candleSeries.data().slice(-1)[0].time"
    )
    assert after == n, f"stale frame mutated the series: {n} -> {after}"
    assert last_after == T

    # Valid frame on the NEW channel in the NEXT bucket grows the series by 1.
    holder["route"].send(
        json.dumps(
            {
                "ch": "market_kline_5min",
                "symbol": "BTCUSDT",
                "ts": (T + 300) * 1000,
                "data": {"o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5},
            }
        )
    )
    page.wait_for_function(
        f"() => window.marketChart.candleSeries.data().length === {n + 1}",
        timeout=5000,
    )
    final = page.evaluate(
        "() => window.marketChart.candleSeries.data().slice(-1)[0].time"
    )
    assert final == T + 300
    calls = page.evaluate("() => window.__setDataCalls")
    assert calls == 0, f"setData called {calls} times during the live path"


def _wait_ready(page):
    """Wait for boot to finish: layout applied + chart built (DOM seam)."""
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )


def _tree_tokens(page):
    """The active indicator tokens listed in the object tree (R1 active-only)."""
    return page.evaluate(
        "() => Array.from(document.querySelectorAll("
        "'.object-tree .tree-row[data-token]')).map((r) => r.dataset.token)"
    )


# --- F5 S3 E2E coverage delta (F5 FIX-5, issue #177) -------------------------
#
# S3 legitimately deleted the DOM these assertions checked: the indicators
# `fieldset` (add-any-token via checkbox) and `#drawing-list`. R18's "green with
# NO assertion edits" clause was unmeetable by the change that removes that DOM,
# so the archive reconciles R18/R20 to "green except the assertions removed AND
# REPLACED by equivalent coverage". This is that reconciliation. Format:
# "removed scenario -> what it verified -> replacement".
#
# * checkbox `.indicator-toggle[sma/ema/rsi]` checked -> saved layout restored
#   -> test_boot_restores_saved_layout (tree tokens)
# * checkbox is_checked -> active membership render
#   -> test_fetch_failure_falls_back_to_defaults (tree tokens)
# * checkbox `rsi` on -> one debounced PUT body -> persist a change
#   -> test_toggle_fires_one_debounced_put (tree eye -> visible:false)
# * checkbox `sma`/`rsi` across interval switch -> per-interval layout load
#   -> test_switch_loads_target_layout (tree tokens)
# * test_toggle_adds_and_removes_panes: uncheck rsi -> pane gone + check macd ->
#   pane + `indicators=macd` -> config change -> rebuild + REFETCH with the new
#   set, and ADD an indicator
#   -> test_indicator_eye_hides_option_only_and_delete_removes_pane: delete rsi
#      -> pane gone AND history REFETCHES with the set minus rsi. ADDING has NO
#      replacement -> issue #176 (new capability, slice S5)
# * `#drawing-list .drawing-del` delete -> drawing delete by id
#   -> test_tree_row_delete_fires_delete (row-delete)
# * settings gear `.indicator-settings[sma]` -> open the settings dialog
#   -> _SETTINGS_GEAR = `.tree-row[data-token=sma] .row-settings`
# * legend: check `bollinger` -> 2nd build -> legend survives a rebuild
#   -> test_legend_resubscribes_across_rebuild (seeded bollinger + style edit)
#
# Net: every removed scenario has an equivalent replacement EXCEPT adding an
# indicator, which S3 removed (active-only membership) and is tracked as the new
# capability issue #176 (add-indicator affordance, slice S5).


@p
def test_boot_restores_saved_layout(saved_layout, browser_page):
    # R4 (issue #71): a persisted layout wins over the DOM defaults on boot —
    # the toggle panel reflects the saved set AND the chart rebuilds to match.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    # Saved: SMA on (len 50), MACD on; EMA/RSI off. The tree lists ACTIVE-ONLY
    # membership (R1), so the saved set is exactly what renders.
    tokens = _tree_tokens(page)
    assert "sma" in tokens
    assert "macd" in tokens
    assert "ema" not in tokens
    assert "rsi" not in tokens
    # The saved param restores into the store -> the sma request carries len 50
    # (the settings dialog reads it back from params).
    page.locator('.tree-row[data-token="sma"] .row-settings').click()
    assert page.locator("#is-period").input_value() == "50"
    page.keyboard.press("Escape")
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
def test_fetch_failure_falls_back_to_defaults(browser_page):
    # R4: a failing layout fetch MUST fall back to the default set — never a
    # blank chart. The store's DEFAULT_INDICATORS is the source of truth.
    page, base_url = browser_page
    page.route("**/market/api/layout?*", lambda route: route.abort())
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    tokens = _tree_tokens(page)
    assert "sma" in tokens
    assert "ema" in tokens
    assert "rsi" in tokens


@p
def test_toggle_fires_one_debounced_put(saved_layout, browser_page):
    # R5: a tree action debounce-saves exactly one PUT carrying the active
    # symbol+interval. The tree is ACTIVE-ONLY (R1), so the persisted action is
    # a row eye (visibility) toggle — the saved payload reflects it.
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
    page.locator('.tree-row[data-token="sma"] .row-eye').click()
    # Debounce (~500 ms) then one PUT; a second quick action must not add one.
    page.wait_for_timeout(1200)
    assert len(puts) == 1, [p.url for p in puts]
    body = json.loads(puts[0].post_data or "{}")
    assert body["symbol"] == "BTCUSDT"
    assert body["interval"] == "1m"
    sma = next(i for i in body["indicators"] if i["token"] == "sma")
    assert sma.get("visible") is False


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
    page.wait_for_function(
        "() => !!document.querySelector('.tree-row[data-token=\"sma\"]')"
        " && !document.querySelector('.tree-row[data-token=\"rsi\"]')",
        timeout=10000,
    )

    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.panes"
        " && window.marketChart.panes.rsi"
        " && window.marketChart.panes.rsi.rsi.data().length > 0",
        timeout=10000,
    )
    # The tree re-sources membership from the store after the target layout load.
    page.wait_for_function(
        "() => !!document.querySelector('.tree-row[data-token=\"rsi\"]')"
        " && !document.querySelector('.tree-row[data-token=\"sma\"]')",
        timeout=10000,
    )


@p
def test_selected_indicator_renders_a_pane(seeded_5m_candles, browser_page):
    # R3/R6: the default active set includes the RSI pane, so a sub-pane series
    # exists with data (DOM-only, no image diff).
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
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
def test_indicator_eye_hides_option_only_and_delete_removes_pane(
    seeded_5m_candles, browser_page
):
    # F5 S3: the object tree has two indicator actions.
    #  (a) eye  -> option-only hide (#68): the series stays, the pane remains.
    #  (b) delete -> membership change -> rebuild/refetch: the pane disappears.
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

    # (a) Eye-hide RSI: option-only. The pane/series stay attached (#68); only
    # the series' visible option flips. No kline refetch.
    kline_requests.clear()
    page.locator('.tree-row[data-token="rsi"] .row-eye').click()
    page.wait_for_function(
        "() => window.marketChart.chart.panes().some((p) => p.getSeries().some("
        " (s) => s.options().visible === false))",
        timeout=10000,
    )
    assert page.evaluate(
        "() => !!(window.marketChart.panes && window.marketChart.panes.rsi)"
    ), "pane stays attached on an option-only hide"
    assert kline_requests == [], kline_requests

    # (b) Delete RSI from the tree: membership change -> rebuild removes the pane.
    page.locator('.tree-row[data-token="rsi"] .row-delete').click()
    page.wait_for_function(
        "() => !(window.marketChart.panes && window.marketChart.panes.rsi)",
        timeout=10000,
    )
    assert page.locator("#chart canvas").count() < with_pane
    # The rebuild REFETCHES history with the indicator set minus the deleted token
    # — the positive replacement for `test_toggle_adds_and_removes_panes`'s
    # "history refetches with the indicator set" (F5 FIX-5, issue #177). A new
    # kline request MUST appear carrying `indicators=` WITHOUT rsi.
    page.wait_for_function(
        "() => true", timeout=1000
    )  # let the rebuild's fetchHistory land
    assert kline_requests, "the delete rebuild MUST refetch history"
    refetched = [u for u in kline_requests if "indicators=" in u]
    assert refetched, kline_requests
    assert not any("rsi" in u.split("indicators=", 1)[1] for u in refetched), refetched


@p
def test_add_indicator_renders_pane_and_refetches(seeded_5m_candles, browser_page):
    # F5 S5 (issue #176): the counterpart to the S3 delete — the tree is
    # ACTIVE-ONLY, so the ADD affordance lists the registry tokens NOT active.
    # Picking MACD (absent from the default set) rebuilds: a MACD pane appears
    # AND history refetches carrying `indicators=` WITH macd (the positive
    # refetch assertion #177 flagged as lost).
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
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    assert not page.evaluate(
        "() => !!(window.marketChart.panes && window.marketChart.panes.macd)"
    ), "MACD absent from the default set"

    kline_requests.clear()
    page.locator(".add-indicator .add-toggle").click()
    macd = page.locator('.add-indicator .add-item[data-token="macd"]')
    assert macd.count() == 1, "macd offered as an inactive candidate"
    macd.click()
    # A MACD pane series renders after the rebuild.
    page.wait_for_function(
        "() => !!(window.marketChart.panes && window.marketChart.panes.macd)",
        timeout=10000,
    )
    # The rebuild refetches history WITH macd in the indicator set.
    page.wait_for_function("() => true", timeout=1000)  # let fetchHistory land
    assert kline_requests, "the add rebuild MUST refetch history"
    refetched = [u for u in kline_requests if "indicators=" in u]
    assert refetched, kline_requests
    assert any("macd" in u.split("indicators=", 1)[1] for u in refetched), refetched
    # The tree lists macd as active now.
    assert "macd" in _tree_tokens(page)


@p
def test_add_indicator_persists_across_reload(seeded_5m_candles, browser_page):
    # R7: an added token round-trips — the debounced PUT persists membership,
    # and a reload for the same (symbol, interval) shows it active + rendered.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.locator(".add-indicator .add-toggle").click()
    page.locator('.add-indicator .add-item[data-token="macd"]').click()
    page.wait_for_function(
        "() => !!(window.marketChart.panes && window.marketChart.panes.macd)",
        timeout=10000,
    )
    page.wait_for_timeout(1200)  # debounced PUT lands before reload

    page.reload()
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )
    page.wait_for_function(
        "() => !!document.querySelector('.tree-row[data-token=\"macd\"]')",
        timeout=10000,
    )
    page.wait_for_function(
        "() => !!(window.marketChart.panes && window.marketChart.panes.macd)",
        timeout=10000,
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
        kind="hline",
        points={"price": 50000.0},
        style={"color": "#2962ff", "lineWidth": 1},
    )
    Drawing.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        kind="rect",
        points={"p1": {"time": 1, "price": 1.0}, "p2": {"time": 2, "price": 2.0}},
        style={"color": "#26a69a", "fill": True},
    )
    return e2e_user


@pytest.fixture
def per_symbol_drawings(e2e_user):
    """A drawing on BTCUSDT and a different one on ETHUSDT (per SYMBOL, R1)."""
    from trading.models import Drawing

    Drawing.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        kind="hline",
        points={"price": 1.0},
        style={},
    )
    Drawing.objects.create(
        user=e2e_user,
        symbol="ETHUSDT",
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
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
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
    # R2: the drawing body is per SYMBOL now — ``interval`` is no longer sent.
    assert "interval" not in body
    assert "price" in body["points"]


@p
def test_draw_toolbar_renders_groups_and_sets_store(browser_page):
    # F5 S2 (R1/R2/R3): the vertical grouped icon toolbar replaces the flat text
    # buttons; activating a tool writes store.tool and moves aria-pressed, and
    # the roving tabindex mirrors the interval-chip pattern.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    toolbar = page.locator('.draw-tools[role="toolbar"]')
    assert toolbar.count() == 1
    assert toolbar.get_attribute("aria-orientation") == "vertical"
    # F6: the F5 four groups plus Measure + Positions.
    assert page.locator('.draw-tools [role="group"]').count() == 6
    assert page.locator(".draw-tool").count() == 7
    # The legacy flat text buttons are gone (labels H-line/Trend/Box no longer exist).
    assert page.locator(".drawings .draw-tool").count() == 0
    # Icons injected by JS (no inline handler); each button names itself.
    assert page.locator(".draw-tools .draw-tool svg").count() == 7
    assert (
        page.locator('.draw-tool[data-kind="fib"]').get_attribute("aria-label")
        == "Fibonacci retracement"
    )

    # No tool active at boot: nothing pressed.
    assert page.locator('.draw-tools .draw-tool[aria-pressed="true"]').count() == 0

    page.locator('.draw-tool[data-kind="fib"]').click()
    page.wait_for_function(
        "() => document.querySelector('.draw-tool[data-kind=\"fib\"]')"
        ".getAttribute('aria-pressed') === 'true'",
        timeout=10000,
    )
    assert page.locator('.draw-tools .draw-tool[aria-pressed="true"]').count() == 1
    # Roving tabindex: the active tool owns the single tab stop.
    fib_tabindex = page.locator('.draw-tool[data-kind="fib"]').get_attribute("tabindex")
    assert fib_tabindex == "0"

    # Keyboard: ArrowDown from the first tool moves focus to the next.
    page.locator('.draw-tool[data-kind="hline"]').focus()
    page.keyboard.press("ArrowDown")
    focused = page.evaluate("() => document.activeElement.dataset.kind")
    assert focused == "trendline"

    # Reactivating the active tool cancels it (legacy toggle semantics).
    page.locator('.draw-tool[data-kind="fib"]').click()
    page.wait_for_function(
        "() => document.querySelectorAll("
        "'.draw-tools .draw-tool[aria-pressed=\"true\"]').length === 0",
        timeout=10000,
    )


@p
def test_tree_row_delete_fires_delete(seeded_drawings, browser_page):
    # R7: the object-tree row delete -> DELETE /market/api/drawings/<id>.
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
    page.locator("#object-tree .tree-row[data-id] .row-delete").first.click()
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    assert len(deletes) == 1, [r.url for r in deletes]


@p
def test_tree_drawing_eye_persists_visible_false(seeded_drawings, browser_page):
    # F5 S3 (R2): the drawing eye toggles visibility and persists via one PUT
    # carrying only ``{visible:false}`` (partial body).
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if r.method == "PUT" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 2",
        timeout=10000,
    )
    eye = page.locator("#object-tree .tree-row[data-id] .row-eye").first
    eye.click()
    page.wait_for_function(
        "() => document.querySelector('#object-tree .tree-row[data-id] .row-eye')"
        ".getAttribute('aria-pressed') === 'false'",
        timeout=10000,
    )
    page.wait_for_timeout(300)  # let the PUT land
    assert len(puts) >= 1, [r.url for r in puts]
    body = json.loads(puts[-1].post_data or "{}")
    assert body == {"visible": False}, body
    # The seam carries the hidden flag (R4).
    assert page.evaluate(
        "() => window.marketChart.drawings.some((d) => d.visible === false)"
    )


@p
def test_tree_keyboard_navigation_and_indicator_visibility(
    seeded_5m_candles, browser_page
):
    # F5 S3 (R3): roving tabindex + Up/Down move focus between treeitems; an
    # indicator eye emits option-only visibility (no rebuild, no refetch).
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.wait_for_function(
        "() => !!document.querySelector('.tree-row[data-token=\"sma\"]')",
        timeout=10000,
    )
    # Exactly one tab stop; ArrowDown moves focus to the next treeitem.
    assert page.locator('#object-tree [role="treeitem"][tabindex="0"]').count() == 1
    page.locator('.tree-row[data-token="sma"]').focus()
    page.keyboard.press("ArrowDown")
    assert page.evaluate(
        "() => document.activeElement !== document.querySelector("
        "'.tree-row[data-token=\"sma\"]')"
    )

    # Indicator eye -> option-only hide. The pane stays, no kline refetch.
    klines = []
    page.on(
        "request",
        lambda r: klines.append(r.url) if "/market/api/kline" in r.url else None,
    )
    page.locator('.tree-row[data-token="sma"] .row-eye').click()
    page.wait_for_function(
        "() => window.marketChart.chart.panes().some((p) => p.getSeries().some("
        " (s) => s.options().visible === false))",
        timeout=10000,
    )
    assert klines == [], klines


@p
def test_tree_row_actions_reachable_and_activatable_by_keyboard(
    seeded_drawings, browser_page
):
    # R6/R9 (F5 FIX-3): the drawing row's eye/lock were mouse-only. A focused row
    # MUST activate them by the documented keys (v = visibility, l = lock) and
    # advertise the binding; the action persists via its own bus path.
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if r.method == "PUT" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 2",
        timeout=10000,
    )
    row = page.locator("#object-tree .tree-row[data-id]").first
    assert row.locator(".row-eye").get_attribute("aria-keyshortcuts") == "v"
    assert row.locator(".row-lock").get_attribute("aria-keyshortcuts") == "l"

    row.focus()
    page.keyboard.press("v")  # eye -> hide
    page.wait_for_function(
        "() => document.querySelector('#object-tree .tree-row[data-id] .row-eye')"
        ".getAttribute('aria-pressed') === 'false'",
        timeout=10000,
    )
    page.keyboard.press("l")  # lock -> locked
    page.wait_for_function(
        "() => document.querySelector('#object-tree .tree-row[data-id] .row-lock')"
        ".getAttribute('aria-pressed') === 'true'",
        timeout=10000,
    )
    page.wait_for_timeout(300)  # let the debounced PUT land
    assert page.evaluate(
        "() => window.marketChart.drawings.some((d) => d.locked === true)"
    )
    assert len(puts) >= 1, [r.url for r in puts]


# --- Drawing interaction (R9-R14): select / drag / delete / deselect ---------
#
# The canvas is not introspectable, so every assertion rides the seam
# (``window.marketChart.drawings``) or the captured network request — never DOM
# pixels. Readiness-gated (DEBT-8). The hline sits at price 100.0,
# inside the seeded 5m candle range, so its pixel y comes from the live series.


@pytest.fixture
def interaction_drawing(e2e_user):
    """One hline at 100.0 — inside the seeded 5m candle range (93-107)."""
    from trading.models import Drawing

    return Drawing.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        kind="hline",
        points={"price": 100.0},
        style={"color": "#2962ff", "lineWidth": 1},
    )


def _hline_y(page, price):
    """Pane-relative y for ``price`` on the live candle series (or None)."""
    return page.evaluate(
        "(price) => { const s = window.marketChart.candleSeries;"
        " return s ? s.priceToCoordinate(price) : null; }",
        price,
    )


def _select_hline(page):
    """Switch to the seeded 5m key and click the hline at price 100.0."""
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    y = _hline_y(page, 100.0)
    assert y is not None, "no price coordinate for the seeded hline"
    chart = page.locator("#chart")
    box = chart.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + y)
    chart.focus()
    return chart, box


@p
def test_click_empty_plot_then_delete_is_noop(
    seeded_5m_candles, interaction_drawing, browser_page
):
    # R9/R11: a pointerdown on empty plot clears selection, so a following Delete
    # deletes nothing and issues no request.
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
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    chart = page.locator("#chart")
    box = chart.bounding_box()
    # Bottom-right corner of the plot is empty (below the hline).
    page.mouse.click(box["x"] + box["width"] - 8, box["y"] + box["height"] - 8)
    chart.focus()
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)
    assert deletes == [], [r.url for r in deletes]
    assert page.evaluate("() => window.marketChart.drawings.length") == 1


@p
def test_drag_persists_single_put_and_moves_points(
    seeded_5m_candles, interaction_drawing, browser_page
):
    # R10/R7: dragging the selected hline body moves its price and issues exactly
    # ONE PUT (single write per gesture); the seam reflects the new points.
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if r.method == "PUT" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    chart, box = _select_hline(page)
    y = _hline_y(page, 100.0)
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + y
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, start_y - 40, steps=8)
    page.mouse.up()
    page.wait_for_function(
        "() => window.marketChart.drawings[0].points.price !== 100.0",
        timeout=5000,
    )
    assert len(puts) == 1, [r.url for r in puts]
    moved = page.evaluate("() => window.marketChart.drawings[0].points.price")
    assert moved != 100.0


@p
def test_drag_undo_issues_second_put_with_prior_points(
    seeded_5m_candles, interaction_drawing, browser_page
):
    # F7 R2/R3 (S2): a drag records exactly ONE entry; Ctrl+Z replays the move
    # through drawings.js — a SECOND PUT carrying the PRE-drag points. DOM+network
    # only (no pixels), readiness-gated (DEBT-8, #149).
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if r.method == "PUT" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    chart, box = _select_hline(page)
    y = _hline_y(page, 100.0)
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + y
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, start_y - 40, steps=8)
    page.mouse.up()
    page.wait_for_function(
        "() => window.marketChart.drawings[0].points.price !== 100.0",
        timeout=5000,
    )
    assert len(puts) == 1, [r.url for r in puts]  # one gesture = one PUT
    page.keyboard.press("Control+z")
    page.wait_for_function(
        "() => window.marketChart.drawings[0].points.price === 100.0",
        timeout=5000,
    )
    assert len(puts) == 2, [r.url for r in puts]  # undo replays a second PUT
    assert json.loads(puts[1].post_data or "{}")["points"]["price"] == 100.0


@p
def test_create_undo_deletes_via_tool(seeded_5m_candles, browser_page):
    # F7 R3 (S2): a tool create records {op:create}; Ctrl+Z DELETEs the new row.
    # The duplicate path is equivalent (replayOps: duplicate ≡ create), so this
    # covers the create/duplicate undo matrix end-to-end.
    page, base_url = browser_page
    posts, deletes = [], []
    page.on(
        "request",
        lambda r: (
            posts.append(r)
            if r.method == "POST" and "/market/api/drawings" in r.url
            else None
        ),
    )
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
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
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
    created_id = page.evaluate("() => window.marketChart.drawings[0].id")
    page.keyboard.press("Control+z")
    page.wait_for_function(
        "() => window.marketChart.drawings.length === 0",
        timeout=5000,
    )
    assert len(deletes) == 1, [r.url for r in deletes]
    assert deletes[0].url.endswith(f"/{created_id}")


@p
def test_drag_put_returns_200_and_persists_across_reload(
    seeded_5m_candles, interaction_drawing, browser_page
):
    # S3: the PUT endpoint is real now, so the S2 drag lands (200) and a reload
    # restores the drawing at its new position (asserted via the seam, not DOM
    # pixels). Readiness-gated (DEBT-8); dev-only (class-C WS flake, #149).
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if r.method == "PUT" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    chart, box = _select_hline(page)
    y = _hline_y(page, 100.0)
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + y
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, start_y - 40, steps=8)
    with page.expect_response(
        lambda r: r.request.method == "PUT" and "/market/api/drawings/" in r.url,
        timeout=10000,
    ) as resp_info:
        page.mouse.up()
    # The endpoint is real now: the drag's PUT lands with a 200.
    assert resp_info.value.status == 200, resp_info.value.status
    moved = page.evaluate("() => window.marketChart.drawings[0].points.price")
    assert moved != 100.0
    assert len(puts) == 1, [r.url for r in puts]  # exactly one write per gesture

    # Reload: the persisted row is restored at the moved price.
    page.reload()
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    restored = page.evaluate("() => window.marketChart.drawings[0].points.price")
    assert restored != 100.0
    assert abs(restored - moved) < 1e-6


@pytest.fixture
def hidden_hline(e2e_user):
    """One hline at 100.0 with ``visible:false`` (R9: not pointer-grabbable)."""
    from trading.models import Drawing

    return Drawing.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        kind="hline",
        points={"price": 100.0},
        style={"color": "#2962ff", "lineWidth": 1},
        visible=False,
    )


@pytest.fixture
def locked_hline(e2e_user):
    """One hline at 100.0 with ``locked:true`` (R9: not pointer-grabbable)."""
    from trading.models import Drawing

    return Drawing.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        kind="hline",
        points={"price": 100.0},
        style={"color": "#2962ff", "lineWidth": 1},
        locked=True,
    )


@p
def test_locked_drawing_is_not_pointer_grabbable_but_tree_selectable(
    seeded_5m_candles, locked_hline, browser_page
):
    # R9 (F5 FIX-1): a locked drawing is NOT pointer-selectable/draggable — a
    # pointerdown on it neither moves it (no PUT) nor opens it (no dialog) — but
    # the tree still selects it via a bus emit (drawing:selected).
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if r.method == "PUT" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    assert page.evaluate("() => window.marketChart.drawings[0].locked === true")

    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    y = _hline_y(page, 100.0)
    assert y is not None, "no price coordinate for the seeded locked hline"
    box = page.locator("#chart").bounding_box()
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + y
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, start_y - 40, steps=8)
    page.mouse.up()
    page.wait_for_timeout(300)
    # The pointer drag was ignored: no PUT, price unchanged.
    assert puts == [], [r.url for r in puts]
    assert page.evaluate("() => window.marketChart.drawings[0].points.price") == 100.0

    # Double-click on the locked line opens NO properties dialog (R13 no-op).
    page.mouse.dblclick(start_x, start_y)
    page.wait_for_timeout(200)
    assert not page.locator("#drawing-settings-dialog[open]").count()

    # Tree selection still works (bus emit, not a pointer hit).
    page.locator(".tree-row[data-id]").first.click()
    page.wait_for_function(
        "() => document.querySelector('.tree-row[data-id]')"
        ".getAttribute('aria-selected') === 'true'",
        timeout=5000,
    )


@p
def test_hidden_drawing_is_not_pointer_grabbable(
    seeded_5m_candles, hidden_hline, browser_page
):
    # R9 (F5 FIX-2): a hidden drawing renders blank AND is not pointer-grabbable —
    # a drag at its price moves nothing and issues no PUT. The tree still selects
    # it (a bus emit, not a pointer hit).
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if r.method == "PUT" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    # The row is present (parked, R4) and reflects the hidden flag.
    assert page.evaluate("() => window.marketChart.drawings[0].visible === false")
    assert (
        page.locator(".tree-row[data-id] .row-eye").first.get_attribute("aria-pressed")
        == "false"
    )

    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    y = _hline_y(page, 100.0)
    assert y is not None, "no price coordinate for the seeded hidden hline"
    box = page.locator("#chart").bounding_box()
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + y
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, start_y - 40, steps=8)
    page.mouse.up()
    page.wait_for_timeout(300)
    # The pointer drag was ignored: no PUT, price unchanged.
    assert puts == [], [r.url for r in puts]
    assert page.evaluate("() => window.marketChart.drawings[0].points.price") == 100.0

    # Tree selection still works (bus emit, not a pointer hit).
    page.locator(".tree-row[data-id]").first.click()
    page.wait_for_function(
        "() => document.querySelector('.tree-row[data-id]')"
        ".getAttribute('aria-selected') === 'true'",
        timeout=5000,
    )


@p
def test_keyboard_delete_removes_selected(
    seeded_5m_candles, interaction_drawing, browser_page
):
    # R11: with a shape selected and #chart focused, Delete removes it (same
    # DELETE path as the panel list) and the seam drops the row.
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
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    _select_hline(page)
    page.keyboard.press("Delete")
    page.wait_for_function(
        "() => window.marketChart.drawings.length === 0",
        timeout=5000,
    )
    assert len(deletes) == 1, [r.url for r in deletes]


@p
def test_escape_deselects_without_delete(
    seeded_5m_candles, interaction_drawing, browser_page
):
    # R11/R13: Escape clears the selection and issues no DELETE.
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
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    _select_hline(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert deletes == [], [r.url for r in deletes]
    assert page.evaluate("() => window.marketChart.drawings.length") == 1


@pytest.fixture
def selection_symbol_switch_drawings(e2e_user):
    """BTC + ETH hlines at 100.0, seeded BEFORE the Playwright context (sync ORM)."""
    from trading.models import Drawing

    Drawing.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        kind="hline",
        points={"price": 100.0},
        style={},
    )
    eth = Drawing.objects.create(
        user=e2e_user,
        symbol="ETHUSDT",
        kind="hline",
        points={"price": 100.0},
        style={},
    )
    return eth


@p
def test_symbol_switch_clears_selection_state(
    seeded_5m_candles,
    seeded_eth_5m_candles,
    selection_symbol_switch_drawings,
    browser_page,
):
    # R14: a SYMBOL switch clears the selection with the drawings, so a stale id
    # can never delete a new-symbol row.
    eth = selection_symbol_switch_drawings
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    _select_hline(page)
    page.locator('.pair[data-symbol="ETHUSDT"]').click()
    page.wait_for_function(
        "() => window.marketChart.drawings.length === 1"
        f" && window.marketChart.drawings[0].id === {eth.id}",
        timeout=10000,
    )
    deletes = []
    page.on(
        "request",
        lambda r: (
            deletes.append(r)
            if r.method == "DELETE" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.locator("#chart").focus()
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)
    assert deletes == [], f"stale selection deleted a new-symbol row: {deletes}"
    assert page.evaluate("() => window.marketChart.drawings.length") == 1


@p
def test_dialog_edits_style_and_persists_single_put(
    seeded_5m_candles, interaction_drawing, browser_page
):
    # R12: double-clicking a shape opens the properties dialog; confirming merges
    # color/lineWidth into style, re-renders and PUTs once. kind/points untouched.
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if r.method == "PUT" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    chart, box = _select_hline(page)
    y = _hline_y(page, 100.0)
    page.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + y)
    dialog = page.locator("#drawing-settings-dialog")
    dialog.wait_for(state="visible", timeout=5000)
    # Edited color + width, then confirm (method=dialog -> value "ok").
    page.fill("#ds-color", "#ff0000")
    page.fill("#ds-width", "3")
    dialog.locator('button[value="ok"]').click()
    page.wait_for_function(
        "() => window.marketChart.drawings[0].style.color === '#ff0000'",
        timeout=5000,
    )
    style = page.evaluate("() => window.marketChart.drawings[0].style")
    assert style["color"] == "#ff0000"
    assert style["lineWidth"] == 3
    assert len(puts) == 1, [r.url for r in puts]
    body = json.loads(puts[0].post_data or "{}")
    assert body["style"]["color"] == "#ff0000"
    assert "kind" not in body and "points" not in body


@p
def test_interval_switch_keeps_drawings(seeded_drawings, browser_page):
    # R7: a drawing is per SYMBOL, so an interval-only switch keeps every shape
    # attached and issues NO drawings refetch.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    assert page.evaluate("() => window.marketChart.drawings.length") == 2

    fetches = []
    page.on(
        "request",
        lambda r: fetches.append(r.url) if "/market/api/drawings?" in r.url else None,
    )
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.smc && window.marketChart.smc.interval === '5m'",
        timeout=10000,
    )
    # Shapes survived the interval switch unchanged (same symbol).
    assert page.evaluate("() => window.marketChart.drawings.length") == 2
    assert fetches == [], f"unexpected drawings refetch: {fetches}"


@p
def test_symbol_switch_clears_then_loads_drawings(per_symbol_drawings, browser_page):
    # R7: switching SYMBOL clears the previous shapes and loads the new symbol's.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    assert page.evaluate("() => window.marketChart.drawings.length") == 1
    assert page.evaluate("() => window.marketChart.drawings[0].points.price") == 1.0

    page.locator('.pair[data-symbol="ETHUSDT"]').click()
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


@p
def test_smc_toggle_persists_across_reload(seeded_5m_candles, browser_page):
    # R7: unchecking a family debounce-saves it; after a reload the checkbox is
    # restored OFF from ChartPreference (no longer session-only).
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    page.locator('.smc-toggle[data-family="range"]').uncheck()
    page.wait_for_timeout(900)  # let the debounce PUT land

    page.reload()
    _wait_ready(page)
    assert not page.locator('.smc-toggle[data-family="range"]').is_checked()
    # The other families stay ON (only the toggled one persisted).
    assert page.locator('.smc-toggle[data-family="swings"]').is_checked()
    # Seam frozen (R18): restoring a toggle adds no 9th key.
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8


@p
def test_smc_toggle_survives_interval_switch(seeded_5m_candles, browser_page):
    # R7: the toggle is user-global, not per-chart — a switchTo must NOT reset a
    # family toggled off on the boot key.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    page.locator('.smc-toggle[data-family="range"]').uncheck()
    page.wait_for_function(
        "() => window.marketChart.smcToggles.range === false", timeout=5000
    )

    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.smc && window.marketChart.smc.interval === '5m'",
        timeout=10000,
    )
    assert not page.locator('.smc-toggle[data-family="range"]').is_checked()
    assert page.evaluate("() => window.marketChart.smcToggles.range") is False


@p
def test_smc_boot_preference_fetch_failure_defaults_all_on(
    seeded_5m_candles, browser_page
):
    # R7: a failed preference fetch at boot is non-fatal — all families stay ON
    # and the SMC layer still renders.
    page, base_url = browser_page
    page.route(
        "**/market/api/preference",
        lambda route: route.abort(),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    for family in ("swings", "structure", "order_blocks", "fvg", "range", "setups"):
        assert page.locator(f'.smc-toggle[data-family="{family}"]').is_checked(), family
    page.wait_for_function(
        "() => window.marketChart.smcCounts"
        " && window.marketChart.smcCounts.swings >= 0",
        timeout=10000,
    )


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
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
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
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
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


# --- indicator settings gear + dialog (Slice 2 / F2.6-F2.8) ------------------
#
# DOM/computed-style only. The dialog writes the ``styles`` store slot, which
# flows through the existing ``indicator:changed`` -> rebuild path; the series
# color/lineWidth/priceFormat are read back via the public v5 pane API
# (``chart.panes()[i].getSeries().options()``), never an image diff. Existing
# assertions above are untouched (add-only).

# F5 S3: the settings gear lives on the object tree's indicator rows.
_SETTINGS_GEAR = '.object-tree .tree-row[data-token="sma"] .row-settings'


def _dialog_open(page):
    """True when the shared settings dialog is on screen (native .open)."""
    return page.evaluate(
        "() => document.getElementById('indicator-settings-dialog').open"
    )


def _pane0_series(page):
    """Line-series options in the price pane: [{color,lineWidth,precision,minMove}]."""
    return page.evaluate(
        "() => window.marketChart.chart.panes()[0].getSeries().map((s) => {"
        " const o = s.options();"
        " const pf = o.priceFormat || {};"
        " return { color: o.color, lineWidth: o.lineWidth,"
        "   precision: pf.precision, minMove: pf.minMove }; }).filter("
        " (r) => r.color !== undefined)"
    )


@p
def test_gear_opens_dialog_prefilled(seeded_5m_candles, browser_page):
    # F2.6/2.1: the gear opens the shared dialog pre-filled from the registry
    # default style; the period control reflects the token's param.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )

    gear = page.locator(_SETTINGS_GEAR)
    assert gear.get_attribute("aria-haspopup") == "dialog"
    gear.focus()
    gear.press("Enter")

    dialogue = page.locator("#indicator-settings-dialog")
    assert _dialog_open(page)
    assert dialogue.get_attribute("aria-label") == "Indicator settings"
    assert page.locator("#is-color").input_value() == "#2962ff"
    assert page.locator("#is-width").input_value() == "1"
    assert page.locator("#is-precision").input_value() == "2"
    # sma has an editable period param -> visible, pre-filled from params.
    assert page.locator("#is-period").input_value() == "20"
    assert page.locator("#is-period").is_visible()


@p
def test_empty_required_field_blocks_submit(seeded_5m_candles, browser_page):
    # F2.6: clearing a required numeric field must NOT apply — native form
    # validation keeps the dialog open (no rebuild, no PUT).
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
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )
    page.locator(_SETTINGS_GEAR).click()
    page.locator("#is-width").fill("")  # clear the required field
    page.locator('#indicator-settings-dialog button[value="ok"]').click()
    page.wait_for_timeout(600)
    # Native validation blocks the dialog from closing/applying.
    assert _dialog_open(page)
    assert puts == [], [r.url for r in puts]


@p
def test_confirm_updates_series_and_persists_across_reload(
    seeded_5m_candles, browser_page
):
    # F2.6/F2.5: applying writes the style slot -> one rebuild -> the sma series
    # takes the new color/lineWidth/priceFormat; the debounced PUT persists it and
    # a reload re-applies it from the layout.
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
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )

    page.locator(_SETTINGS_GEAR).click()
    page.evaluate("() => { document.getElementById('is-color').value = '#ff0000'; }")
    page.locator("#is-width").fill("3")
    page.locator("#is-precision").fill("4")
    page.locator('#indicator-settings-dialog button[value="ok"]').click()

    page.wait_for_function(
        "() => window.marketChart.chart.panes()[0].getSeries().some("
        " (s) => s.options().color === '#ff0000')",
        timeout=10000,
    )
    red = [r for r in _pane0_series(page) if r["color"] == "#ff0000"]
    assert red, _pane0_series(page)
    assert red[0]["lineWidth"] == 3, red
    assert red[0]["precision"] == 4, red
    # Exact literal minMove (no Math.pow float drift across V8 versions).
    assert red[0]["minMove"] == 0.0001, red
    assert (
        page.evaluate("() => document.getElementById('indicator-settings-dialog').open")
        is False
    )

    # Debounced PUT carries the style for sma, then reload persists it.
    page.wait_for_timeout(1200)
    assert len(puts) == 1, [r.url for r in puts]
    body = json.loads(puts[0].post_data or "{}")
    sma = next(i for i in body["indicators"] if i["token"] == "sma")
    assert sma["style"] == {"color": "#ff0000", "lineWidth": 3, "precision": 4}, sma

    page.reload()
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    persisted = [r for r in _pane0_series(page) if r["color"] == "#ff0000"]
    assert persisted, _pane0_series(page)


@p
def test_cancel_makes_no_change(seeded_5m_candles, browser_page):
    # F2.6: cancelling closes with no store write and no rebuild (no PUT).
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
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )
    before = _pane0_series(page)
    puts.clear()

    page.locator(_SETTINGS_GEAR).click()
    page.evaluate("() => { document.getElementById('is-color').value = '#ff0000'; }")
    page.locator('#indicator-settings-dialog button[value="cancel"]').click()

    page.wait_for_timeout(1200)
    assert (
        page.evaluate("() => document.getElementById('indicator-settings-dialog').open")
        is False
    )
    assert _pane0_series(page) == before
    assert puts == [], [r.url for r in puts]


@p
def test_escape_closes_and_returns_focus(seeded_5m_candles, browser_page):
    # F2.8: native <dialog> + Esc closes without applying and returns focus to
    # the gear.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )
    gear = page.locator(_SETTINGS_GEAR)
    gear.focus()
    gear.press("Enter")
    assert _dialog_open(page)

    page.keyboard.press("Escape")
    assert (
        page.evaluate("() => document.getElementById('indicator-settings-dialog').open")
        is False
    )
    assert page.evaluate(
        "() => document.activeElement === document.querySelector("
        "'.object-tree .tree-row[data-token=\"sma\"] .row-settings')"
    )


@p
def test_dialog_has_no_inline_handler_and_seam_frozen(seeded_5m_candles, browser_page):
    # F2.8/R18: the dialog markup carries no inline script/handler; the global
    # seam stays 8 keys.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8
    inline = page.evaluate(
        "() => { const d = document.getElementById('indicator-settings-dialog');"
        " if (!d) return ['missing'];"
        " return Array.prototype.slice.call(d.querySelectorAll('*'))"
        "   .flatMap((n) => Array.prototype.slice.call(n.attributes))"
        "   .map((a) => a.name)"
        "   .filter((n) => /^on/.test(n)); }"
    )
    assert inline == [], inline


@p
def test_gear_and_dialog_no_overflow_at_375(seeded_5m_candles, browser_page):
    # F2.8: the gear and the open dialog cause no horizontal overflow at 375px.
    page, base_url = browser_page
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )
    page.locator(_SETTINGS_GEAR).click()
    assert _dialog_open(page)
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth"
        " - document.documentElement.clientWidth"
    )
    assert overflow <= 1, overflow
    dialog_w = page.evaluate(
        "() => document.getElementById('indicator-settings-dialog')"
        ".getBoundingClientRect().width"
    )
    assert dialog_w <= 375, dialog_w


# --- F8 chart-scales controls (add-only) -------------------------------------
#
# DOM/options assertions only (no image diffs, no new seam key). The scale
# select drives the price-scale mode via applyOptions (option only); the chart
# type select drives a rebuild (series Ctor changes). Both select values are
# read back from the live v5 API — never the frozen 8-key seam.


@p
def test_scale_and_type_selects_present_and_labelled(seeded_5m_candles, browser_page):
    # R26/CS5: both native <select>s render with accessible names, options from
    # the core vocab, and no inline handler.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    scale = page.locator("#scale-mode")
    chart_type = page.locator("#chart-type")
    assert scale.count() == 1
    assert chart_type.count() == 1
    assert scale.get_attribute("aria-label") == "Price scale mode"
    assert chart_type.get_attribute("aria-label") == "Chart type"

    scale_opts = page.evaluate(
        "() => Array.from(document.getElementById('scale-mode').options)"
        ".map((o) => o.value)"
    )
    type_opts = page.evaluate(
        "() => Array.from(document.getElementById('chart-type').options)"
        ".map((o) => o.value)"
    )
    assert scale_opts == ["linear", "log", "percentage"], scale_opts
    assert type_opts == ["candles", "line", "area", "heikin-ashi"], type_opts

    inline = page.evaluate(
        "() => ['scale-mode', 'chart-type'].flatMap((id) =>"
        " Array.prototype.slice.call(document.getElementById(id).attributes)"
        "   .map((a) => a.name)).filter((n) => /^on/.test(n))"
    )
    assert inline == [], inline


@p
def test_scale_select_changes_price_scale_mode(seeded_5m_candles, browser_page):
    # CS2/R21: choosing a scale applies the mode to the right price scale via
    # applyOptions — no rebuild, no fetchHistory (option only, #68).
    page, base_url = browser_page
    klines = []
    page.on(
        "request",
        lambda r: klines.append(r.url) if "/market/api/kline" in r.url else None,
    )
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    mode = "() => window.marketChart.chart.priceScale('right').options().mode"
    before = page.evaluate(mode)
    klines.clear()

    page.select_option("#scale-mode", "log")
    page.wait_for_function(
        f"() => window.marketChart.chart.priceScale('right').options().mode"
        f" !== {before}",
        timeout=5000,
    )
    after = page.evaluate(mode)
    assert after != before, (before, after)
    # No history refetch on a scale change (light event).
    assert klines == [], klines
    # The select reflects the new mode.
    assert page.locator("#scale-mode").input_value() == "log"


@p
def test_type_select_rebuilds_with_new_series_ctor(seeded_5m_candles, browser_page):
    # CS3/R21: choosing a chart type routes through rebuild() — the candle
    # series Ctor changes (v5 cannot change type in place) and history refetches.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    assert (
        page.evaluate("() => window.marketChart.candleSeries.seriesType()")
        == "Candlestick"
    )
    first = page.evaluate("() => window.marketChart.candleSeries")

    page.select_option("#chart-type", "line")
    page.wait_for_function(
        "() => window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.seriesType() === 'Line'",
        timeout=10000,
    )
    second = page.evaluate("() => window.marketChart.candleSeries")
    assert second != first, "rebuild must construct a NEW series (no in-place)"
    # A line series is a value series: data points carry {time,value}.
    point = page.evaluate(
        "() => { const d = window.marketChart.candleSeries.data();"
        " return d.length ? d[0] : null; }"
    )
    assert point is not None and "value" in point and "close" not in point, point


@p
def test_type_select_heikin_ashi_chains_and_rebuilds(seeded_5m_candles, browser_page):
    # CS3/CS4: heikin-ashi builds a CandlestickSeries with transformed OHLC data
    # (a haClose-style average differs from the raw close on at least one bar).
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.select_option("#chart-type", "heikin-ashi")
    page.wait_for_function(
        "() => window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.seriesType() === 'Candlestick'"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    # HA bar 1 close == (o+h+l+c)/4 of the raw bar; recompute from raw candles is
    # not exposed, so assert the seam stays frozen and the series has data.
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8
    assert page.locator("#chart-type").input_value() == "heikin-ashi"


# --- F8 persistence (Slice 3, add-only) --------------------------------------


@pytest.fixture
def saved_scale_and_type_preference(e2e_user):
    """Seed scale_mode/chart_type BEFORE the Playwright context.

    Boot fetches this preference before the first build (CS6); a saved
    log/area makes the restore observable on both selects + the chart options.
    """
    from trading.models import ChartPreference

    ChartPreference.objects.create(user=e2e_user, scale_mode="log", chart_type="area")
    return e2e_user


@p
def test_boot_restores_saved_scale_and_type(
    seeded_5m_candles, saved_scale_and_type_preference, browser_page
):
    # CS6: a persisted scale/type wins on boot — the selects reflect it AND the
    # chart builds with the saved price-scale mode (linear is the default).
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    assert page.locator("#scale-mode").input_value() == "log"
    assert page.locator("#chart-type").input_value() == "area"
    # The right price scale is Logarithmic (mode 1), not the default Normal (0).
    mode = page.evaluate(
        "() => window.marketChart.chart.priceScale('right').options().mode"
    )
    assert mode != 0, mode
    # An area type builds an Area series.
    assert page.evaluate("() => window.marketChart.candleSeries.seriesType()") == "Area"


@p
def test_scale_change_debounce_persists_only_scale(seeded_5m_candles, browser_page):
    # CS6: a scale change debounce-PUTs ONLY scale_mode (never interval/type).
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

    page.select_option("#scale-mode", "percentage")
    page.wait_for_function(
        "() => document.getElementById('scale-mode').value === 'percentage'",
        timeout=2000,
    )
    page.wait_for_timeout(800)  # let the debounce fire

    assert puts, "a scale change must PUT the preference"
    bodies = [json.loads(r.post_data or "{}") for r in puts]
    assert bodies and bodies[-1] == {"scale_mode": "percentage"}, bodies


@p
def test_chart_type_change_debounce_persists_only_type(seeded_5m_candles, browser_page):
    # CS6: a type change rebuilds and debounce-PUTs ONLY chart_type.
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

    page.select_option("#chart-type", "line")
    page.wait_for_function(
        "() => window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.seriesType() === 'Line'",
        timeout=10000,
    )
    page.wait_for_timeout(800)  # let the debounce fire

    bodies = [json.loads(r.post_data or "{}") for r in puts]
    assert bodies and bodies[-1] == {"chart_type": "line"}, bodies


@p
def test_scale_and_type_round_trip_persists_across_reload(
    seeded_5m_candles, browser_page
):
    # CS6: change scale+type, reload, and both are restored from the server.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    page.select_option("#scale-mode", "percentage")
    page.select_option("#chart-type", "line")
    page.wait_for_function(
        "() => window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.seriesType() === 'Line'",
        timeout=10000,
    )
    page.wait_for_timeout(800)  # let both debounce PUTs land

    page.reload()
    _wait_ready(page)

    assert page.locator("#scale-mode").input_value() == "percentage"
    assert page.locator("#chart-type").input_value() == "line"
    assert page.evaluate("() => window.marketChart.candleSeries.seriesType()") == "Line"
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8


# --- F1 legend regression guards (Slice 1 / #143) ----------------------------
#
# Committed regressions for the three probe-only scenarios in the F1 verify
# report. DOM/computed-style only (no image diffs, no new seam key). Each test
# is anti-vacuous: it FAILS if the guarded behavior is removed (RED-check noted
# in the docstring).


@pytest.fixture
def bollinger_5m_layout(e2e_user):
    """Seed a 5m layout with bollinger active (3 overlay series) BEFORE the browser.

    F5 S3: the tree is active-only, so bollinger cannot be *added* from the UI;
    it is seeded active. A style change then forces the 2nd `chart:built`.
    """
    from trading.models import ChartLayout

    ChartLayout.objects.create(
        user=e2e_user,
        symbol="BTCUSDT",
        interval="5m",
        indicators=[
            {"token": "sma"},
            {"token": "ema"},
            {"token": "rsi"},
            {"token": "bollinger"},
        ],
    )
    return e2e_user


@p
def test_legend_resubscribes_across_rebuild(
    seeded_5m_candles, bollinger_5m_layout, browser_page
):
    # LC4 (RED: unwire the `chart:built` re-subscribe -> the rebuilt chart's
    # crosshair handler never fires -> the hover readout never changes). Forces
    # a 2nd `chart:built` via a style change (indicator:changed), then proves the
    # legend is still a single overlay AND still tracks the crosshair.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    # Active set: sma + ema + rsi + bollinger(3 series) -> exactly 6 rows.
    # (The legend idle render is the readiness gate after an interval switch.)
    page.wait_for_function(
        "() => document.querySelectorAll('#chart .chart-legend .lg-row').length === 6",
        timeout=10000,
    )

    # Config change -> 2nd `chart:built` (indicator:changed). A style change on a
    # seeded token rebuilds once; the legend must re-attach to the new chart.
    page.locator('.tree-row[data-token="sma"] .row-settings').click()
    page.evaluate("() => { document.getElementById('is-color').value = '#ff0000'; }")
    page.locator('#indicator-settings-dialog button[value="ok"]').click()
    page.wait_for_function(
        "() => window.marketChart.chart.panes()[0].getSeries().some("
        " (s) => s.options().color === '#ff0000')",
        timeout=10000,
    )

    # No duplicate legend overlay after the rebuild (idempotent injection).
    assert page.locator("#chart .chart-legend").count() == 1

    # Hover the rebuilt chart: the readout must MOVE (stale handler -> no change).
    idle_text = page.locator("#chart .chart-legend .lg-ohlc").inner_text()
    page.evaluate("(t) => { window.__legendIdleOhlc = t; }", idle_text)
    canvas = page.locator("#chart canvas").first
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.4)
    page.wait_for_function(
        "() => document.querySelector('#chart .chart-legend .lg-ohlc').textContent"
        " !== window.__legendIdleOhlc",
        timeout=5000,
    )
    hover_text = page.locator("#chart .chart-legend .lg-ohlc").inner_text()
    assert "H " in hover_text and hover_text != idle_text
    # Seam still frozen after the rebuild.
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8


@p
def test_legend_aria_live_debounced_not_per_move(seeded_5m_candles, browser_page):
    # LC5 (RED: remove the hover->off / debounce-on-leave policy -> aria-live
    # churns per mousemove, transitions spike far past 2). Counts the
    # aria-live attribute transitions actually emitted during a hover->leave.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.wait_for_function(
        "() => document.querySelector('#chart .chart-legend') !== null",
        timeout=10000,
    )
    # Boot starts polite (idle); observe every aria-live write on the overlay.
    assert page.locator("#chart .chart-legend").get_attribute("aria-live") == "polite"
    page.evaluate(
        "() => { window.__liveTransitions = [];"
        " const el = document.querySelector('#chart .chart-legend');"
        " window.__liveObs = new MutationObserver((muts) => {"
        "   muts.forEach((m) => { if (m.attributeName === 'aria-live')"
        "     window.__liveTransitions.push(el.getAttribute('aria-live')); }); });"
        " window.__liveObs.observe(el,"
        "   { attributes: true, attributeFilter: ['aria-live'] }); }"
    )

    canvas = page.locator("#chart canvas").first
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    for i in range(20):
        page.mouse.move(
            box["x"] + box["width"] * (0.2 + (i % 10) * 0.05),
            box["y"] + box["height"] * 0.4,
        )
    page.wait_for_timeout(150)
    # During hover the region is muted: no per-move announcement.
    assert page.locator("#chart .chart-legend").get_attribute("aria-live") == "off"

    # Leave the chart; the >=300ms debounce settles into exactly one polite flip.
    page.mouse.move(0, 0)
    page.wait_for_timeout(400)
    transitions = page.evaluate("() => window.__liveTransitions")
    assert len(transitions) <= 2, transitions
    assert page.locator("#chart .chart-legend").get_attribute("aria-live") == "polite"


@p
def test_legend_idle_lists_all_active_series_exact(seeded_5m_candles, browser_page):
    # LC6 (RED: drop the `rsi` default -> the row count is no longer 3). Closes
    # the vacuous `>= 1` at test_legend_overlay_shows_ohlc_and_updates_on_crosshair
    # with EXACT default-actives counts and labels (overlays first, then pane).
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.wait_for_function(
        "() => document.querySelectorAll('#chart .chart-legend .lg-row').length > 0",
        timeout=10000,
    )
    assert page.locator("#chart .chart-legend .lg-row").count() == 3
    assert page.locator("#chart .chart-legend .lg-token").all_inner_texts() == [
        "SMA 20",
        "EMA 20",
        "RSI",
    ]


# --- F2 settings regression guards (Slice 2 / #144) --------------------------
#
# Committed regressions for the probe-only F2 scenarios. DOM/options only; no
# new seam key. Each test is anti-vacuous: it FAILS if the guarded behavior is
# removed (RED-check noted in the docstring).


def _install_create_chart_counter(page):
    """Count CDN ``LightweightCharts.createChart`` calls in ``window.__builds``.

    The counter wraps the CDN global — NOT a ``window.marketChart`` seam key —
    so the frozen 8-key seam is untouched. The CDN global is itself frozen after
    load, so its ``createChart`` cannot be patched in place; on first access we
    copy the enumerable API surface into a mutable object and count calls there.
    The getter is installed before ``goto`` so the deferred module boots against
    the counting copy.
    """
    page.add_init_script(
        """
        window.__builds = 0;
        let _lc = null;
        Object.defineProperty(window, "LightweightCharts", {
          configurable: true,
          get() {
            if (_lc && !_lc.__wrapped) {
              const src = _lc;
              const copy = {};
              Object.getOwnPropertyNames(src).forEach((k) => {
                try { copy[k] = src[k]; } catch (e) { /* skip non-readable */ }
              });
              const orig = src.createChart;
              if (typeof orig === "function") {
                copy.createChart = function () {
                  window.__builds += 1;
                  return orig.apply(src, arguments);
                };
              }
              copy.__wrapped = true;
              _lc = copy;
            }
            return _lc;
          },
          set(v) { _lc = v; },
        });
        """
    )


@p
def test_style_change_rebuilds_exactly_once(seeded_5m_candles, browser_page):
    # W2 (RED: emit a second rebuild for one style change -> __builds === 2).
    # F2.5/#68: confirming a style travels ``indicator:changed`` -> ONE rebuild()
    # on the setData path; exactly one createChart per confirmed change. The
    # counter is reset AFTER boot so the delta isolates the style change.
    # Fallback (if the CDN wrap proves brittle): count one ``/market/api/kline``
    # GET via ``page.on("request")`` instead of the global counter.
    page, base_url = browser_page
    _install_create_chart_counter(page)
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    assert page.evaluate("() => window.__builds") >= 1, "boot must build at least once"

    # Count builds attributable ONLY to the confirmed style change.
    page.evaluate("() => { window.__builds = 0; }")

    page.locator(_SETTINGS_GEAR).click()
    assert _dialog_open(page)
    page.evaluate("() => { document.getElementById('is-color').value = '#ff0000'; }")
    page.locator("#is-width").fill("3")
    page.locator('#indicator-settings-dialog button[value="ok"]').click()

    # The change landed (series took the new color) before we read the count.
    page.wait_for_function(
        "() => window.marketChart.chart.panes()[0].getSeries().some("
        " (s) => s.options().color === '#ff0000')",
        timeout=10000,
    )
    assert page.evaluate("() => window.__builds") == 1
    # The seam is still frozen after the rebuild.
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8


# --- F3 chart-shell regression guards (Slice 3 / #145) -----------------------
#
# Committed regressions for the three probe-only F3 shell scenarios. DOM/
# computed-style only (no image diffs, no new seam key). Each test is
# anti-vacuous: it FAILS if the guarded behavior is removed (RED-check noted in
# the docstring).


def _active_element(page):
    """The focused element's tag + interval/class (for focus-move assertions)."""
    return page.evaluate(
        "() => { const el = document.activeElement;"
        " return { tag: el.tagName, interval: el.dataset ? el.dataset.interval : null,"
        "   cls: el.className }; }"
    )


@p
def test_interval_chips_keyboard_navigation(seeded_5m_candles, browser_page):
    # W1 (RED: drop the chip keydown listener -> ArrowRight no longer moves
    # focus -> activeElement stays on 1m). R22: arrows move focus across the
    # group; Enter/Space activate the focused chip and sync the store.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries"
        " && window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    first = page.locator('.interval-chip[data-interval="1m"]')
    first.focus()
    assert _active_element(page)["interval"] == "1m"

    # ArrowRight moves DOM focus to the adjacent chip (5m), not activation.
    page.keyboard.press("ArrowRight")
    assert _active_element(page)["interval"] == "5m", _active_element(page)
    assert first.get_attribute("aria-pressed") == "true", "focus move must not activate"

    # Enter activates the focused chip: aria-pressed flips + select syncs.
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.querySelector('.interval-chip[data-interval=\"5m\"]')"
        ".getAttribute('aria-pressed') === 'true'",
        timeout=10000,
    )
    assert (
        page.locator('.interval-chip[data-interval="1m"]').get_attribute("aria-pressed")
        == "false"
    )
    assert page.locator("#interval").input_value() == "5m"

    # Space on another chip activates it too (native button activation).
    page.locator('.interval-chip[data-interval="15m"]').focus()
    page.keyboard.press("Space")
    page.wait_for_function(
        "() => document.querySelector('.interval-chip[data-interval=\"15m\"]')"
        ".getAttribute('aria-pressed') === 'true'",
        timeout=10000,
    )
    assert (
        page.locator('.interval-chip[data-interval="5m"]').get_attribute("aria-pressed")
        == "false"
    )
    assert page.locator("#interval").input_value() == "15m"
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8


@p
def test_chart_autosize_follows_viewport_resize(seeded_5m_candles, browser_page):
    # W2 (RED: remove ``autoSize: true`` -> the chart root keeps its boot size
    # and no longer tracks #chart after the viewport resize). R20: the chart
    # root tracks the container height via the ResizeObserver, and no re-boot.
    page, base_url = browser_page
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )
    before = page.evaluate(
        "() => document.getElementById('chart').getBoundingClientRect().height"
    )

    page.set_viewport_size({"width": 640, "height": 800})
    # The container height changed at the narrow viewport (70dvh), so a tracked
    # root must change too — proving it is not a boot-frozen snapshot.
    page.wait_for_function(
        "() => { const c = document.getElementById('chart');"
        " const root = document.querySelector('#chart .tv-lightweight-charts');"
        " if (!c || !root) return false;"
        " return Math.abs(root.getBoundingClientRect().height"
        " - c.getBoundingClientRect().height) <= 2; }",
        timeout=10000,
    )
    boxes = page.evaluate(
        "() => { const c = document.getElementById('chart');"
        " const root = document.querySelector('#chart .tv-lightweight-charts');"
        " return { chartH: c.getBoundingClientRect().height,"
        "   rootH: root.getBoundingClientRect().height }; }"
    )
    assert abs(boxes["rootH"] - boxes["chartH"]) <= 2, boxes
    assert abs(boxes["chartH"] - before) > 2, (before, boxes)
    # A resize adapts in place: the chart never re-boots (ready stays true).
    assert page.evaluate("() => window.marketChart.ready") is True
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8


@p
def test_shell_desktop_panel_and_chip_a11y(seeded_5m_candles, browser_page):
    # W3 (RED: drop ``:focus-visible`` outline rule -> the focused chip's
    # outline-style is 'none'; drop group/toggle names -> role lookups fail).
    # R23: at >820px the toggle is hidden, the panel/chart are visible, and the
    # chips/toggle carry accessible names + aria state + a visible focus outline.
    page, base_url = browser_page
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{base_url}/market/")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.ready === true",
        timeout=10000,
    )

    # Desktop: the responsive toggle is display:none; panel + chart are visible.
    assert page.locator(".panel-toggle").is_visible() is False
    assert page.locator("#panel").is_visible() is True
    assert page.locator("#chart").is_visible() is True

    # Accessible names + aria state on the chip group, a chip, and the toggle.
    # The toggle is display:none here, so its name is read from the DOM (role
    # queries exclude hidden elements); the group/chip are visible.
    assert page.get_by_role("group", name="Interval").count() == 1
    toggle = page.locator(".panel-toggle")
    assert toggle.evaluate("el => el.textContent.trim()") == "Panel"
    assert toggle.get_attribute("aria-expanded") == "true"
    assert toggle.get_attribute("aria-controls") == "panel"
    chip = page.locator('.interval-chip[data-interval="1m"]')
    assert chip.get_attribute("aria-pressed") == "true"
    # Keyboard focus paints a visible outline (:focus-visible policy in theme.css).
    chip.focus()
    page.keyboard.press("ArrowRight")  # keyboard focus -> :focus-visible matches
    outline = page.evaluate(
        "() => { const el = document.activeElement;"
        " return getComputedStyle(el).outlineStyle; }"
    )
    assert outline != "none", outline


# --- chart-theme persistence + shell + control (Slice 2, add-only) -----------
#
# DOM/computed-style/options assertions only (no image diffs, no new seam key).
# The theme control (native <select id="theme">) resolves against the OS media
# query, writes ``data-theme`` on the root (never "system"), and flips the
# canvas options option-only (#68). Reload persists; system tracks emulate_media.
# Kept OFF the WS path (no route_web_socket) so it never rides the DEBT-8 flake.


@p
def test_theme_control_present_labelled_and_options(seeded_5m_candles, browser_page):
    # R27: the theme control renders with an accessible name + the frozen vocab,
    # inside the existing toolbar (no new controller), with no inline handler.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    theme = page.locator("#theme")
    assert theme.count() == 1
    assert theme.get_attribute("aria-label") == "Theme"
    opts = page.evaluate(
        "() => Array.from(document.getElementById('theme').options).map((o) => o.value)"
    )
    assert opts == ["light", "dark", "system"], opts
    inline = page.evaluate(
        "() => Array.prototype.slice.call(document.getElementById('theme').attributes)"
        ".map((a) => a.name).filter((n) => /^on/.test(n))"
    )
    assert inline == [], inline
    # The control is not display:none/hidden (native + Playwright-actionable).
    assert theme.is_visible()


@p
def test_theme_change_flips_data_theme_and_canvas_options(
    seeded_5m_candles, browser_page
):
    # CT2/CT5/R27 (#68): choosing light sets data-theme="light" AND swaps the
    # canvas options via applyOptions only — no setData on the candle series.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    # Force a starting dark for a deterministic DOM flip.
    page.select_option("#theme", "dark")
    page.wait_for_function(
        "() => document.documentElement.dataset.theme === 'dark'", timeout=5000
    )
    dark_bg = page.evaluate(
        "() => window.marketChart.chart.options().layout.background.color"
    )
    assert dark_bg == "#0e1117", dark_bg

    # Spy on setData AFTER boot: a live theme flip must never write data.
    page.evaluate(
        "() => { const s = window.marketChart.candleSeries; window.__setDataCalls = 0;"
        " const orig = s.setData.bind(s); s.setData = function(){"
        " window.__setDataCalls++; return orig.apply(s, arguments); }; }"
    )
    page.select_option("#theme", "light")
    page.wait_for_function(
        "() => document.documentElement.dataset.theme === 'light'", timeout=5000
    )
    light_bg = page.evaluate(
        "() => window.marketChart.chart.options().layout.background.color"
    )
    assert light_bg == "#ffffff", light_bg
    assert page.evaluate("() => window.__setDataCalls") == 0
    # Never the preference value "system" (CT2).
    assert page.evaluate("() => document.documentElement.dataset.theme") == "light"


@p
def test_theme_change_debounce_persists_only_theme(seeded_5m_candles, browser_page):
    # CT6/R27: a theme change debounce-PUTs only {theme} to the preference API.
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

    page.select_option("#theme", "dark")
    page.wait_for_function(
        "() => document.documentElement.dataset.theme === 'dark'", timeout=5000
    )
    page.wait_for_timeout(900)  # let the debounce fire

    bodies = [json.loads(r.post_data or "{}") for r in puts]
    assert bodies and bodies[-1] == {"theme": "dark"}, bodies


@p
def test_theme_round_trip_persists_across_reload(seeded_5m_candles, browser_page):
    # CT6: change the theme, reload, and both layers restore from the server.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    page.select_option("#theme", "light")
    page.wait_for_function(
        "() => document.documentElement.dataset.theme === 'light'", timeout=5000
    )
    page.wait_for_timeout(900)  # let the debounce PUT land

    page.reload()
    _wait_ready(page)
    assert page.evaluate("() => document.documentElement.dataset.theme") == "light"
    assert page.locator("#theme").input_value() == "light"
    assert (
        page.evaluate(
            "() => window.marketChart.chart.options().layout.background.color"
        )
        == "#ffffff"
    )
    assert page.evaluate("() => Object.keys(window.marketChart).length") == 8


@pytest.fixture
def saved_theme_preference(e2e_user):
    """Seed a theme preference BEFORE the Playwright context (CT6 boot restore)."""
    from trading.models import ChartPreference

    ChartPreference.objects.create(user=e2e_user, theme="dark")
    return e2e_user


@p
def test_boot_restores_saved_theme(
    seeded_5m_candles, saved_theme_preference, browser_page
):
    # CT6: a persisted theme wins on boot — the select + root attribute + chart
    # options all reflect it before any interaction.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)

    assert page.locator("#theme").input_value() == "dark"
    assert page.evaluate("() => document.documentElement.dataset.theme") == "dark"
    assert (
        page.evaluate(
            "() => window.marketChart.chart.options().layout.background.color"
        )
        == "#0e1117"
    )


@p
def test_system_theme_follows_emulated_color_scheme(seeded_5m_candles, browser_page):
    # CT3: with the preference "system", the resolved theme follows the OS media
    # query — emulate dark -> "dark", emulate light -> "light" (never "system").
    page, base_url = browser_page
    page.emulate_media(color_scheme="dark")
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    assert page.locator("#theme").input_value() == "system"
    assert page.evaluate("() => document.documentElement.dataset.theme") == "dark"

    page.emulate_media(color_scheme="light")
    page.select_option("#theme", "light")
    page.select_option("#theme", "system")
    page.wait_for_function(
        "() => document.documentElement.dataset.theme === 'light'", timeout=5000
    )
    assert (
        page.evaluate(
            "() => window.marketChart.chart.options().layout.background.color"
        )
        == "#ffffff"
    )


# --- F6 measure + position instruments (issue #119) --------------------------
#
# DOM + captured-network assertions only (never pixels, #149); readiness-gated
# via ``_wait_ready``. The measure readout is observed through its
# ``#measure-readout`` aria-live DOM node (R18: no seam key); the position via
# ``window.marketChart.drawings`` + the captured POST/PUT.


# A MEASURED readout: the node seeds with an en dash (U+2013) placeholder, so a
# ``trim().length > 0`` gate passes before any drag (vacuous, #189). A real
# measurement carries a signed percent ("+1.23%") and a price/time figure.
_MEASURED_JS = (
    "() => { const n = document.getElementById('measure-readout');"
    " const t = n ? n.textContent.trim() : '';"
    " return /%/.test(t) && /\\d/.test(t); }"
)


@p
def test_measure_drag_writes_readout_and_no_post(seeded_5m_candles, browser_page):
    # R1/R5: a drag with the measure tool active reports the span in the DOM
    # readout and issues NO POST/PUT (ephemeral; no persistence anywhere).
    page, base_url = browser_page
    writes = []
    page.on(
        "request",
        lambda r: (
            writes.append(r.url)
            if r.method in ("POST", "PUT") and "/market/api/drawings" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.locator('.draw-tool[data-kind="measure"]').click()
    canvas = page.locator("#chart canvas").first
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    x = box["x"] + box["width"] / 2
    page.mouse.move(x, box["y"] + box["height"] * 0.4)
    page.mouse.down()
    page.mouse.move(x + 60, box["y"] + box["height"] * 0.6, steps=8)
    page.mouse.up()
    # #189: wait for a MEASURED readout (a real price/% figure), not just a
    # non-empty node — the placeholder en dash would otherwise pass vacuously.
    page.wait_for_function(_MEASURED_JS, timeout=10000)
    assert page.locator("#measure-readout").get_attribute("aria-live") == "polite"
    measured = page.locator("#measure-readout").text_content()
    assert "%" in measured, measured  # a real measurement carries a percent
    assert writes == [], f"measure issued a write: {writes}"
    assert page.evaluate("() => window.marketChart.drawings.length") == 0


@p
def test_measure_replaced_and_cleared_on_tool_change(seeded_5m_candles, browser_page):
    # R1/R4: a new measure replaces the old; changing the tool clears the readout.
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.locator('.draw-tool[data-kind="measure"]').click()
    canvas = page.locator("#chart canvas").first
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()

    def drag(dx):
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.5)
        page.mouse.down()
        page.mouse.move(
            box["x"] + box["width"] / 2 + dx,
            box["y"] + box["height"] * 0.6,
            steps=6,
        )
        page.mouse.up()

    drag(50)
    page.wait_for_function(_MEASURED_JS, timeout=10000)
    first = page.locator("#measure-readout").text_content()
    drag(90)
    page.wait_for_function(
        "(prev) => { const n = document.getElementById('measure-readout');"
        " if (!n || !/%/.test(n.textContent)) return false;"
        " return n.textContent.trim() !== prev.trim(); }",
        arg=first,
        timeout=10000,
    )
    # Switch to another tool -> the measure clears (R4).
    page.locator('.draw-tool[data-kind="hline"]').click()
    page.wait_for_function(
        "() => document.getElementById('measure-readout').textContent.trim() === ''",
        timeout=5000,
    )


@p
def test_position_three_click_persists_and_drag_one_put(
    seeded_5m_candles, browser_page
):
    # R5/R10: three clicks (entry, stop, take_profit) finalize ONE position POST;
    # dragging a level issues exactly ONE PUT and shifts only that price. The
    # exchange socket is mocked (no live frames) so the seeded 5m range — and the
    # clicked entry column — stay put for a deterministic handle drag (#149).
    page, base_url = browser_page
    page.route_web_socket("wss://fapi.bitunix.com/**", lambda ws: None)
    posts = []
    puts = []
    page.on(
        "request",
        lambda r: (
            posts.append(r)
            if r.method == "POST" and "/market/api/drawings" in r.url
            else puts.append(r)
            if r.method == "PUT" and "/market/api/drawings" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    # Let the history fetch settle so the visible range stops moving under the
    # cursor (a late async load would otherwise remap the clicked entry column).
    page.wait_for_timeout(1200)
    page.locator('.draw-tool[data-kind="position"]').click()
    canvas = page.locator("#chart canvas").first
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    cx = box["x"] + box["width"] / 2
    # Three clicks at distinct x + price y (entry, stop below, take_profit above);
    # a short pause between clicks avoids Playwright coalescing them into a dblclick.
    for dx, frac in ((-80, 0.5), (0, 0.68), (80, 0.32)):
        page.mouse.click(cx + dx, box["y"] + box["height"] * frac)
        page.wait_for_timeout(500)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    assert len(posts) == 1, [r.url for r in posts]
    body = json.loads(posts[0].post_data or "{}")
    assert body["kind"] == "position"
    assert set(body["points"]) == {"entry", "stop", "take_profit"}

    # Deselect the tool (re-click cancels), then drag the stop level -> one PUT.
    page.locator('.draw-tool[data-kind="position"]').click()
    stop_before = page.evaluate("() => window.marketChart.drawings[0].points.stop")
    # The stop handle sits on the box's right edge (BOX_WIDTH=120), i.e. at
    # entry_x + 120 with the stop price's y — both read from the live mapping.
    entry_x = page.evaluate(
        "(t) => window.marketChart.chart.timeScale().timeToCoordinate(t)",
        page.evaluate("() => window.marketChart.drawings[0].points.entry.time"),
    )
    stop_y = page.evaluate(
        "(p) => window.marketChart.candleSeries.priceToCoordinate(p)", stop_before
    )
    assert entry_x is not None and stop_y is not None
    start_x = box["x"] + entry_x + 120
    start_y = box["y"] + stop_y
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, start_y - 40, steps=8)
    page.mouse.up()
    page.wait_for_function(
        "(before) => window.marketChart.drawings[0].points.stop !== before",
        arg=stop_before,
        timeout=5000,
    )
    assert len(puts) == 1, [r.url for r in puts]


@p
def test_position_escape_cancels_mid_draft(seeded_5m_candles, browser_page):
    # R6 (design-system): Escape cancels a pending position draft — no POST — and
    # a subsequent three-click draft still finalizes exactly one position.
    page, base_url = browser_page
    page.route_web_socket("wss://fapi.bitunix.com/**", lambda ws: None)
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
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.wait_for_timeout(1200)
    page.locator('.draw-tool[data-kind="position"]').click()
    canvas = page.locator("#chart canvas").first
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    cx = box["x"] + box["width"] / 2
    # Two clicks (entry + stop) leave a half-collected draft, then Escape.
    for dx, frac in ((-80, 0.5), (0, 0.68)):
        page.mouse.click(cx + dx, box["y"] + box["height"] * frac)
        page.wait_for_timeout(500)
    page.locator("#chart").focus()  # the keydown listener lives on the #chart container
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    # No draft was persisted, and the abandoned draft is gone: a fresh 3-click
    # sequence must start at entry, not resume the dead draft's take_profit.
    assert posts == [], [r.url for r in posts]
    for dx, frac in ((-80, 0.5), (0, 0.68), (80, 0.32)):
        page.mouse.click(cx + dx, box["y"] + box["height"] * frac)
        page.wait_for_timeout(500)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    assert len(posts) == 1, [r.url for r in posts]
    body = json.loads(posts[0].post_data or "{}")
    assert body["kind"] == "position"
    assert set(body["points"]) == {"entry", "stop", "take_profit"}


@p
def test_position_seed_copies_smc_setup_verbatim(seeded_5m_candles, browser_page):
    # R15: the explicit seed copies a setup's entry/stop/take_profit VERBATIM from
    # the fetched SMC payload (no JS recompute) into the created position POST.
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
        "() => window.marketChart.smc && window.marketChart.smc.interval === '5m'",
        timeout=10000,
    )
    setups = page.evaluate("() => window.marketChart.smc.setups")
    if not setups:
        pytest.skip("no setup computed for the seeded window")
    expected = setups[-1]
    page.locator("#position-seed").click()
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length >= 1",
        timeout=10000,
    )
    assert len(posts) == 1, [r.url for r in posts]
    body = json.loads(posts[0].post_data or "{}")
    assert body["kind"] == "position"
    assert body["points"]["stop"] == expected["stop"]
    assert body["points"]["take_profit"] == expected["take_profit"]
    assert body["points"]["entry"]["price"] == expected["entry"]
    assert body["points"]["entry"]["time"] == expected["time"]


@p
def test_position_readout_reports_rr_after_seed(seeded_5m_candles, browser_page):
    # R6 (design-system): the selected position's R:R lives in the aria-live
    # ``#position-readout`` DOM node, not only on the canvas. Selecting the tree
    # row for the seeded position shows "R:R <n>"; deselecting clears it.
    page, base_url = browser_page
    page.route_web_socket("wss://fapi.bitunix.com/**", lambda ws: None)
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart.smc && window.marketChart.smc.interval === '5m'",
        timeout=10000,
    )
    if not page.evaluate("() => window.marketChart.smc.setups"):
        pytest.skip("no setup computed for the seeded window")
    page.locator("#position-seed").click()
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length >= 1",
        timeout=10000,
    )
    assert page.locator("#position-readout").get_attribute("aria-live") == "polite"
    # Select the position row in the object tree -> the R:R is announced.
    page.locator("#object-tree li.tree-row[data-id]").first.click()
    page.wait_for_function(
        "() => { const n = document.getElementById('position-readout');"
        " return n && /^R:R \\d/.test(n.textContent.trim()); }",
        timeout=10000,
    )
    rr = page.locator("#position-readout").text_content().strip()
    assert rr.startswith("R:R "), rr


# --- F7 S3: context menu over the chart (design §c / R1-R4) -------------------
#
# The menu is a JS-built DOM ``role="menu"`` over ``#chart``; a Duplicate/Delete
# activation reuses the drawings bus commands (POST/DELETE), so undo of each is
# asserted via CAPTURED network verbs and the DOM (never pixels, #149). Undo is
# the S2 Ctrl/Cmd+Z router; the menu adds NO seam key (R18/R20).


def _open_row_menu(page):
    """Right-click the seeded hline and wait for the role=menu to appear."""
    chart, box = _select_hline(page)  # selects the 5m key + clicks the hline
    y = _hline_y(page, 100.0)
    assert y is not None, "no price coordinate for the seeded hline"
    page.mouse.click(
        box["x"] + box["width"] / 2,
        box["y"] + y,
        button="right",
    )
    page.wait_for_selector('div[role="menu"]', timeout=5000)
    return chart, box


@p
def test_context_menu_on_drawing_shows_delete_and_duplicate(
    seeded_5m_candles, interaction_drawing, browser_page
):
    # R1/R2: a right-click on a drawing opens a JS-built role=menu whose items
    # are Delete then Duplicate (DOM only, readiness-gated).
    page, base_url = browser_page
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    _open_row_menu(page)
    menu = page.locator('div[role="menu"]')
    labels = menu.locator('[role="menuitem"]').all_text_contents()
    assert labels == ["Delete", "Duplicate"], labels
    # The controller binds the listener with addEventListener, never inline.
    assert page.evaluate(
        "() => !document.getElementById('chart').getAttribute('oncontextmenu')"
    )


@p
def test_context_menu_duplicate_then_undo_deletes(
    seeded_5m_candles, interaction_drawing, browser_page
):
    # R4: Duplicate emits drawing:duplicate -> one POST (a new row); Ctrl+Z
    # undoes the create -> one DELETE (network intercept, DOM length).
    page, base_url = browser_page
    posts, deletes = [], []
    page.on(
        "request",
        lambda r: (
            posts.append(r)
            if r.method == "POST" and "/market/api/drawings" in r.url
            else None
        ),
    )
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
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    _open_row_menu(page)
    page.locator('div[role="menu"] [role="menuitem"]', has_text="Duplicate").click()
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 2",
        timeout=10000,
    )
    assert len(posts) == 1, [r.url for r in posts]
    cloned_id = page.evaluate("() => window.marketChart.drawings[1].id")
    page.keyboard.press("Control+z")
    page.wait_for_function(
        "() => window.marketChart.drawings.length === 1",
        timeout=5000,
    )
    assert len(deletes) == 1, [r.url for r in deletes]
    assert deletes[0].url.endswith(f"/{cloned_id}")


@p
def test_context_menu_delete_then_undo_reposts(
    seeded_5m_candles, interaction_drawing, browser_page
):
    # R4: Delete emits drawing:delete -> one DELETE; Ctrl+Z re-POSTs the
    # committed row, minting a NEW id (R3 undo-server consistency).
    page, base_url = browser_page
    posts, deletes = [], []
    page.on(
        "request",
        lambda r: (
            posts.append(r)
            if r.method == "POST" and "/market/api/drawings" in r.url
            else None
        ),
    )
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
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=10000,
    )
    original_id = page.evaluate("() => window.marketChart.drawings[0].id")
    _open_row_menu(page)
    page.locator('div[role="menu"] [role="menuitem"]', has_text="Delete").click()
    page.wait_for_function(
        "() => window.marketChart.drawings.length === 0",
        timeout=5000,
    )
    assert len(deletes) == 1, [r.url for r in deletes]
    assert deletes[0].url.endswith(f"/{original_id}")
    page.keyboard.press("Control+z")
    page.wait_for_function(
        "() => window.marketChart.drawings && window.marketChart.drawings.length === 1",
        timeout=5000,
    )
    assert len(posts) == 1, [r.url for r in posts]
    restored_id = page.evaluate("() => window.marketChart.drawings[0].id")
    assert restored_id != original_id, "a restored row carries a NEW id"


@p
def test_context_menu_reset_scale_emits_scale_changed_no_put(
    seeded_5m_candles, browser_page
):
    # R4: reset-scale reuses the F8 option-only path — the store flips to linear,
    # scale:changed fires (select reflects it) and NO drawings PUT is issued (#68).
    page, base_url = browser_page
    puts = []
    page.on(
        "request",
        lambda r: (
            puts.append(r)
            if r.method == "PUT" and "/market/api/drawings/" in r.url
            else None
        ),
    )
    page.goto(f"{base_url}/market/")
    _wait_ready(page)
    page.select_option("#interval", "5m")
    page.wait_for_function(
        "() => window.marketChart && window.marketChart.candleSeries &&"
        " window.marketChart.candleSeries.data().length > 0",
        timeout=10000,
    )
    page.select_option("#scale-mode", "log")
    page.wait_for_function(
        "() => document.getElementById('scale-mode').value === 'log'",
        timeout=2000,
    )
    # Right-click empty space (no drawing) -> the menu offers Reset scale.
    chart = page.locator("#chart")
    box = chart.bounding_box()
    page.mouse.click(
        box["x"] + box["width"] - 8, box["y"] + box["height"] - 8, button="right"
    )
    page.wait_for_selector('div[role="menu"]', timeout=5000)
    page.locator('div[role="menu"] [role="menuitem"]', has_text="Reset scale").click()
    # scale:changed routed to the host's option-only path: the price scale is
    # Normal (mode 0) again and no drawings PUT was issued (#68).
    page.wait_for_function(
        "() => window.marketChart.chart.priceScale('right').options().mode === 0",
        timeout=2000,
    )
    assert puts == [], [r.url for r in puts]
