"""R14 contract: user-owned rows are scoped to their owner, fail-closed.

Exercises the ownership deep module (`UserOwnedModel.for_user`) through both
adapters — `ExchangeCredential` and `Watchlist` — so the seam is proven to
generalise past the secret table.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from trading.models import ExchangeCredential, Watchlist


@pytest.mark.django_db
def test_for_user_returns_only_the_owner_rows(user_a, user_b):
    mine = ExchangeCredential.objects.create(
        user=user_a, api_key_encrypted="k", api_secret_encrypted="s"
    )
    other = Watchlist.objects.create(user=user_a, symbol="BTCUSDT")

    assert list(ExchangeCredential.for_user(user_a)) == [mine]
    assert list(Watchlist.for_user(user_a)) == [other]
    assert list(ExchangeCredential.for_user(user_b)) == []
    assert list(Watchlist.for_user(user_b)) == []


@pytest.mark.django_db
def test_for_user_empty_owner_is_not_an_error(user_a):
    assert list(ExchangeCredential.for_user(user_a)) == []
    assert list(Watchlist.for_user(user_a)) == []


@pytest.mark.django_db
def test_cross_user_get_denied(user_a, user_b):
    cred = ExchangeCredential.objects.create(
        user=user_a, api_key_encrypted="k", api_secret_encrypted="s"
    )
    row = Watchlist.objects.create(user=user_a, symbol="ETHUSDT")

    with pytest.raises(ExchangeCredential.DoesNotExist):
        ExchangeCredential.for_user(user_b).get(pk=cred.pk)
    with pytest.raises(Watchlist.DoesNotExist):
        Watchlist.for_user(user_b).get(pk=row.pk)


@pytest.mark.django_db
def test_duplicate_user_symbol_rejected(user_a):
    Watchlist.objects.create(user=user_a, symbol="BTCUSDT")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Watchlist.objects.create(user=user_a, symbol="BTCUSDT")


@pytest.mark.django_db
def test_same_symbol_allowed_across_users(user_a, user_b):
    Watchlist.objects.create(user=user_a, symbol="BTCUSDT")
    Watchlist.objects.create(user=user_b, symbol="BTCUSDT")

    assert Watchlist.for_user(user_a).count() == 1
    assert Watchlist.for_user(user_b).count() == 1
