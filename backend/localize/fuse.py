"""Product of maps, normalize, credible region → SkyMap."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.schemas import Alert, SkyMap


def fuse_maps(
    maps: list[np.ndarray],
    *,
    alert: Alert,
    components: list[str],
    out_dir: Path,
    nside: int = 64,
) -> SkyMap:
    """Multiply component maps, normalize to sum 1, write FITS, return SkyMap.

    Writes data/run/<alert_id>/skymap.fits (and optional Mollweide PNG later).
    """
    raise NotImplementedError("fuse_maps is filled in a later prompt.")


def credible_region_area_deg2(prob: np.ndarray, *, level: float = 0.9) -> float:
    """Return the sky area (deg²) of the credible region at the given level."""
    raise NotImplementedError("credible_region_area_deg2 is filled in a later prompt.")
