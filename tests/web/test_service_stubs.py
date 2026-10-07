"""R7 contract: worker/scheduler boot as Redis-ping + idle stubs.

Mocks ``redis.Redis.ping`` so the stubs construct and run without a live
server; a real ``ping`` would need a broker the local suite does not have.
"""

from __future__ import annotations

import pytest
import redis


@pytest.fixture
def fake_redis(monkeypatch):
    """Redis that never connects: ping is a no-op returning True."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(redis.Redis, "ping", lambda self: True)


@pytest.mark.parametrize("module_name", ["worker", "scheduler"])
def test_stub_boots_and_idles(module_name, fake_redis):
    import importlib

    module = importlib.import_module(module_name)
    # One idle iteration then clean exit — proves boot + ping + loop guard.
    assert module.main(iterations=1) == 0
