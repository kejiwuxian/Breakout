"""HST / JWST ToO request drafts (Markdown) for human review."""

from __future__ import annotations

from backend.schemas import CandidateScore, SkyMap


def draft_hst_too(candidate: CandidateScore, skymap: SkyMap) -> str:
    """Return an HST ToO request draft (Markdown). Not submitted automatically."""
    raise NotImplementedError("draft_hst_too is filled in a later prompt.")


def draft_jwst_too(candidate: CandidateScore, skymap: SkyMap) -> str:
    """Return a JWST ToO request draft (Markdown). Not submitted automatically.

    Note: JWST cannot observe very bright targets; the draft must say so when
    relevant. People approve before any submission.
    """
    raise NotImplementedError("draft_jwst_too is filled in a later prompt.")
