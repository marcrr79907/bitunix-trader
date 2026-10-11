"""R1/R3: per-user `/positions/` — auth-gated, latest-per-symbol, R14 isolated."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from trading.models import PositionSnapshot, TickerSnapshot

User = get_user_model()
URL = "/positions/"


def _ts(n: int) -> datetime:
    return datetime(2025, 1, 1, 0, n, tzinfo=UTC)


@pytest.mark.django_db
def test_positions_anonymous_redirects(client):
    response = client.get(URL)
    assert response.status_code == 302
    assert response.url.startswith("/login/")


@pytest.mark.django_db
def test_positions_empty_state(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    response = client.get(URL)
    assert response.status_code == 200
    assert b"No positions yet" in response.content


@pytest.mark.django_db
def test_positions_renders_latest_per_symbol(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    PositionSnapshot.objects.create(user=user, symbol="BTCUSDT", side="LONG", ts=_ts(1))
    PositionSnapshot.objects.create(user=user, symbol="BTCUSDT", side="LONG", ts=_ts(2))
    client.force_login(user)
    response = client.get(URL)
    assert response.status_code == 200
    assert response.content.count(b"BTCUSDT") == 1  # only max-ts row


@pytest.mark.django_db
def test_positions_distance_and_margin_reuse(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    PositionSnapshot.objects.create(
        user=user,
        symbol="BTCUSDT",
        side="LONG",
        liq_price=45000.0,
        margin_rate=0.9,
        ts=_ts(1),
    )
    TickerSnapshot.objects.create(symbol="BTCUSDT", ts=_ts(1), last_price=50000.0)
    response = client.get(URL)
    body = response.content.decode()
    assert "10.0%" in body  # |45000-50000|/50000*100
    assert "danger" in body  # margin rate 0.9 >= MARGIN_WARN


@pytest.mark.django_db
def test_positions_missing_mark_is_dash(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    PositionSnapshot.objects.create(
        user=user, symbol="NOMARK", side="LONG", liq_price=10.0, ts=_ts(1)
    )
    response = client.get(URL)
    assert response.status_code == 200  # no error without a TickerSnapshot


@pytest.mark.django_db
def test_positions_isolation_a_not_b(client):
    a = User.objects.create_user(email="a@example.com", password="pw-123456")
    b = User.objects.create_user(email="b@example.com", password="pw-123456")
    PositionSnapshot.objects.create(user=a, symbol="BTCUSDT", ts=_ts(1))
    client.force_login(b)
    response = client.get(URL)
    assert b"BTCUSDT" not in response.content
    assert b"No positions yet" in response.content
