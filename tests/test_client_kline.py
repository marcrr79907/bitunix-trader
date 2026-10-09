"""R1 contract: read-only kline client method.

``kline()`` is a PUBLIC unsigned GET against ``/api/v1/futures/market/kline``:
no signing headers hit the wire. Mapping happens once at the seam — ``time``
ms → unix-seconds int, prices → float. Empty upstream returns ``[]``; HTTP or
API failure surfaces as ``BitunixError``. ``requests.get`` is monkeypatched;
no Django.
"""

from __future__ import annotations

import pytest

from src.client import PUBLIC_PREFIX, BitunixClient, BitunixError

KLINE_PATH = f"{PUBLIC_PREFIX}/kline"

ROW = {
    "time": "1700000000000",
    "open": "50000.5",
    "high": "51000",
    "low": "49000",
    "close": "50500",
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def _capture_get(monkeypatch, response):
    """Replace requests.get; return the captured (url, kwargs) of the call."""
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return response

    monkeypatch.setattr("src.client.requests.get", fake_get)
    return captured


def test_kline_hits_public_path_unsigned(monkeypatch):
    captured = _capture_get(
        monkeypatch, FakeResponse(payload={"code": 0, "data": [ROW], "msg": "Success"})
    )

    BitunixClient().kline("BTCUSDT", "1m", 100)

    assert captured["url"].endswith(KLINE_PATH)
    assert captured["kwargs"]["params"] == {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "limit": 100,
    }
    # Public endpoint: no signing headers on the wire.
    assert captured["kwargs"]["headers"] == {}


def test_kline_defaults_match_spec(monkeypatch):
    captured = _capture_get(
        monkeypatch, FakeResponse(payload={"code": 0, "data": [ROW], "msg": "Success"})
    )

    BitunixClient().kline("BTCUSDT")

    assert captured["kwargs"]["params"] == {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "limit": 100,
    }


def test_kline_maps_ms_to_unix_seconds_and_floats(monkeypatch):
    _capture_get(
        monkeypatch, FakeResponse(payload={"code": 0, "data": [ROW], "msg": "Success"})
    )

    candles = BitunixClient().kline("BTCUSDT", "1m", 100)

    assert candles == [
        {
            "time": 1700000000,
            "open": 50000.5,
            "high": 51000.0,
            "low": 49000.0,
            "close": 50500.0,
        }
    ]
    assert isinstance(candles[0]["time"], int)


def test_kline_api_code_ne_zero_raises(monkeypatch):
    _capture_get(
        monkeypatch,
        FakeResponse(payload={"code": 70014, "msg": "symbol not exist"}, text=""),
    )

    with pytest.raises(BitunixError):
        BitunixClient().kline("NOSUCHUSDT")


def test_kline_http_ne_200_raises(monkeypatch):
    _capture_get(monkeypatch, FakeResponse(status_code=503, payload=None, text="boom"))

    with pytest.raises(BitunixError):
        BitunixClient().kline("BTCUSDT")


def test_kline_empty_data_returns_empty_list(monkeypatch):
    _capture_get(
        monkeypatch, FakeResponse(payload={"code": 0, "data": [], "msg": "Success"})
    )

    assert BitunixClient().kline("BTCUSDT") == []


def test_kline_null_data_returns_empty_list(monkeypatch):
    # Some public endpoints return data: null instead of [].
    _capture_get(
        monkeypatch, FakeResponse(payload={"code": 0, "data": None, "msg": "Success"})
    )

    assert BitunixClient().kline("BTCUSDT") == []


if __name__ == "__main__":
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tests.test_client_kline import (  # noqa: F401
        test_kline_api_code_ne_zero_raises,
        test_kline_defaults_match_spec,
        test_kline_empty_data_returns_empty_list,
        test_kline_hits_public_path_unsigned,
        test_kline_http_ne_200_raises,
        test_kline_maps_ms_to_unix_seconds_and_floats,
        test_kline_null_data_returns_empty_list,
    )

    test_kline_hits_public_path_unsigned(None)
    test_kline_defaults_match_spec(None)
    test_kline_maps_ms_to_unix_seconds_and_floats(None)
    test_kline_api_code_ne_zero_raises(None)
    test_kline_http_ne_200_raises(None)
    test_kline_empty_data_returns_empty_list(None)
    test_kline_null_data_returns_empty_list(None)
    print("ok: kline client contract holds")
