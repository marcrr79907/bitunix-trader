"""chart-layout-templates model contract (F11-B, T1/T2).

The entity half of ``openspec/changes/f11-layout-templates``: the unique
constraint, the JSON round-trip and ``for_user`` scoping. The JSON API lives in
``test_market_templates.py``.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from trading.models import ChartTemplate


@pytest.fixture
def user_a(db):
    return get_user_model().objects.create_user(
        email="tpl-a@example.com", password="pw-123456"
    )


@pytest.fixture
def user_b(db):
    return get_user_model().objects.create_user(
        email="tpl-b@example.com", password="pw-123456"
    )


# --- T1: entity ---------------------------------------------------------------


def test_name_is_unique_per_user(user_a):
    ChartTemplate.objects.create(user=user_a, name="Scalping", indicators=[])

    with pytest.raises(IntegrityError):
        ChartTemplate.objects.create(user=user_a, name="Scalping", indicators=[])


def test_distinct_users_may_share_a_name(user_a, user_b):
    ChartTemplate.objects.create(user=user_a, name="Scalping", indicators=[])
    ChartTemplate.objects.create(user=user_b, name="Scalping", indicators=[])

    assert ChartTemplate.objects.count() == 2


def test_indicators_round_trip(user_a):
    payload = [
        {
            "token": "sma",
            "params": {"sma_len": 50},
            "style": {"color": "#ff0000", "lineWidth": 2},
        }
    ]
    ChartTemplate.objects.create(user=user_a, name="T", indicators=payload)

    assert ChartTemplate.objects.get(name="T").indicators == payload


def test_for_user_scopes_templates(user_a, user_b):
    ChartTemplate.objects.create(user=user_a, name="A", indicators=[])
    ChartTemplate.objects.create(user=user_b, name="B", indicators=[])

    assert [t.name for t in ChartTemplate.for_user(user_a)] == ["A"]
