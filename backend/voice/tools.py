"""Judge Q&A function tools, read-only over our data.

Tools: get_top_candidates, get_skymap_summary, get_breakout_countdown.
Answers must name the bibcode for every claim and say simulated when needed.
"""

from __future__ import annotations

from typing import Any


def get_top_candidates(*, limit: int = 5) -> dict[str, Any]:
    """Return top CandidateScore rows for the active alert (read-only)."""
    raise NotImplementedError("get_top_candidates is filled in a later prompt.")


def get_skymap_summary() -> dict[str, Any]:
    """Return a summary of the active SkyMap (read-only)."""
    raise NotImplementedError("get_skymap_summary is filled in a later prompt.")


def get_breakout_countdown(*, star_id: str | None = None) -> dict[str, Any]:
    """Return breakout countdown for the top or named candidate (read-only)."""
    raise NotImplementedError("get_breakout_countdown is filled in a later prompt.")


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_top_candidates",
        "description": "Return top ranked candidates with bibcodes and simulated flags.",
    },
    {
        "type": "function",
        "name": "get_skymap_summary",
        "description": "Return fused sky map peak and credible region summary.",
    },
    {
        "type": "function",
        "name": "get_breakout_countdown",
        "description": "Return breakout class window and countdown for a candidate.",
    },
]
