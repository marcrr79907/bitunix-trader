"""chart-layout-templates JSON API contract (F11-B, T3).

CRUD over ``ChartTemplate``, scoped by ``for_user`` (R14). The payload is the
exact shape ``ChartLayout`` stores, so ``parse_layout_indicators`` is the single
validation point.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from trading.models import ChartTemplate

TEMPLATES_URL = "/market/api/templates"

VALID = [{"token": "sma", "params": {"sma_len": 50}}]


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


@pytest.fixture
def client_a(user_a):
    client = Client()
    client.force_login(user_a)
    return client


@pytest.fixture
def client_b(user_b):
    client = Client()
    client.force_login(user_b)
    return client


def _post(client, payload):
    return client.post(
        TEMPLATES_URL, data=json.dumps(payload), content_type="application/json"
    )


# --- T3: GET ------------------------------------------------------------------


def test_get_lists_only_the_callers_templates_ordered(client_a, user_a, user_b):
    ChartTemplate.objects.create(user=user_a, name="Zeta", indicators=[])
    ChartTemplate.objects.create(user=user_a, name="Alpha", indicators=[])
    ChartTemplate.objects.create(user=user_b, name="Other", indicators=[])

    body = client_a.get(TEMPLATES_URL).json()

    assert [t["name"] for t in body["templates"]] == ["Alpha", "Zeta"]


def test_get_empty_is_an_empty_list_not_404(client_a):
    response = client_a.get(TEMPLATES_URL)

    assert response.status_code == 200
    assert response.json() == {"templates": []}


def test_get_row_shape(client_a, user_a):
    row = ChartTemplate.objects.create(user=user_a, name="T", indicators=VALID)

    body = client_a.get(TEMPLATES_URL).json()["templates"][0]

    assert body == {"id": row.id, "name": "T", "indicators": VALID}


def test_anonymous_is_redirected(client, db):
    response = client.get(TEMPLATES_URL)

    assert response.status_code == 302
    assert response.url.startswith("/login/")


# --- T3: POST -----------------------------------------------------------------


def test_post_creates_a_template(client_a, user_a):
    response = _post(client_a, {"name": "Scalping", "indicators": VALID})

    assert response.status_code == 201
    assert ChartTemplate.for_user(user_a).get(name="Scalping").indicators == VALID


def test_post_trims_the_name(client_a, user_a):
    _post(client_a, {"name": "  Scalping  ", "indicators": VALID})

    assert ChartTemplate.for_user(user_a).get().name == "Scalping"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "T", "indicators": [{"token": "notreal"}]},
        {"name": "T", "indicators": [{"token": "sma", "style": {"lineWidth": 9}}]},
        {"name": "T", "indicators": [{"token": "sma", "visible": "yes"}]},
        {"name": "T", "indicators": "notalist"},
    ],
)
def test_post_invalid_indicators_write_nothing(client_a, payload):
    response = _post(client_a, payload)

    assert response.status_code == 400
    assert ChartTemplate.objects.count() == 0


@pytest.mark.parametrize("name", ["", "   ", "x" * 41, 123])
def test_post_invalid_name_is_400(client_a, name):
    response = _post(client_a, {"name": name, "indicators": VALID})

    assert response.status_code == 400
    assert ChartTemplate.objects.count() == 0


def test_post_duplicate_name_is_400(client_a, user_a):
    _post(client_a, {"name": "Scalping", "indicators": VALID})
    response = _post(client_a, {"name": "Scalping", "indicators": []})

    assert response.status_code == 400
    assert ChartTemplate.for_user(user_a).count() == 1


def test_post_rejects_invalid_json(client_a):
    response = client_a.post(
        TEMPLATES_URL, data="{oops", content_type="application/json"
    )

    assert response.status_code == 400


def test_post_rejects_a_non_object_body(client_a):
    response = client_a.post(
        TEMPLATES_URL, data="[1,2]", content_type="application/json"
    )

    assert response.status_code == 400


def test_post_requires_csrf(user_a):
    enforcing = Client(enforce_csrf_checks=True)
    enforcing.force_login(user_a)

    response = enforcing.post(
        TEMPLATES_URL,
        data=json.dumps({"name": "T", "indicators": VALID}),
        content_type="application/json",
    )

    assert response.status_code == 403


def test_owner_is_never_taken_from_the_body(client_a, user_a, user_b):
    _post(client_a, {"name": "T", "indicators": VALID, "user": user_b.pk})

    assert ChartTemplate.objects.get(name="T").user_id == user_a.pk


# --- T3: DELETE ---------------------------------------------------------------


def test_delete_removes_the_row(client_a, user_a):
    row = ChartTemplate.objects.create(user=user_a, name="T", indicators=[])

    response = client_a.delete(f"{TEMPLATES_URL}/{row.id}")

    assert response.status_code == 204
    assert not ChartTemplate.for_user(user_a).exists()


def test_delete_is_404_for_a_foreign_id(client_a, user_a, user_b):
    row = ChartTemplate.objects.create(user=user_b, name="B", indicators=[])

    response = client_a.delete(f"{TEMPLATES_URL}/{row.id}")

    assert response.status_code == 404
    assert ChartTemplate.for_user(user_b).exists()


def test_delete_is_404_for_an_absent_id(client_a):
    response = client_a.delete(f"{TEMPLATES_URL}/999999")

    assert response.status_code == 404
