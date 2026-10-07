"""Production settings: fail closed when SECRET_KEY is absent."""

from __future__ import annotations

import os

from .base import *  # noqa: F403

# Dict-index on purpose: a missing SECRET_KEY raises KeyError at boot instead of
# silently falling back to a shared insecure secret.
SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = False
