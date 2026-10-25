"""Build the community alert JSON package from pipeline outputs."""

from __future__ import annotations

from typing import Any

from backend.schemas import Alert, CandidateScore, SkyMap

SCHEMA_VERSION = "breakout.community_alert.v1"


def _candidate_public(score: CandidateScore) -> dict[str, Any]:
    """Public follow-up row: coords + ranking; evidence bibcodes only if present."""
    evidence = [
        {"bibcode": e.bibcode, "claim": e.claim}
        for e in score.lit.evidence
        if e.bibcode
    ]
    row: dict[str, Any] = {
        "star_id": score.star_id,
        "ra_deg": score.ra_deg,
        "dec_deg": score.dec_deg,
        "class": score.class_,
        "spectral_type": score.spectral_type,
        "distance_kpc": score.distance_kpc,
        "p_sky": score.p_sky,
        "posterior": score.posterior,
        "breakout": {
            "class_window": score.breakout.class_window,
            "countdown_from": score.breakout.countdown_from,
        },
        "ir_followup": score.ir_followup,
        "presn_watch": score.presn_watch,
        "evidence": evidence,
        "simulated": bool(score.simulated),
        # v1.1 inventory / Grok rank fields (null when absent)
        "rank_confidence": score.rank_confidence,
        "rank_reasoning": score.rank_reasoning,
        "composition": score.composition,
        "life_expectancy": (
            score.life_expectancy.model_dump(mode="json")
            if score.life_expectancy is not None
            else None
        ),
    }
    return row


def build_community_alert(
    alert: Alert,
    skymap: SkyMap,
    candidates: list[CandidateScore],
    *,
    max_candidates: int = 10,
) -> dict[str, Any]:
    """Package ranked stars for community telescope follow-up.

    Suitable for webhook POST bodies and ``GET /alerts/latest``. Does not invent
    numbers: only fields already present on Alert / SkyMap / CandidateScore.
    """
    top = candidates[: max(0, int(max_candidates))]
    simulated = bool(alert.simulated) or bool(skymap.simulated) or any(
        c.simulated for c in top
    )
    return {
        "schema": SCHEMA_VERSION,
        "type": "breakout.ranked_candidates",
        "alert_id": alert.alert_id,
        "kind": alert.kind,
        "source": alert.source,
        "t0_utc": alert.t0_utc,
        "significance": alert.significance,
        "simulated": simulated,
        "skymap": {
            "peak_ra_deg": skymap.peak.ra_deg,
            "peak_dec_deg": skymap.peak.dec_deg,
            "credible_90_deg2": skymap.credible_90_deg2,
            "components": list(skymap.components),
            "simulated": bool(skymap.simulated),
        },
        "candidates": [_candidate_public(c) for c in top],
        "instrument_hint": (
            "Point optical/NIR instruments at ranked ICRS coordinates. "
            "Prefer IR filters when ir_followup is true. "
            "This is a BREAKOUT community alert, not an official GCN notice."
        ),
        "note": (
            "Fields with simulated=true are not real observations. "
            "Evidence claims cite only ADS bibcodes already on CandidateScore."
        ),
    }
