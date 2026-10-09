#!/usr/bin/env python
"""Django management entry point. Defaults to dev settings."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_project_paths() -> None:
    """Make ``web/`` and the repo root importable regardless of invocation.

    Django's startup imports the root URLconf, which now reaches the
    framework-free core (``src/``) through ``market.quotes``. ``manage.py`` must
    not depend on the caller's ``PYTHONPATH`` (CI runs it with none; Docker sets
    one). Adding ``web/`` and the repo root here keeps ``manage.py check`` /
    ``makemigrations`` working everywhere.
    """
    web_dir = Path(__file__).resolve().parent
    repo_root = web_dir.parent
    for path in (repo_root, web_dir):
        entry = str(path)
        if entry not in sys.path:
            sys.path.insert(0, entry)


def main() -> None:
    _ensure_project_paths()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
