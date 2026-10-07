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


@pytest.mark.django_db
def test_healthz_ignores_invalid_host(client, settings):
    """Railway's internal probe arrives with a private-IP Host; /healthz must
    answer 200 regardless, while real routes keep strict host validation."""
    settings.ALLOWED_HOSTS = ["example.com"]
    ok = client.get("/healthz", HTTP_HOST="100.64.0.1")
    assert ok.status_code == 200
    # A non-health route with the same bogus host is still rejected.
    assert client.get("/login/", HTTP_HOST="100.64.0.1").status_code == 400
