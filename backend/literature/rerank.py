"""LIVE: lookup + rerank candidates; no LLM call.

Reads the offline index and returns CandidateScore rows conforming to v1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.literature.build_index import INDEX_PATH
from backend.schemas import CandidateScore, SkyMap


def rerank(
    candidates: list[dict[str, Any]],
    skymap: SkyMap,
    *,
    index_path: Path = INDEX_PATH,
    watchlist: set[str] | None = None,
) -> list[CandidateScore]:
    """Lookup literature scores and compute posteriors for candidates.

    Ranking: P ∝ p_sky × w_class × w_lit × w_watch. No network / LLM.
    """
    raise NotImplementedError("rerank is filled in a later prompt.")
