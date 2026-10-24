"""Dust flag and IR recommendation when optical is obscured."""

from __future__ import annotations

from backend.schemas import CandidateScore


def ir_followup_recommended(
    *,
    ra_deg: float,
    dec_deg: float,
    extinction_av_mag: float | None,
) -> bool:
    """Return True when dust likely hides the optical transient."""
    raise NotImplementedError("ir_followup_recommended is filled in a later prompt.")


def apply_extinction_flag(score: CandidateScore) -> CandidateScore:
    """Set ir_followup on a CandidateScore from position / A_V."""
    raise NotImplementedError("apply_extinction_flag is filled in a later prompt.")
