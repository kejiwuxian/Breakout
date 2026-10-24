"""Stars inside the credible region of a SkyMap."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import healpy as hp
import numpy as np

from backend.candidates.catalog import load_curated_stars
from backend.localize.fuse import position_in_credible_region
from backend.schemas import SkyMap


def _load_star_rows(star_table_path: Path) -> list[dict[str, Any]]:
    path = Path(star_table_path)
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"star JSON must be a list: {path}")
        return data
    if path.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(path).to_dict(orient="records")
    # Directory or missing → curated JSON.
    return load_curated_stars()


def filter_candidates(
    skymap: SkyMap,
    star_table_path: Path,
    *,
    credible_level: float = 0.9,
    prob: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Return catalog rows whose positions fall inside the credible region.

    Uses the fused HEALPix map at ``skymap.prob_path`` (NESTED). Does not
    invent star properties — only filters existing curated/catalog rows.
    """
    if prob is None:
        fits = Path(skymap.prob_path)
        if not fits.is_file():
            # Allow repo-relative paths.
            from backend.config import ROOT

            fits = ROOT / skymap.prob_path
        prob = np.asarray(hp.read_map(str(fits), nest=True))

    rows = _load_star_rows(Path(star_table_path))
    out: list[dict[str, Any]] = []
    for row in rows:
        ra = row.get("ra_deg")
        dec = row.get("dec_deg")
        if ra is None or dec is None:
            continue
        if position_in_credible_region(
            prob, float(ra), float(dec), level=credible_level
        ):
            out.append(dict(row))
    return out
