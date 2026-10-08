"""Answer the liveness probe before host validation; add a minimal CSP.

Railway's internal healthcheck connects to the container's private IP
(100.64.0.0/10), so the request Host is a bare IP that ALLOWED_HOSTS cannot
express, and CommonMiddleware rejects it with HTTP 400.

This middleware sits first in the stack and short-circuits only the health path,
before CommonMiddleware can validate the host. Every real request keeps strict
host validation (where Host feeds redirects and password-reset links).

The same module hosts the CSP header middleware (last in the stack): Django has
no CSP setting and django-csp is a new runtime dependency for one header.
``/admin/*`` is exempt — Django admin uses inline handlers and would break
under a strict ``script-src``.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from config.health import healthz

HEALTH_PATH = "/healthz"

CSP_POLICY = (
    "default-src 'self'; script-src 'self' https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com; "
    "connect-src 'self' wss://fapi.bitunix.com; img-src 'self' data:"
)
CSP_EXEMPT = ("/admin/",)


class HealthProbeHostMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == HEALTH_PATH:
            return healthz(request)
        return self.get_response(request)


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if not request.path.startswith(CSP_EXEMPT):
            response.headers.setdefault("Content-Security-Policy", CSP_POLICY)
        return response
