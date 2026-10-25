"""Tests for backend.physics.breakout_window."""

from __future__ import annotations

from backend.config import CLASS_WINDOWS
from backend.physics.breakout_window import breakout_countdown, class_window


def test_class_windows_match_config_citations() -> None:
    assert CLASS_WINDOWS["WR"] == "minutes"
    assert CLASS_WINDOWS["BSG"] == "hours"
    assert CLASS_WINDOWS["RSG"] == "about 1 day"
    assert CLASS_WINDOWS["UNK"] == "n/a"
    assert class_window("WR") == "minutes"
    assert class_window("BSG") == "hours"
    assert class_window("RSG") == "about 1 day"
    assert class_window("UNK") == "n/a"


def test_breakout_countdown_uses_burst_t0() -> None:
    t0 = "2026-10-24T21:46:00Z"
    b = breakout_countdown("WR", t0_utc=t0)
    assert b.class_window == "minutes"
    assert b.countdown_from == t0
    b_rsg = breakout_countdown("RSG", t0_utc=t0)
    assert b_rsg.class_window == "about 1 day"
    assert b_rsg.countdown_from == t0


def test_unk_field_star_does_not_inherit_rsg_breakout() -> None:
    """BSC5/UNK AOI hits must not clone Betelgeuse/RSG life+breakout windows."""
    t0 = "2026-10-24T21:46:00Z"
    rsg = breakout_countdown("RSG", t0_utc=t0)
    unk = breakout_countdown("UNK", t0_utc=t0)
    assert rsg.class_window == "about 1 day"
    assert unk.class_window == "n/a"
    assert unk.class_window != rsg.class_window
    # Truly unknown class strings also stay absent (not silent RSG promotion).
    assert class_window("NOT_A_CLASS") == "n/a"
