"""GCN Circular draft for human review (never auto-submitted)."""

from __future__ import annotations

from backend.schemas import Alert, CandidateScore, SkyMap


def draft_circular(
    alert: Alert,
    skymap: SkyMap,
    candidates: list[CandidateScore],
) -> str:
    """Return a GCN Circular draft (Markdown) marked for human review.

    GCN Circulars are written and submitted by people; BREAKOUT only drafts.
    Label every simulated number as simulated.
    """
    raise NotImplementedError("draft_circular is filled in a later prompt.")
