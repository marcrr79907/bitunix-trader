"""AS1-AS6 contract: the server-rendered, read-only ``/analytics/`` screen.

``/analytics/`` is GET-only, login-gated and server-rendered. It reads only the
caller's own ``Trade.for_user`` rows (R14), delegates every metric to the pure
``src/analytics.py`` (single source — no math here), extracts historical SMC
setups through the frozen ``get_smc_payload`` seam, and renders inline SVG with
no JS and no new dependency. Another user's trades never leak, and an upstream
failure degrades to no signals rather than a 500.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest
from django.contrib.auth import get_user_model
from trading.models import Trade

User = get_user_model()
URL = "/analytics/"

# Trade A1: 1_700_000_000_000 ms -> hour 22, seconds 1_700_000_000.
CTIME_A1 = 1_700_000_000_000
CTIME_A2 = 1_700_003_600_000  # +1h -> hour 23


def _trade(user, tid, symbol, pnl, ctime, fee=0.0, side="BUY", qty=1.0):
    return Trade.objects.create(
        user=user,
        trade_id=tid,
        symbol=symbol,
        side=side,
        qty=qty,
        realized_pnl=pnl,
        fee=fee,
        ctime=ctime,
    )


def _signal(symbol="BTCUSDT", time=CTIME_A1 // 1000, direction="long", score=4):
    return {
        "symbol": symbol,
        "time": time,
        "direction": direction,
        "entry": 100.0,
        "stop": 95.0,
        "score": score,
    }


class SignalRecorder:
    """Stubs ``trading.views.extract_signals``; records calls, returns signals."""

    def __init__(self, by_symbol=None):
        self._by_symbol = by_symbol or {}
        self.calls = []

    def __call__(self, symbol, bars):
        self.calls.append((symbol, list(bars)))
        return self._by_symbol.get(symbol, [])


@pytest.fixture
def login_a(client, user_a):
    client.force_login(user_a)
    return client


# --- AS1: route and auth -----------------------------------------------------


def test_analytics_anonymous_redirects_to_login(client):
    response = client.get(URL)
    assert response.status_code == 302
    assert response.url.startswith("/login/")


@pytest.mark.django_db
def test_analytics_authenticated_renders_html(login_a, monkeypatch):
    from trading import views

    monkeypatch.setattr(views, "extract_signals", SignalRecorder({}))

    response = login_a.get(URL)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    body = response.content.decode()
    assert "<html" in body
    assert "bitunix-trader" in body  # extends the base shell
    assert 'aria-label="Primary"' in body


# --- AS2: per-user scoping --------------------------------------------------


@pytest.mark.django_db
def test_analytics_no_trades_empty_state(login_a, monkeypatch):
    from trading import views

    recorder = SignalRecorder({})
    monkeypatch.setattr(views, "extract_signals", recorder)

    response = login_a.get(URL)

    assert response.status_code == 200
    assert b"No trades yet" in response.content
    assert recorder.calls == []  # no symbols -> no upstream work


@pytest.mark.django_db
def test_analytics_isolation_a_not_b(login_a, user_a, user_b, monkeypatch):
    from trading import views

    _trade(user_a, "TA", "BTCUSDT", 10.0, CTIME_A1)
    monkeypatch.setattr(views, "extract_signals", SignalRecorder({"BTCUSDT": []}))

    login_a.force_login(user_b)
    response = login_a.get(URL)

    assert response.status_code == 200
    assert b"BTCUSDT" not in response.content
    assert b"No trades yet" in response.content


# --- AS3: breakdowns and calibration content --------------------------------


@pytest.mark.django_db
def test_analytics_renders_grouped_summaries(login_a, user_a, monkeypatch):
    from trading import views

    _trade(user_a, "TA1", "BTCUSDT", 10.0, CTIME_A1)
    _trade(user_a, "TA2", "ETHUSDT", -5.0, CTIME_A2)
    monkeypatch.setattr(
        views, "extract_signals", SignalRecorder({"BTCUSDT": [_signal()]})
    )

    body = login_a.get(URL).content.decode()

    # hour / symbol buckets render with their keys, and the matched setup kind
    # comes from the calibration block (single source — no view-side join).
    assert "BTCUSDT" in body
    assert "ETHUSDT" in body
    assert "long:score4" in body  # matched setup kind
    assert "unmatched" in body  # the ETHUSDT trade has no signal
    assert "10.00" in body  # net PnL from the frozen summarize
    assert "-5.00" in body


@pytest.mark.django_db
def test_analytics_calibration_none_r_renders_dash(login_a, user_a, monkeypatch):
    from trading import views

    _trade(user_a, "TA1", "BTCUSDT", 10.0, CTIME_A1)
    # entry == stop -> risk 0 -> r_by_setup value None -> must render "—".
    zero_risk = {**_signal(), "entry": 100.0, "stop": 100.0}
    monkeypatch.setattr(
        views, "extract_signals", SignalRecorder({"BTCUSDT": [zero_risk]})
    )

    body = login_a.get(URL).content.decode()

    assert "long:score4" in body
    assert "—" in body  # None R never divides by zero


@pytest.mark.django_db
def test_analytics_view_delegates_math(login_a, user_a, monkeypatch):
    from trading import views

    _trade(user_a, "TA1", "BTCUSDT", 10.0, CTIME_A1)
    monkeypatch.setattr(
        views, "extract_signals", SignalRecorder({"BTCUSDT": [_signal()]})
    )

    called = {"group": []}
    real_group = views.group_metrics
    real_calibrate = views.calibrate

    def spy_group(rows, dimension):
        called["group"].append(dimension)
        return real_group(rows, dimension)

    def spy_calibrate(signals, trades, *, window_seconds):
        called["calibrate"] = window_seconds
        return real_calibrate(signals, trades, window_seconds=window_seconds)

    monkeypatch.setattr(views, "group_metrics", spy_group)
    monkeypatch.setattr(views, "calibrate", spy_calibrate)

    response = login_a.get(URL)

    assert response.status_code == 200
    # hour + symbol group through the pure helper; the setup breakdown is the
    # single-sourced calibrate join (the join is never reimplemented here).
    assert set(called["group"]) == {"hour", "symbol"}
    assert called["calibrate"] == 3600


# --- AS4: inline SVG, no JS -------------------------------------------------


@pytest.mark.django_db
def test_analytics_renders_inline_svg_no_script(login_a, user_a, monkeypatch):
    from trading import views

    _trade(user_a, "TA1", "BTCUSDT", 10.0, CTIME_A1)
    monkeypatch.setattr(
        views, "extract_signals", SignalRecorder({"BTCUSDT": [_signal()]})
    )

    body = login_a.get(URL).content.decode()

    svgs = re.findall(r"<svg.*?</svg>", body, re.S)
    assert len(svgs) >= 2  # equity + bars
    for svg in svgs:
        ET.fromstring(svg)  # well-formed markup
    assert "<polyline" in body  # the equity curve actually drew
    assert not re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", body)
    assert not re.search(r"\son[a-z]+\s*=", body), "inline handler found"


@pytest.mark.django_db
def test_analytics_svg_labels_are_escaped(login_a, user_a, monkeypatch):
    from trading import views

    _trade(user_a, "TA1", "A<B", 10.0, CTIME_A1)
    monkeypatch.setattr(views, "extract_signals", SignalRecorder({"A<B": []}))

    body = login_a.get(URL).content.decode()

    assert "A&lt;B" in body  # escaped label in the SVG text node
    assert "A<B" not in body  # raw symbol never breaks out
    for svg in re.findall(r"<svg.*?</svg>", body, re.S):
        ET.fromstring(svg)  # still parses with the escaped label


@pytest.mark.django_db
def test_analytics_csp_unchanged(login_a, user_a, monkeypatch):
    """AS4: inline SVG is HTML, not script — the CSP header is untouched."""
    from config.middleware import CSP_POLICY
    from trading import views

    monkeypatch.setattr(views, "extract_signals", SignalRecorder({}))

    response = login_a.get(URL)

    assert response.headers["Content-Security-Policy"] == CSP_POLICY


@pytest.mark.django_db
def test_analytics_svg_carries_accessible_labels(login_a, user_a, monkeypatch):
    """AS4: every inline SVG exposes role="img" plus an aria-label/title."""
    from trading import views

    _trade(user_a, "TA1", "BTCUSDT", 10.0, CTIME_A1)
    monkeypatch.setattr(
        views, "extract_signals", SignalRecorder({"BTCUSDT": [_signal()]})
    )

    body = login_a.get(URL).content.decode()

    svgs = re.findall(r"<svg\b.*?</svg>", body, re.S)
    assert svgs
    for svg in svgs:
        root = ET.fromstring(svg)
        assert root.get("role") == "img"
        has_label = root.get("aria-label") or root.find(
            "{http://www.w3.org/2000/svg}title"
        )
        assert has_label, svg


@pytest.mark.django_db
def test_analytics_non_color_state_cue(login_a, user_a, monkeypatch):
    """AS4/theme: a sign marks a winning bucket — state is not colour-only."""
    from trading import views

    _trade(user_a, "TA1", "BTCUSDT", 10.0, CTIME_A1)  # winner
    _trade(user_a, "TA2", "ETHUSDT", -5.0, CTIME_A2)  # loser
    monkeypatch.setattr(
        views,
        "extract_signals",
        SignalRecorder({"BTCUSDT": [], "ETHUSDT": []}),
    )

    body = login_a.get(URL).content.decode()

    # Positive net PnL carries an explicit "+" cue alongside the colour class.
    assert "+10.00" in body
    assert "-5.00" in body  # the loss keeps its sign (also a non-colour cue)
    assert 'class="num pos"' in body or "pos" in body


# --- AS5: historical signal seam --------------------------------------------


class SmcRecorder:
    """Stubs ``trading.analytics.get_smc_payload``; records calls."""

    def __init__(self, setups=None, error=None):
        self._setups = setups or []
        self._error = error
        self.calls = []

    def __call__(self, client, symbol, interval, limit, *, before=None):
        self.calls.append((symbol, interval, limit, before))
        if self._error is not None:
            raise self._error
        return {"symbol": symbol, "interval": interval, "setups": list(self._setups)}


def test_extract_signals_one_call_per_distinct_bar(monkeypatch):
    from trading import analytics

    recorder = SmcRecorder()
    monkeypatch.setattr(analytics, "get_smc_payload", recorder)

    ctimes = [CTIME_A1, CTIME_A1, CTIME_A2]
    analytics.extract_signals("BTCUSDT", ctimes)

    # Two distinct hourly bars -> two chain passes, not three, oldest-first,
    # each bounded by the END of its bar (exclusive upper bound in seconds).
    assert [(c[0], c[1]) for c in recorder.calls] == [
        ("BTCUSDT", "1h"),
        ("BTCUSDT", "1h"),
    ]
    assert [c[3] for c in recorder.calls] == [
        (CTIME_A1 // 3_600_000 + 1) * 3600,
        (CTIME_A2 // 3_600_000 + 1) * 3600,
    ]


def test_extract_signals_shapes_setups_as_signals(monkeypatch):
    from trading import analytics

    setup = {
        "direction": "long",
        "time": 1_699_999_999,
        "entry": 101.0,
        "stop": 99.0,
        "take_profit": 105.0,
        "rr": 2.0,
        "score": 4,
    }
    monkeypatch.setattr(analytics, "get_smc_payload", SmcRecorder([setup]))

    signals = analytics.extract_signals("BTCUSDT", [CTIME_A1])

    assert signals == [
        {
            "symbol": "BTCUSDT",
            "time": 1_699_999_999,
            "direction": "long",
            "entry": 101.0,
            "stop": 99.0,
            "score": 4,
        }
    ]


def test_extract_signals_swallows_upstream_error(monkeypatch):
    import requests
    from trading import analytics

    from src.client import BitunixError

    monkeypatch.setattr(
        analytics, "get_smc_payload", SmcRecorder(error=BitunixError(70014, "nope"))
    )
    assert analytics.extract_signals("BTCUSDT", [CTIME_A1]) == []

    monkeypatch.setattr(
        analytics,
        "get_smc_payload",
        SmcRecorder(error=requests.ConnectionError("boom")),
    )
    assert analytics.extract_signals("BTCUSDT", [CTIME_A1]) == []
