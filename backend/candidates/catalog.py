"""Pull RSG / BSG / WR / LBV lists (astroquery).

Offline demos use data/stars/curated_stars.json and star_table.parquet;
live catalog queries require network and must not run on the trigger path
when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.config import ROOT

STARS_DIR = ROOT / "data" / "stars"


def load_curated_stars(path: Path | None = None) -> list[dict[str, Any]]:
    """Load Vincent's curated real stars JSON (citations required)."""
    raise NotImplementedError("load_curated_stars is filled in a later prompt.")


def build_star_table(*, use_network: bool = False) -> Path:
    """Build star_table.parquet from curated stars (+ optional SIMBAD/VizieR).

    When use_network is False, only local curated data is used.
    """
    raise NotImplementedError("build_star_table is filled in a later prompt.")
