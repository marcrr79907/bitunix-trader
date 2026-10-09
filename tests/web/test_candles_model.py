"""R1 contract: global Candle model.

A candle is shared market data, not per-user: no owner FK, not
``UserOwnedModel``. The unique ``(symbol, interval, time)`` key makes re-persist
idempotent, and the composite index serves per-series range scans.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, transaction
from trading.models import Candle, UserOwnedModel


def test_candle_is_global_not_owned():
    assert not issubclass(Candle, UserOwnedModel)
    with pytest.raises(FieldDoesNotExist):
        Candle._meta.get_field("user")


@pytest.mark.django_db
def test_unique_symbol_interval_time_rejects_duplicate():
    row = dict(
        symbol="BTCUSDT",
        interval="5m",
        time=1_700_000_000,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
    )
    Candle.objects.create(**row)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Candle.objects.create(**row)

    assert Candle.objects.count() == 1


@pytest.mark.django_db
def test_same_time_different_series_is_allowed():
    # Triangulation: the uniqueness is the triple, not time alone.
    base = dict(time=1_700_000_000, open=1.0, high=2.0, low=0.5, close=1.5)
    Candle.objects.create(symbol="BTCUSDT", interval="5m", **base)
    Candle.objects.create(symbol="BTCUSDT", interval="1h", **base)
    Candle.objects.create(symbol="ETHUSDT", interval="5m", **base)

    assert Candle.objects.count() == 3


def test_composite_index_present():
    names = {index.name for index in Candle._meta.indexes}
    assert "ix_candle_symbol_interval_time" in names

    index = next(
        i for i in Candle._meta.indexes if i.name == "ix_candle_symbol_interval_time"
    )
    assert list(index.fields) == ["symbol", "interval", "time"]


def test_quote_vol_is_nullable():
    field = Candle._meta.get_field("quote_vol")
    assert field.null is True
