"""R14 contract: user-owned rows are scoped to their owner, fail-closed.

Exercises the ownership deep module (`UserOwnedModel.for_user`) through both
adapters — `ExchangeCredential` and `Watchlist` — so the seam is proven to
generalise past the secret table.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.db import IntegrityError, transaction
from trading.models import (
    AccountSnapshot,
    ExchangeCredential,
    PositionSnapshot,
    Trade,
    Watchlist,
)

TS = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


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
def test_cross_user_get_denied_for_private_models(user_a, user_b):
    # R14.2: the 3 private owned models fail closed exactly like the originals.
    pos = PositionSnapshot.objects.create(user=user_a, symbol="BTCUSDT", ts=TS)
    acct = AccountSnapshot.objects.create(user=user_a, ts=TS)
    trade = Trade.objects.create(user=user_a, trade_id="T1", symbol="BTCUSDT", ctime=1)

    with pytest.raises(PositionSnapshot.DoesNotExist):
        PositionSnapshot.for_user(user_b).get(pk=pos.pk)
    with pytest.raises(AccountSnapshot.DoesNotExist):
        AccountSnapshot.for_user(user_b).get(pk=acct.pk)
    with pytest.raises(Trade.DoesNotExist):
        Trade.for_user(user_b).get(pk=trade.pk)

    # The owner still sees their own rows.
    assert PositionSnapshot.for_user(user_a).get(pk=pos.pk) == pos
    assert AccountSnapshot.for_user(user_a).get(pk=acct.pk) == acct
    assert Trade.for_user(user_a).get(pk=trade.pk) == trade


@pytest.mark.django_db
def test_for_user_scopes_private_models_to_the_owner(user_a, user_b):
    PositionSnapshot.objects.create(user=user_a, symbol="BTCUSDT", ts=TS)
    AccountSnapshot.objects.create(user=user_a, ts=TS)
    Trade.objects.create(user=user_a, trade_id="T1", symbol="BTCUSDT", ctime=1)

    assert PositionSnapshot.for_user(user_a).count() == 1
    assert AccountSnapshot.for_user(user_a).count() == 1
    assert Trade.for_user(user_a).count() == 1
    assert PositionSnapshot.for_user(user_b).count() == 0
    assert AccountSnapshot.for_user(user_b).count() == 0
    assert Trade.for_user(user_b).count() == 0


@pytest.mark.django_db
def test_same_trade_id_allowed_across_users(user_a, user_b):
    # R1: trade_id uniqueness is per user — A and B do not collide on one id.
    mine = Trade.objects.create(user=user_a, trade_id="T1", symbol="BTCUSDT", ctime=1)
    theirs = Trade.objects.create(user=user_b, trade_id="T1", symbol="BTCUSDT", ctime=1)

    assert mine.pk != theirs.pk
    assert Trade.for_user(user_a).get(trade_id="T1") == mine
    assert Trade.for_user(user_b).get(trade_id="T1") == theirs


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
