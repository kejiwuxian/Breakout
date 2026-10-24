"""Stars inside the credible region of a SkyMap."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.schemas import SkyMap


def filter_candidates(
    skymap: SkyMap,
    star_table_path: Path,
    *,
    credible_level: float = 0.9,
) -> list[dict[str, Any]]:
    """Return catalog rows whose positions fall inside the credible region."""
    raise NotImplementedError("filter_candidates is filled in a later prompt.")
