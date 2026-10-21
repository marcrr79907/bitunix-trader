"""Contract tests for the pure setup-outcome resolver (smc-setup-outcomes R2-R5, R9).

Strict TDD: RED written before implementation. ``resolve_setup`` walks candles
strictly after the anchor (the caller filters), activates on the first candle
touching entry, and resolves conservatively: a candle covering both stop and
take-profit is ``ambiguous`` — counted as a loss, never a win. DB-free: no
Django, no clock, no I/O, never raises.
"""

from __future__ import annotations

import copy

import pytest

from src.smc.signals import OutcomeRecord, resolve_setup

BASE = 1_700_000_000
STEP = 3600

LONG = {"direction": "long", "entry": 100.0, "stop": 90.0, "take_profit": 110.0}
SHORT = {"direction": "short", "entry": 100.0, "stop": 110.0, "take_profit": 90.0}


def _candles(rows):
    """``[(high, low), ...]`` → ``[(time, high, low), ...]`` ascending from BASE."""
    return [(BASE + i * STEP, high, low) for i, (high, low) in enumerate(rows)]


# --- shape ----------------------------------------------------------------


def test_outcome_record_shape_is_the_six_frozen_fields():
    out = resolve_setup(**LONG, candles=_candles([(100.5, 99.5)]))

    assert out._fields == (
        "status",
        "resolved_time",
        "bars_to_resolution",
        "mfe_r",
        "mae_r",
        "sl_then_tp",
    )


# --- five statuses (R2) ---------------------------------------------------


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        # TP candle after activation, stop untouched → take_profit.
        (
            [(100.5, 99.5), (110.5, 109.5)],
            OutcomeRecord("take_profit", BASE + STEP, 1, 1.05, -0.05, None),
        ),
        # Stop candle after activation, no later TP → stop_loss, sl_then_tp False.
        # Window spans activation→resolution inclusive: lows min 89.5 → -1.05.
        (
            [(100.5, 99.5), (90.5, 89.5), (95.0, 94.0)],
            OutcomeRecord("stop_loss", BASE + STEP, 1, 0.05, -1.05, False),
        ),
        # One candle covering both levels → ambiguous (conservative, never TP).
        (
            [(100.5, 99.5), (110.5, 89.5), (95.0, 94.0)],
            OutcomeRecord("ambiguous", BASE + STEP, 1, 1.05, -1.05, False),
        ),
        # Horizon exhausted with no stop/TP touch → expired, resolved_time NULL.
        (
            [(100.5, 99.5), (105.0, 95.0), (105.0, 95.0), (105.0, 95.0)],
            OutcomeRecord("expired", None, None, 0.5, -0.5, None),
        ),
        # Entry never touched (stop touches before activation are ignored).
        (
            [(95.0, 85.0), (95.0, 85.0), (95.0, 85.0)],
            OutcomeRecord("not_triggered", None, None, -0.5, -1.5, None),
        ),
    ],
)
def test_five_statuses(rows, expected):
    assert resolve_setup(**LONG, candles=_candles(rows)) == expected


def test_same_candle_sl_and_tp_is_ambiguous_never_take_profit():
    # The activation candle itself spans stop AND take-profit: the honest
    # conservative answer is ambiguous (counted as a loss), never a win.
    out = resolve_setup(**LONG, candles=_candles([(110.5, 89.5)]))

    assert out.status == "ambiguous"
    assert out.status != "take_profit"
    assert out.resolved_time == BASE
    assert out.bars_to_resolution == 0


# --- sl_then_tp (R5) ------------------------------------------------------


def test_sl_then_tp_true_when_tp_touched_strictly_later():
    rows = [(100.5, 99.5), (90.5, 89.5), (110.5, 109.5)]

    out = resolve_setup(**LONG, candles=_candles(rows))

    assert out.status == "stop_loss"
    assert out.sl_then_tp is True


@pytest.mark.parametrize(
    "rows",
    [
        # Ambiguous on the resolution candle itself: that TP touch is NOT
        # "strictly after", so without a later touch the flag is False.
        [(110.5, 89.5)],
        # A later candle touching TP flips it to True.
        [(110.5, 89.5), (110.5, 109.5)],
    ],
)
def test_sl_then_tp_reads_only_strictly_after_the_resolution_candle(rows):
    out = resolve_setup(**LONG, candles=_candles(rows))

    assert out.status == "ambiguous"
    assert out.sl_then_tp is (len(rows) > 1)


@pytest.mark.parametrize(
    "rows",
    [
        [(100.5, 99.5), (110.5, 109.5)],  # take_profit
        [(100.5, 99.5), (105.0, 95.0), (105.0, 95.0)],  # expired
        [(95.0, 85.0), (95.0, 85.0)],  # not_triggered
    ],
)
def test_sl_then_tp_is_null_for_every_other_status(rows):
    out = resolve_setup(**LONG, candles=_candles(rows))

    assert out.sl_then_tp is None


# --- R = 0 guards (R4) ----------------------------------------------------


@pytest.mark.parametrize(
    ("rows", "status"),
    [
        # entry == stop: the activation candle touches stop immediately.
        ([(100.5, 99.5), (100.5, 99.5)], "stop_loss"),
        # entry == stop and the same candle also touches TP → ambiguous.
        ([(110.5, 99.5)], "ambiguous"),
        # entry == stop and entry never touched: the division guard still holds.
        ([(95.0, 85.0)], "not_triggered"),
    ],
)
def test_r_zero_degrades_every_r_metric_to_null(rows, status):
    zero = {"direction": "long", "entry": 100.0, "stop": 100.0, "take_profit": 110.0}
    out = resolve_setup(**zero, candles=_candles(rows))

    assert out.status == status
    assert out.mfe_r is None
    assert out.mae_r is None
    assert out.sl_then_tp is None


# --- MFE/MAE direction formulas (R4) --------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "rows", "expected"),
    [
        # long: mfe = max((high - entry)/R), mae = min((low - entry)/R).
        (
            LONG,
            [(100.5, 99.5), (112.0, 109.0)],
            OutcomeRecord("take_profit", BASE + STEP, 1, 1.2, -0.05, None),
        ),
        # short: mfe = max((entry - low)/R), mae = min((entry - high)/R).
        (
            SHORT,
            [(100.5, 99.5), (91.0, 87.0)],
            OutcomeRecord("take_profit", BASE + STEP, 1, 1.3, -0.05, None),
        ),
    ],
)
def test_mfe_mae_follow_the_direction_formulas(kwargs, rows, expected):
    assert resolve_setup(**kwargs, candles=_candles(rows)) == expected


def test_tp_resolution_has_mfe_at_least_rr():
    out = resolve_setup(**LONG, candles=_candles([(100.5, 99.5), (110.5, 109.5)]))

    assert out.mfe_r >= (LONG["take_profit"] - LONG["entry"]) / (
        LONG["entry"] - LONG["stop"]
    )


def test_never_activated_mae_is_clamped_to_zero():
    # Price never crossed the adverse side: the raw formula is positive there,
    # and mae_r MUST be <= 0.
    out = resolve_setup(**LONG, candles=_candles([(105.0, 101.0)]))

    assert out.status == "not_triggered"
    assert out.mfe_r == 0.5
    assert out.mae_r == 0.0


# --- bars_to_resolution (R3) ----------------------------------------------


def test_bars_to_resolution_is_zero_when_the_activation_candle_resolves():
    out = resolve_setup(**LONG, candles=_candles([(105.0, 89.0)]))

    assert out.status == "stop_loss"
    assert out.bars_to_resolution == 0
    assert out.resolved_time == BASE


def test_bars_to_resolution_counts_from_activation_not_from_the_anchor():
    rows = [(100.5, 99.5), (98.0, 97.0), (98.0, 97.0), (110.5, 109.5)]

    out = resolve_setup(**LONG, candles=_candles(rows))

    assert out.status == "take_profit"
    assert out.bars_to_resolution == 3
    assert out.resolved_time == BASE + 3 * STEP


def test_horizon_bars_slices_the_walk():
    rows = [(100.5, 99.5), (98.0, 97.0), (90.5, 89.5)]

    short_horizon = resolve_setup(**LONG, candles=_candles(rows), horizon_bars=2)
    full_horizon = resolve_setup(**LONG, candles=_candles(rows))

    assert short_horizon == OutcomeRecord("expired", None, None, 0.05, -0.3, None)
    assert full_horizon.status == "stop_loss"


# --- purity, guards, determinism (R9) -------------------------------------


def test_empty_candles_are_not_triggered_without_raising():
    assert resolve_setup(**LONG, candles=[]) == OutcomeRecord(
        "not_triggered", None, None, None, None, None
    )


def test_resolver_is_deterministic_and_does_not_mutate_inputs():
    rows = [(100.5, 99.5), (90.5, 89.5), (110.5, 109.5)]
    candles = _candles(rows)
    frozen = copy.deepcopy(candles)

    first = resolve_setup(**LONG, candles=candles)
    second = resolve_setup(**LONG, candles=candles)

    assert first == second
    assert candles == frozen
