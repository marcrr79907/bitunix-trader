"""R1/R14 contract: the three private owned models are per-user and idempotent.

``PositionSnapshot``/``AccountSnapshot``/``Trade`` inherit ``UserOwnedModel`` (FK
CASCADE, ``for_user``) and carry a ``(user, …)`` UniqueConstraint so a re-sync
cannot duplicate an existing row. Ownership is proven A≠B, trade ids are per-user,
and no row can exist without an owner.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.db import IntegrityError, transaction
from trading.models import AccountSnapshot, PositionSnapshot, Trade, UserOwnedModel

TS = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

PRIVATE_MODELS = [PositionSnapshot, AccountSnapshot, Trade]


@pytest.mark.parametrize("model", PRIVATE_MODELS)
def test_private_models_inherit_user_owned(model):
    assert issubclass(model, UserOwnedModel)
    field = model._meta.get_field("user")
    assert field.remote_field.on_delete.__name__ == "CASCADE"
    assert field.null is False


@pytest.mark.django_db
def test_position_for_user_scopes_to_owner(user_a, user_b):
    PositionSnapshot.objects.create(user=user_a, symbol="BTCUSDT", ts=TS)
    assert PositionSnapshot.for_user(user_a).count() == 1
    assert PositionSnapshot.for_user(user_b).count() == 0


@pytest.mark.django_db
def test_account_for_user_scopes_to_owner(user_a, user_b):
    AccountSnapshot.objects.create(user=user_a, ts=TS)
    assert AccountSnapshot.for_user(user_a).count() == 1
    assert AccountSnapshot.for_user(user_b).count() == 0


@pytest.mark.django_db
def test_trade_for_user_scopes_to_owner(user_a, user_b):
    Trade.objects.create(user=user_a, trade_id="T1", symbol="BTCUSDT", ctime=1)
    assert Trade.for_user(user_a).count() == 1
    assert Trade.for_user(user_b).count() == 0


@pytest.mark.django_db
def test_duplicate_position_rejected(user_a):
    PositionSnapshot.objects.create(user=user_a, symbol="BTCUSDT", ts=TS)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PositionSnapshot.objects.create(user=user_a, symbol="BTCUSDT", ts=TS)


@pytest.mark.django_db
def test_duplicate_account_rejected(user_a):
    AccountSnapshot.objects.create(user=user_a, ts=TS)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AccountSnapshot.objects.create(user=user_a, ts=TS)


@pytest.mark.django_db
def test_duplicate_trade_id_rejected(user_a):
    Trade.objects.create(user=user_a, trade_id="T1", symbol="BTCUSDT", ctime=1)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Trade.objects.create(user=user_a, trade_id="T1", symbol="BTCUSDT", ctime=1)


@pytest.mark.django_db
def test_trade_id_allowed_across_users(user_a, user_b):
    # Uniqueness is per user: A and B may both log exchange trade id T1.
    Trade.objects.create(user=user_a, trade_id="T1", symbol="BTCUSDT", ctime=1)
    Trade.objects.create(user=user_b, trade_id="T1", symbol="BTCUSDT", ctime=1)
    assert Trade.for_user(user_a).count() == 1
    assert Trade.for_user(user_b).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "build",
    [
        lambda: PositionSnapshot.objects.create(symbol="BTCUSDT", ts=TS),
        lambda: AccountSnapshot.objects.create(ts=TS),
        lambda: Trade.objects.create(trade_id="T1", symbol="BTCUSDT", ctime=1),
    ],
)
def test_owner_is_required(build):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            build()
