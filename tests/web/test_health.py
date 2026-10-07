"""R8 contract: /healthz is an anonymous liveness probe that leaks nothing."""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_healthz_returns_200_anonymously(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_healthz_body_has_no_secrets(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.content.decode().lower()
    for leak in ("secret", "password", "postgres", "redis://", "database_url"):
        assert leak not in body
