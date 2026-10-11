"""R2/R3: per-user `/journal/` — auth-gated, metrics reuse, R14 isolated."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from trading.models import Trade

User = get_user_model()
URL = "/journal/"


def _trade(user, tid, symbol, pnl, fee):
    return Trade.objects.create(
        user=user, trade_id=tid, symbol=symbol, realized_pnl=pnl, fee=fee
    )


@pytest.mark.django_db
def test_journal_anonymous_redirects(client):
    response = client.get(URL)
    assert response.status_code == 302
    assert response.url.startswith("/login/")


@pytest.mark.django_db
def test_journal_empty_state(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    response = client.get(URL)
    assert response.status_code == 200
    assert b"No trades yet" in response.content


@pytest.mark.django_db
def test_journal_known_metrics(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    # nets = [10, -5, 5] -> win_rate 66.67, net 10.0, expectancy 3.333, PF 3.0
    _trade(user, "T1", "BTCUSDT", 10.0, 0.0)
    _trade(user, "T2", "BTCUSDT", -5.0, 0.0)
    _trade(user, "T3", "ETHUSDT", 5.0, 0.0)
    response = client.get(URL)
    body = response.content.decode()
    assert "66.67" in body  # win rate
    assert "10.00" in body  # net pnl
    assert "3.3333" in body  # expectancy
    assert "3.00" in body  # profit factor


@pytest.mark.django_db
def test_journal_isolation_a_not_b(client):
    a = User.objects.create_user(email="a@example.com", password="pw-123456")
    b = User.objects.create_user(email="b@example.com", password="pw-123456")
    _trade(a, "TA", "BTCUSDT", 10.0, 0.0)
    client.force_login(b)
    response = client.get(URL)
    assert b"BTCUSDT" not in response.content
    assert b"No trades yet" in response.content
