"""Development settings: local-only defaults, DEBUG on, insecure key allowed."""

from __future__ import annotations

import os

from .base import *  # noqa: F403
from .base import env_bool

DEBUG = env_bool("DEBUG", True)

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key-not-for-production")

ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1"]  # noqa: F405
