"""R14 isolation harness: two independent users for cross-tenant tests.

PR2 ships the harness only. No green isolation assertion yet — Phase 2 of the
product adds owned rows and the test that flips red -> green uses these fixtures.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def user_a(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="user_a@example.com", password="pw-a-12345"
    )


@pytest.fixture
def user_b(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="user_b@example.com", password="pw-b-12345"
    )
