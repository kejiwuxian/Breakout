"""GCN Circular draft for human review (never auto-submitted)."""

from __future__ import annotations

from backend.schemas import Alert, CandidateScore, SkyMap


def _sim_label(simulated: bool) -> str:
    return " (simulated)" if simulated else ""


def draft_circular(
    alert: Alert,
    skymap: SkyMap,
    candidates: list[CandidateScore],
) -> str:
    """Return a GCN Circular draft (Markdown) marked for human review.

    GCN Circulars are written and submitted by people; BREAKOUT only drafts.
    Label every simulated number as simulated. Cite only ADS bibcodes present
    on CandidateScore evidence (no invented citations).
    """
    top = candidates[0] if candidates else None
    sim_alert = bool(alert.simulated)
    sim_map = bool(skymap.simulated)

    detector_lines: list[str] = []
    for hit in alert.detectors:
        n_label = f"{hit.n_events}{_sim_label(sim_alert)}"
        pointing = "no pointing"
        if hit.pointing is not None:
            pointing = (
                f"pointing RA={hit.pointing.ra_deg:.4f} deg, "
                f"Dec={hit.pointing.dec_deg:.4f} deg, "
                f"err={hit.pointing.err_deg:.3f} deg{_sim_label(sim_alert)}"
            )
        detector_lines.append(
            f"- **{hit.name}:** n_events={n_label}; t_arrival={hit.t_arrival_utc}; {pointing}"
        )

    candidate_lines: list[str] = []
    bibcodes: list[str] = []
    for i, score in enumerate(candidates[:5], start=1):
        sim = _sim_label(score.simulated)
        dist = (
            f"{score.distance_kpc:.3f} kpc{sim}"
            if score.distance_kpc is not None
            else "distance unknown (not invented)"
        )
        candidate_lines.append(
            f"{i}. `{score.star_id}` ({score.class_}): "
            f"RA={score.ra_deg:.6f} deg, Dec={score.dec_deg:.6f} deg{sim}; "
            f"posterior={score.posterior:.4f}{sim}; {dist}; "
            f"ir_followup={score.ir_followup}"
        )
        for ev in score.lit.evidence:
            bib = (ev.bibcode or "").strip()
            if bib and bib not in bibcodes:
                bibcodes.append(bib)

    evidence_lines = (
        [f"- `{b}`" for b in bibcodes]
        if bibcodes
        else ["- (none on ranked rows; no bibcode → no claim)"]
    )

    parts = [
        "# DRAFT for human review",
        "",
        "Subject: BREAKOUT multimessenger localization and progenitor candidates "
        f"— {alert.alert_id}",
        "",
        "This text is a **DRAFT for human review**. BREAKOUT does not submit GCN "
        "Circulars. Simulated values are labeled `(simulated)`. Citations appear "
        "only with ADS bibcodes already present on CandidateScore evidence.",
        "",
        "## Alert",
        f"- **alert_id:** `{alert.alert_id}`",
        f"- **kind:** {alert.kind}",
        f"- **source:** {alert.source}",
        f"- **t0_utc:** {alert.t0_utc}{_sim_label(sim_alert)}",
        f"- **significance:** {alert.significance}{_sim_label(sim_alert)}",
        f"- **simulated:** {sim_alert}",
        "",
        "## Detectors",
        *(detector_lines or ["- (none)"]),
        "",
        "## Skymap",
        f"- **nside / ordering:** {skymap.nside} / {skymap.ordering} (ICRS)",
        f"- **90% credible area:** {skymap.credible_90_deg2:.2f} deg²{_sim_label(sim_map)}",
        f"- **peak:** RA {skymap.peak.ra_deg:.6f} deg, Dec {skymap.peak.dec_deg:.6f} deg"
        f"{_sim_label(sim_map)}",
        f"- **components:** {', '.join(skymap.components) or '(none)'}",
        f"- **simulated:** {sim_map}",
        "",
        "## Top candidates",
        *(candidate_lines or ["- (no candidates in the credible region)"]),
        "",
        "## Literature bibcodes cited",
        *evidence_lines,
        "",
        "## Notes",
        "- Triangulation uses light-travel time across Earth (at most about 42 ms).",
        "- Optical / IR follow-up drafts (LCOGT, HST, JWST) are prepared separately "
        "and also require human approval before any submission.",
        "",
    ]
    if top is not None:
        parts.extend(
            [
                f"Top-ranked progenitor candidate: `{top.star_id}` "
                f"(posterior={top.posterior:.4f}{_sim_label(top.simulated)}).",
                "",
            ]
        )
    parts.append(f"simulated={str(sim_alert or sim_map).lower()}")
    return "\n".join(parts) + "\n"
