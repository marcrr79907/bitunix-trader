"""Configuration loaded from .env with in-code defaults.

No python-dotenv dependency: a ~15 line loader covers our needs. Secrets never
live in the repo; .env is gitignored.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(ROOT / "bitunix.db")

BASE_URL = "https://fapi.bitunix.com"

# Note: BitUnix lists PEPE as 1000PEPEUSDT (1000x contract), not PEPEUSDT.
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "1000PEPEUSDT"]

# Thresholds
FUNDING_EXTREME = 0.0005  # 0.05% per funding interval
MARGIN_WARN = 0.5  # 50% margin ratio
POLL_SECONDS = 30


def load_env(path: str | Path = ROOT / ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, # comments. Does not overwrite
    already-exported variables."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env()

API_KEY = os.environ.get("BITUNIX_API_KEY", "").strip()
API_SECRET = os.environ.get("BITUNIX_API_SECRET", "").strip()
PUBLIC_ONLY = not (API_KEY and API_SECRET)

SYMBOLS = [
    s.strip() for s in os.environ.get("BITUNIX_SYMBOLS", "").split(",") if s.strip()
] or DEFAULT_SYMBOLS

# F11: one cap shared by the watchlist API and the worker ingest set, so the two
# limits can never disagree.
MAX_WATCHLIST_SYMBOLS = 50

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
