"""Pull RSG / BSG / WR / LBV lists (astroquery).

Offline demos use data/stars/curated_stars.json and star_table.parquet;
live catalog queries require network and must not run on the trigger path
when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import ROOT

STARS_DIR = ROOT / "data" / "stars"
CURATED_PATH = STARS_DIR / "curated_stars.json"
STAR_TABLE_PATH = STARS_DIR / "star_table.parquet"


def load_curated_stars(path: Path | None = None) -> list[dict[str, Any]]:
    """Load Vincent's curated real stars JSON (citations required for claims)."""
    target = Path(path) if path is not None else CURATED_PATH
    if not target.is_file():
        return []
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"curated_stars must be a JSON list: {target}")
    return data


def build_star_table(*, use_network: bool = False) -> Path:
    """Build star_table.parquet from curated stars (+ optional SIMBAD/VizieR).

    When use_network is False, only local curated data is used. Writes a minimal
    parquet if pandas/pyarrow are available; otherwise returns the JSON path.
    """
    stars = load_curated_stars()
    STAR_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if use_network:
        raise RuntimeError(
            "build_star_table(use_network=True) is disabled on the trigger path; "
            "use curated stars when USE_CACHED_STREAM=True."
        )
    try:
        import pandas as pd

        pd.DataFrame(stars).to_parquet(STAR_TABLE_PATH, index=False)
        return STAR_TABLE_PATH
    except Exception:
        # Offline fallback: filter accepts JSON via load_curated_stars.
        return CURATED_PATH
