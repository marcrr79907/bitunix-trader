"""BitUnix futures REST client.

The ONLY module that speaks HTTP to BitUnix. Everything else consumes these
functions. Read-only against the API: no order endpoints are called here.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import string
import time
from typing import Any

import requests

BASE_URL = "https://fapi.bitunix.com"
PUBLIC_PREFIX = "/api/v1/futures/market"
PRIVATE_PREFIX = "/api/v1/futures"

_ALNUM = string.ascii_letters + string.digits


class BitunixError(Exception):
    """Raised when HTTP status != 200 or the API returns code != 0."""

    def __init__(self, code: Any, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"bitunix error {code}: {msg}")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sign(
    secret: str,
    nonce: str,
    timestamp: str,
    api_key: str,
    query: str = "",
    body: str = "",
) -> str:
    """Double SHA256 signature.

    digest = SHA256(nonce + timestamp + api_key + query + body)
    sign   = SHA256(digest + secret)
    """
    digest = sha256_hex(nonce + timestamp + api_key + query + body)
    return sha256_hex(digest + secret)


def _random_nonce() -> str:
    return "".join(secrets.choice(_ALNUM) for _ in range(32))


def _canonical_query(params: dict[str, Any] | None) -> str:
    """queryParams sorted by key ascending, concatenated as k+v with no separators."""
    if not params:
        return ""
    return "".join(f"{k}{params[k]}" for k in sorted(params))


class BitunixClient:
    def __init__(
        self,
        api_key: str = "",
        secret: str = "",
        base_url: str = BASE_URL,
    ):
        self.api_key = api_key
        self.secret = secret
        self.base_url = base_url.rstrip("/")

    def _headers(self, query: str, body: str) -> dict[str, str]:
        nonce = _random_nonce()
        ts = str(int(time.time() * 1000))
        return {
            "api-key": self.api_key,
            "nonce": nonce,
            "timestamp": ts,
            "sign": sign(self.secret, nonce, ts, self.api_key, query, body),
            "Content-Type": "application/json",
        }

    def get(
        self, path: str, params: dict[str, Any] | None = None, private: bool = False
    ) -> Any:
        query = _canonical_query(params)
        headers = self._headers(query, "") if private else {}
        url = self.base_url + path
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        return self._unwrap(resp)

    def post(self, path: str, body: dict[str, Any], private: bool = True) -> Any:
        # Compact JSON with no spaces; the SAME string is signed and sent.
        raw = json.dumps(body, separators=(",", ":"))
        headers = self._headers("", raw) if private else {}
        resp = requests.post(
            self.base_url + path, data=raw, headers=headers, timeout=15
        )
        return self._unwrap(resp)

    @staticmethod
    def _unwrap(resp: requests.Response) -> Any:
        if resp.status_code != 200:
            raise BitunixError(resp.status_code, resp.text[:300])
        payload = resp.json()
        code = payload.get("code")
        if code != 0:
            raise BitunixError(code, payload.get("msg", ""))
        return payload.get("data")

    # --- public market endpoints ---

    def tickers(self, symbols: list[str] | None = None) -> list[dict]:
        params = {"symbols": ",".join(symbols)} if symbols else None
        return self.get(f"{PUBLIC_PREFIX}/tickers", params)

    def funding_rate_batch(self) -> list[dict]:
        # Endpoint ignores `symbols` and returns every pair; filter client-side.
        return self.get(f"{PUBLIC_PREFIX}/funding_rate/batch")

    def kline(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        rows = self.get(f"{PUBLIC_PREFIX}/kline", params)  # unsigned public GET
        return [
            {
                "time": int(r["time"]) // 1000,
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "quote_vol": float(r["quoteVol"]) if r.get("quoteVol") else None,
            }
            for r in (rows or [])
        ]

    # --- private account endpoints (read-only) ---

    def positions(self, symbol: str | None = None) -> list[dict]:
        params = {"symbol": symbol} if symbol else None
        return self.get(
            f"{PRIVATE_PREFIX}/position/get_pending_positions", params, private=True
        )

    def account(self, margin_coin: str = "USDT") -> list[dict]:
        return self.get(
            f"{PRIVATE_PREFIX}/account",
            {"marginCoin": margin_coin},
            private=True,
        )

    def history_trades(self, symbol: str | None = None, skip: int = 0) -> dict:
        params = {"skip": skip, "limit": 100}
        if symbol:
            params["symbol"] = symbol
        return self.get(
            f"{PRIVATE_PREFIX}/trade/get_history_trades", params, private=True
        )

    def history_orders(self, symbol: str | None = None, skip: int = 0) -> dict:
        params = {"skip": skip, "limit": 100}
        if symbol:
            params["symbol"] = symbol
        return self.get(
            f"{PRIVATE_PREFIX}/trade/get_history_orders", params, private=True
        )
