"""Answer the liveness probe before host validation.

Railway's internal healthcheck connects to the container's private IP
(100.64.0.0/10), so the request Host is a bare IP that ALLOWED_HOSTS cannot
express, and CommonMiddleware rejects it with HTTP 400.

This middleware sits first in the stack and short-circuits only the health path,
before CommonMiddleware can validate the host. Every real request keeps strict
host validation (where Host feeds redirects and password-reset links).
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from config.health import healthz

HEALTH_PATH = "/healthz"


class HealthProbeHostMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == HEALTH_PATH:
            return healthz(request)
        return self.get_response(request)
