"""Liveness probe: process is up. No DB/Redis dependency by design (D5).

A DB-coupled healthcheck turns a database blip into a container restart storm.
Readiness (with real dependencies) is added when the first dependency lands.
"""

from __future__ import annotations

from django.http import JsonResponse


def healthz(request):
    """Return a tiny 200 body with no secrets or connection strings."""
    return JsonResponse({"status": "ok"})
