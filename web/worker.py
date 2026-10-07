"""Worker service stub (R7).

Boots, pings Redis to prove ``REDIS_URL`` is wired, then idles. Phase 0 carries
no business logic — the real sync loop lands in a later phase.
"""

from __future__ import annotations

import logging
import os
import time

import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

IDLE_SECONDS = 30


def ping_redis() -> None:
    """Connect to Redis via ``REDIS_URL`` and ping. Raises if unreachable."""
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    redis.Redis.from_url(url).ping()


def idle_loop(iterations: int | None = None) -> int:
    """Ping Redis each pass, then idle.

    ``iterations`` caps the loop for tests; ``None`` runs until interrupted
    (the deployed behaviour). Returns 0 on clean exit.
    """
    count = 0
    while iterations is None or count < iterations:
        ping_redis()
        logger.info("worker up; redis reachable; idle (no business logic)")
        count += 1
        if iterations is None:
            time.sleep(IDLE_SECONDS)
    return 0


def main(iterations: int | None = None) -> int:
    return idle_loop(iterations)


if __name__ == "__main__":
    raise SystemExit(main())
