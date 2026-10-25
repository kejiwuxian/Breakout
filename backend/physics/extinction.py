"""Dust flag and IR recommendation when optical is obscured.

Uses only catalog ``extinction_av_mag`` when present. Never invents A_V.
Threshold and source live in ``backend.config`` (AV_IR_THRESHOLD_*).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.config import AV_IR_THRESHOLD_MAG, AV_IR_THRESHOLD_SOURCE, settings
from backend.schemas import CandidateScore


@dataclass(frozen=True)
class ExtinctionDecision:
    """IR follow-up decision with an explicit why (for UI / logs / tests)."""

    ir_followup: bool
    reason: str
    threshold_mag: float
    extinction_av_mag: float | None
    source: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _threshold() -> float:
    return float(getattr(settings, "av_ir_threshold_mag", AV_IR_THRESHOLD_MAG))


def extinction_decision(
    *,
    ra_deg: float,
    dec_deg: float,
    extinction_av_mag: float | None,
) -> ExtinctionDecision:
    """Decide IR follow-up and record why. Does not invent extinction values.

    ``ra_deg`` / ``dec_deg`` are reserved for a future dust-map lookup; the MVP
    uses only the catalog A_V when provided.
    """
    del ra_deg, dec_deg
    threshold = _threshold()
    source = AV_IR_THRESHOLD_SOURCE

    if extinction_av_mag is None:
        return ExtinctionDecision(
            ir_followup=False,
            reason=(
                "extinction_av_mag is null; no IR flag "
                "(never invent dust). "
                f"threshold={threshold} mag; source={source}"
            ),
            threshold_mag=threshold,
            extinction_av_mag=None,
            source=source,
        )

    av = float(extinction_av_mag)
    if av >= threshold:
        return ExtinctionDecision(
            ir_followup=True,
            reason=(
                f"extinction_av_mag={av} >= threshold={threshold} mag → "
                f"recommend IR follow-up. source={source}"
            ),
            threshold_mag=threshold,
            extinction_av_mag=av,
            source=source,
        )
    return ExtinctionDecision(
        ir_followup=False,
        reason=(
            f"extinction_av_mag={av} < threshold={threshold} mag → "
            f"no IR flag. source={source}"
        ),
        threshold_mag=threshold,
        extinction_av_mag=av,
        source=source,
    )


def ir_followup_recommended(
    *,
    ra_deg: float,
    dec_deg: float,
    extinction_av_mag: float | None,
) -> bool:
    """Return True when dust likely hides the optical transient."""
    return extinction_decision(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        extinction_av_mag=extinction_av_mag,
    ).ir_followup


def apply_extinction_flag(score: CandidateScore) -> CandidateScore:
    """Set ``ir_followup`` on a CandidateScore from catalog A_V / threshold."""
    decision = extinction_decision(
        ra_deg=score.ra_deg,
        dec_deg=score.dec_deg,
        extinction_av_mag=score.extinction_av_mag,
    )
    return score.model_copy(update={"ir_followup": decision.ir_followup})
