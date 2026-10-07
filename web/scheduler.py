"""Scheduler service stub (R7).

Same boot contract as the worker: ping Redis, then idle. Shares the idle loop
so the two stubs stay identical at the seam; Phase 0 schedules nothing.
"""

from __future__ import annotations

import logging

from worker import idle_loop

logger = logging.getLogger(__name__)


def main(iterations: int | None = None) -> int:
    logger.info("scheduler up; redis reachable; idle (no business logic)")
    return idle_loop(iterations)


if __name__ == "__main__":
    raise SystemExit(main())
