"""R6/R7/R8 contract: the ``evaluate_setups`` command (smc-setup-outcomes).

Tests drive the module-level ``run(now, ...)`` seam with an injected ``now``
(no wall clock in the tested path) and an ``OutRecorder``, mirroring
``test_prune_snapshots``. Setups and candles are seeded directly; the pure
``resolve_setup`` under the seam is already contract-tested, so assertions
target the command's own behavior: gating, ordering, selection flags,
idempotent upsert and the dry-run contract.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from trading.models import Candle, Setup, SetupOutcome

pytestmark = pytest.mark.django_db

SYMBOL = "BTCUSDT"
INTERVAL = "1h"
ANCHOR = 1_700_000_000
HOUR = 3600
NOW = ANCHOR + 4 * HOUR

# Four candles strictly after ANCHOR: c1 activates (touches entry=100),
# c4 touches take_profit=110 → take_profit resolved on c4 (bars=3).
TP_ROWS = [(1, 105.0, 95.0), (2, 105.0, 96.0), (3, 105.0, 96.0), (4, 111.0, 104.0)]


class OutRecorder:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, message):
        self.lines.append(str(message))


def _setup(anchor=ANCHOR, symbol=SYMBOL, interval=INTERVAL, **fields):
    defaults = dict(
        direction="long",
        entry=100.0,
        stop=90.0,
        take_profit=110.0,
        rr=1.0,
        score=3,
        engine_version="1:w200",
    )
    defaults.update(fields)
    return Setup.objects.create(
        symbol=symbol, interval=interval, anchor_time=anchor, **defaults
    )


def _candles(anchor=ANCHOR, symbol=SYMBOL, interval=INTERVAL, rows=TP_ROWS):
    Candle.objects.bulk_create(
        [
            Candle(
                symbol=symbol,
                interval=interval,
                time=anchor + offset * HOUR,
                open=100.0,
                high=high,
                low=low,
                close=100.0,
            )
            for offset, high, low in rows
        ]
    )


def _run(now=NOW, **overrides):
    from trading.management.commands.evaluate_setups import run

    out = OutRecorder()
    written = run(
        overrides.get("now", now),
        interval=overrides.get("interval"),
        horizon_bars=overrides.get("horizon_bars", 4),
        max_setups=overrides.get("max_setups"),
        dry_run=overrides.get("dry_run", False),
        out=out,
    )
    return written, out


# --- R6: full-horizon gating -----------------------------------------------


def test_full_horizon_gate_skips_incomplete_window():
    _setup(anchor=ANCHOR)
    _candles()

    written, out = _run(now=ANCHOR + 3 * HOUR)

    assert written == 0
    assert SetupOutcome.objects.count() == 0
    assert "evaluate done: evaluated=0 skipped=1" in out.lines


def test_setup_becomes_eligible_when_now_advances():
    _setup(anchor=ANCHOR)
    _candles()

    written, _ = _run(now=NOW)

    assert written == 1
    outcome = SetupOutcome.objects.get()
    assert outcome.status == "take_profit"
    assert outcome.resolved_time == ANCHOR + 4 * HOUR
    assert outcome.bars_to_resolution == 3
    assert outcome.mfe_r == pytest.approx(1.1)
    assert outcome.mae_r == pytest.approx(-0.5)
    assert outcome.sl_then_tp is None
    assert outcome.horizon_bars == 4


def test_now_is_injected_not_wall_clock():
    _setup(anchor=ANCHOR)
    _candles()

    # The real clock (2026) is far past the horizon end; the injected `now`
    # (before it) must govern — if run() read the wall clock this would
    # evaluate. Mirrors the prune_snapshots clock-injection proof.
    written, _ = _run(now=ANCHOR + 3 * HOUR)

    assert written == 0
    assert SetupOutcome.objects.count() == 0


# --- R7: deterministic selection -------------------------------------------


def test_order_is_anchor_ascending_with_id_tiebreak():
    eth = _setup(anchor=ANCHOR - 2 * HOUR, symbol="ETHUSDT")
    btc = _setup(anchor=ANCHOR - 2 * HOUR, symbol="BTCUSDT")
    sol = _setup(anchor=ANCHOR - HOUR, symbol="SOLUSDT")
    for setup in (eth, btc, sol):
        _candles(anchor=setup.anchor_time, symbol=setup.symbol)

    _, out = _run()

    # eth/btc share an anchor: the stable id tie-break keeps creation order.
    assert out.lines[:3] == [
        "ETHUSDT 1h: take_profit",
        "BTCUSDT 1h: take_profit",
        "SOLUSDT 1h: take_profit",
    ]


def test_interval_filter_selects_only_matching():
    _setup(anchor=ANCHOR - 2 * HOUR)
    _setup(anchor=ANCHOR - 16 * HOUR, symbol="ETHUSDT", interval="4h")
    _candles(anchor=ANCHOR - 2 * HOUR)
    _candles(anchor=ANCHOR - 16 * HOUR, symbol="ETHUSDT", interval="4h")

    written, _ = _run(interval="1h")

    assert written == 1
    assert SetupOutcome.objects.count() == 1
    assert SetupOutcome.objects.get().setup.symbol == "BTCUSDT"


def test_interval_absent_evaluates_every_interval():
    _setup(anchor=ANCHOR - 2 * HOUR)
    _setup(anchor=ANCHOR - 16 * HOUR, symbol="ETHUSDT", interval="4h")
    _candles(anchor=ANCHOR - 2 * HOUR)
    _candles(anchor=ANCHOR - 16 * HOUR, symbol="ETHUSDT", interval="4h")

    written, out = _run()

    assert written == 2
    assert SetupOutcome.objects.count() == 2
    # The older 4h setup is evaluated first: ascending anchor across intervals.
    assert out.lines[0].startswith("ETHUSDT 4h:")


def test_unknown_interval_raises_naming_it():
    with pytest.raises(ValueError, match="bogus"):
        _run(interval="bogus")


def test_max_setups_bounds_processed_setups():
    btc = _setup(anchor=ANCHOR - 3 * HOUR)
    eth = _setup(anchor=ANCHOR - 2 * HOUR, symbol="ETHUSDT")
    sol = _setup(anchor=ANCHOR - HOUR, symbol="SOLUSDT")
    for setup in (btc, eth, sol):
        _candles(anchor=setup.anchor_time, symbol=setup.symbol)

    written, _ = _run(max_setups=2)

    assert written == 2
    symbols = set(SetupOutcome.objects.values_list("setup__symbol", flat=True))
    assert symbols == {"BTCUSDT", "ETHUSDT"}


# --- R7: idempotency, dry-run, recalculation --------------------------------


def test_dry_run_writes_nothing_and_reports_would_write():
    _setup(anchor=ANCHOR)
    _candles()

    written, out = _run(dry_run=True)

    assert written == 1
    assert SetupOutcome.objects.count() == 0
    assert out.lines == [
        f"{SYMBOL} {INTERVAL}: would_write=take_profit",
        "evaluate done: evaluated=1 skipped=0",
    ]


def test_rerun_is_idempotent():
    _setup(anchor=ANCHOR)
    _candles()

    first, _ = _run()
    second, _ = _run()

    assert first == second == 1
    assert SetupOutcome.objects.count() == 1
    assert Setup.objects.count() == 1


def test_horizon_recalc_overwrites_outcome_and_leaves_setup_byte_identical():
    _setup(anchor=ANCHOR)
    _candles()
    _run()  # horizon 4 → take_profit on c4
    before = list(Setup.objects.order_by("id").values())

    written, _ = _run(horizon_bars=2)

    assert written == 1
    assert SetupOutcome.objects.count() == 1
    outcome = SetupOutcome.objects.get()
    assert outcome.status == "expired"  # only c1..c2 walked: no resolution
    assert outcome.horizon_bars == 2
    assert outcome.resolved_time is None
    assert list(Setup.objects.order_by("id").values()) == before


def test_engine_version_stamp_copied_verbatim_across_reruns():
    _setup(anchor=ANCHOR, engine_version="1:w200")
    _candles()

    _run()
    assert SetupOutcome.objects.get().engine_version == "1:w200"

    _run(horizon_bars=2)
    assert SetupOutcome.objects.get().engine_version == "1:w200"


# --- progress reporting -----------------------------------------------------


def test_out_receives_progress_and_done_lines():
    _setup(anchor=ANCHOR)
    _candles()

    _, out = _run()

    assert out.lines[0] == f"{SYMBOL} {INTERVAL}: take_profit"
    assert out.lines[-1] == "evaluate done: evaluated=1 skipped=0"


# --- CLI wiring -------------------------------------------------------------


def test_call_command_wires_flags_to_run():
    _setup(anchor=ANCHOR)  # historical (2023): its full horizon is long past
    _candles()

    call_command("evaluate_setups", horizon_bars=4)

    assert SetupOutcome.objects.count() == 1
    assert SetupOutcome.objects.get().status == "take_profit"
