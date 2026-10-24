"""Dust flag and IR recommendation when optical is obscured."""

from __future__ import annotations

from backend.schemas import CandidateScore

# Threshold in A_V magnitudes: fields with A_V above this get an IR recommendation.
# Conservative placeholder until Tony wires a dust map; null A_V → no IR flag.
AV_IR_THRESHOLD_MAG = 1.0


def ir_followup_recommended(
    *,
    ra_deg: float,
    dec_deg: float,
    extinction_av_mag: float | None,
) -> bool:
    """Return True when dust likely hides the optical transient.

    Uses only the provided A_V when present; does not invent extinction values.
    ``ra_deg`` / ``dec_deg`` reserved for a future dust-map lookup.
    """
    del ra_deg, dec_deg
    if extinction_av_mag is None:
        return False
    return float(extinction_av_mag) >= AV_IR_THRESHOLD_MAG


def apply_extinction_flag(score: CandidateScore) -> CandidateScore:
    """Set ir_followup on a CandidateScore from position / A_V."""
    flag = ir_followup_recommended(
        ra_deg=score.ra_deg,
        dec_deg=score.dec_deg,
        extinction_av_mag=score.extinction_av_mag,
    )
    return score.model_copy(update={"ir_followup": flag})
