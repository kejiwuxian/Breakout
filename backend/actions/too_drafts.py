"""HST / JWST ToO request drafts (Markdown) for human review.

Never submitted automatically. People approve before any submission.
JWST drafts always note that very bright targets cannot be observed.
"""

from __future__ import annotations

from backend.schemas import CandidateScore, SkyMap


def _sim_tag(simulated: bool) -> str:
    return " **[simulated]**" if simulated else ""


def _coord_block(candidate: CandidateScore) -> str:
    sim = _sim_tag(candidate.simulated)
    dist = (
        f"{candidate.distance_kpc:.3f} kpc{_sim_tag(candidate.simulated)}"
        if candidate.distance_kpc is not None
        else "unknown (catalog null; not invented)"
    )
    av = (
        f"{candidate.extinction_av_mag:.2f} mag{_sim_tag(candidate.simulated)}"
        if candidate.extinction_av_mag is not None
        else "unknown (catalog null; not invented)"
    )
    return "\n".join(
        [
            f"- **Target:** `{candidate.star_id}` (`{candidate.class_}` / {candidate.spectral_type})",
            f"- **ICRS RA:** {candidate.ra_deg:.6f} deg{sim}",
            f"- **ICRS Dec:** {candidate.dec_deg:.6f} deg{sim}",
            f"- **Distance:** {dist}",
            f"- **A_V:** {av}",
            f"- **IR follow-up recommended:** {bool(candidate.ir_followup)} "
            f"(catalog A_V vs threshold; no invented extinction)",
            f"- **Posterior (rank weight):** {candidate.posterior:.6f}{sim}",
            f"- **p_sky:** {candidate.p_sky:.6e}{sim}",
            f"- **Breakout window (estimate):** {candidate.breakout.class_window} "
            f"from {candidate.breakout.countdown_from}",
        ]
    )


def _evidence_block(candidate: CandidateScore) -> str:
    evidence = candidate.lit.evidence or []
    if not evidence:
        return (
            "No ADS-bibcoded literature claims on this CandidateScore row "
            "(no bibcode → no claim; nothing invented)."
        )
    lines = ["Literature evidence (ADS bibcodes only):"]
    for ev in evidence:
        bib = (ev.bibcode or "").strip()
        claim = (ev.claim or "").strip()
        if not bib or not claim:
            continue
        lines.append(f"- `{bib}` — {claim}")
    if len(lines) == 1:
        return (
            "No ADS-bibcoded literature claims on this CandidateScore row "
            "(no bibcode → no claim; nothing invented)."
        )
    return "\n".join(lines)


def _skymap_block(skymap: SkyMap) -> str:
    sim = _sim_tag(skymap.simulated)
    return "\n".join(
        [
            f"- **Alert id:** `{skymap.alert_id}`",
            f"- **Credible 90% area:** {skymap.credible_90_deg2:.2f} deg²{sim}",
            f"- **Peak (ICRS):** RA {skymap.peak.ra_deg:.6f} deg, "
            f"Dec {skymap.peak.dec_deg:.6f} deg{sim}",
            f"- **Components:** {', '.join(skymap.components) or '(none)'}",
            f"- **Simulated map:** {bool(skymap.simulated)}",
        ]
    )


def draft_hst_too(candidate: CandidateScore, skymap: SkyMap) -> str:
    """Return an HST ToO request draft (Markdown). Not submitted automatically."""
    parts = [
        "# HST Target of Opportunity — DRAFT for human review",
        "",
        "BREAKOUT prepares this draft only. **Do not submit** without human approval.",
        "Coordinates are ICRS degrees. Simulated numbers are labeled **[simulated]**.",
        "",
        "## Localization context",
        _skymap_block(skymap),
        "",
        "## Proposed target",
        _coord_block(candidate),
        "",
        "## Science rationale (from offline literature index)",
        _evidence_block(candidate),
        "",
        "## Request notes",
        "- Instrument / mode: to be chosen by the PI (not auto-filled).",
        "- Urgency: shock-breakout / early light-curve capture after neutrino alert.",
        "- This file is a draft; STScI ToO policies and APT submission remain human-owned.",
        "",
        f"simulated={str(bool(candidate.simulated or skymap.simulated)).lower()}",
    ]
    return "\n".join(parts) + "\n"


def draft_jwst_too(candidate: CandidateScore, skymap: SkyMap) -> str:
    """Return a JWST ToO request draft (Markdown). Not submitted automatically.

    Note: JWST cannot observe very bright targets; the draft must say so when
    relevant. People approve before any submission.
    """
    bright_note = (
        "**Brightness constraint:** JWST cannot observe very bright targets "
        "(saturation / bright-object limits). Nearby Galactic RSGs such as "
        f"`{candidate.star_id}` may be too bright for standard imaging modes; "
        "confirm brightness and allowed modes with STScI docs before any APT "
        "submission. BREAKOUT does not invent magnitudes."
    )
    parts = [
        "# JWST Target of Opportunity — DRAFT for human review",
        "",
        "BREAKOUT prepares this draft only. **Do not submit** without human approval.",
        "Coordinates are ICRS degrees. Simulated numbers are labeled **[simulated]**.",
        "",
        "## Critical observing constraint",
        bright_note,
        "",
        "## Localization context",
        _skymap_block(skymap),
        "",
        "## Proposed target",
        _coord_block(candidate),
        "",
        "## Science rationale (from offline literature index)",
        _evidence_block(candidate),
        "",
        "## Request notes",
        "- JWST ToO response floors (hours–days) may miss the earliest breakout window; "
          "treat as later IR science under an approved program.",
        "- Instrument / mode: to be chosen by the PI after brightness check "
          "(not auto-filled; no invented flux).",
        "- This file is a draft; JWST ToO policies and APT submission remain human-owned.",
        "",
        f"simulated={str(bool(candidate.simulated or skymap.simulated)).lower()}",
    ]
    return "\n".join(parts) + "\n"
