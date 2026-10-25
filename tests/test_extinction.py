"""Tests for backend.physics.extinction IR flag."""

from __future__ import annotations

from backend.config import AV_IR_THRESHOLD_MAG, AV_IR_THRESHOLD_SOURCE
from backend.physics.extinction import (
    apply_extinction_flag,
    extinction_decision,
    ir_followup_recommended,
)
from backend.schemas import Breakout, CandidateScore, Literature


def _score(*, av: float | None) -> CandidateScore:
    return CandidateScore(
        star_id="test",
        ra_deg=10.0,
        dec_deg=-5.0,
        class_="RSG",
        spectral_type="M1",
        extinction_av_mag=av,
        p_sky=0.1,
        lit=Literature(
            mass_loss=0.0,
            variability=0.0,
            evolved_stage=0.0,
            confidence=0.0,
            evidence=[],
        ),
        posterior=0.0,
        breakout=Breakout(class_window="about 1 day", countdown_from="2026-10-24T00:00:00Z"),
        ir_followup=False,
        simulated=False,
    )


def test_ir_flag_when_av_above_threshold() -> None:
    av = AV_IR_THRESHOLD_MAG + 0.5
    decision = extinction_decision(ra_deg=0.0, dec_deg=0.0, extinction_av_mag=av)
    assert decision.ir_followup is True
    assert "recommend IR" in decision.reason
    assert str(AV_IR_THRESHOLD_MAG) in decision.reason or f"threshold={AV_IR_THRESHOLD_MAG}" in decision.reason
    assert decision.source == AV_IR_THRESHOLD_SOURCE
    assert ir_followup_recommended(ra_deg=0.0, dec_deg=0.0, extinction_av_mag=av) is True
    flagged = apply_extinction_flag(_score(av=av))
    assert flagged.ir_followup is True


def test_no_ir_flag_when_av_null_or_below() -> None:
    null_decision = extinction_decision(ra_deg=0.0, dec_deg=0.0, extinction_av_mag=None)
    assert null_decision.ir_followup is False
    assert "null" in null_decision.reason.lower()
    assert "never invent" in null_decision.reason.lower()

    low = max(AV_IR_THRESHOLD_MAG - 0.5, 0.0)
    if low < AV_IR_THRESHOLD_MAG:
        low_decision = extinction_decision(ra_deg=0.0, dec_deg=0.0, extinction_av_mag=low)
        assert low_decision.ir_followup is False
        assert apply_extinction_flag(_score(av=low)).ir_followup is False

    assert apply_extinction_flag(_score(av=None)).ir_followup is False
