"""Stars inside the credible region of a SkyMap.

``filter_candidates`` / ``candidates_in_region`` consume a frozen v1 ``SkyMap``
and return catalog row dicts (with ``p_sky``) for ``literature.rerank``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import healpy as hp
import numpy as np

from backend.candidates.catalog import load_curated_stars
from backend.candidates.epoch_position import current_icrs
from backend.config import ROOT
from backend.localize.fuse import credible_region_pixels, position_in_credible_region
from backend.schemas import SkyMap


def _load_star_rows(star_table_path: Path) -> list[dict[str, Any]]:
    path = Path(star_table_path)
    if not path.is_absolute():
        candidate = ROOT / path
        if candidate.is_file():
            path = candidate
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


def _resolve_prob(skymap: SkyMap, prob: np.ndarray | None) -> np.ndarray:
    if prob is not None:
        return np.asarray(prob, dtype=float)
    fits = Path(skymap.prob_path)
    if not fits.is_file():
        fits = ROOT / skymap.prob_path
    if not fits.is_file():
        raise FileNotFoundError(
            f"SkyMap.prob_path not found: {skymap.prob_path} "
            "(contract: filter consumes SkyMap with a readable NESTED FITS map)"
        )
    return np.asarray(hp.read_map(str(fits), nest=True), dtype=float)


def _p_sky_at(prob: np.ndarray, ra_deg: float, dec_deg: float) -> float:
    nside = hp.npix2nside(len(prob))
    ipix = int(hp.ang2pix(nside, ra_deg, dec_deg, nest=True, lonlat=True))
    return float(prob[ipix])


def candidates_in_region(
    skymap: SkyMap,
    star_table: Path | str,
    level: float = 0.9,
    *,
    prob: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Return catalog stars inside the SkyMap credible region, each with ``p_sky``.

    Consumes frozen v1 ``SkyMap`` (NESTED HEALPix). Does not invent star
    properties — only filters existing catalog rows and attaches map probability.
    When ``skymap.simulated`` is true, output rows are labeled ``simulated=true``.
    """
    return filter_candidates(
        skymap,
        Path(star_table),
        credible_level=level,
        prob=prob,
    )


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
    if not isinstance(skymap, SkyMap):
        raise TypeError("filter consumes backend.schemas.SkyMap (v1)")

    prob_map = _resolve_prob(skymap, prob)
    in_region = set(credible_region_pixels(prob_map, level=credible_level).tolist())
    nside = hp.npix2nside(len(prob_map))

    rows = _load_star_rows(Path(star_table_path))
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("ra_deg") is None or row.get("dec_deg") is None:
            continue
        # Epoch-propagate when public PM fields exist; else catalog coords.
        try:
            ra_f, dec_f = current_icrs(row, at_utc=None)
        except ValueError:
            continue
        ipix = int(hp.ang2pix(nside, ra_f, dec_f, nest=True, lonlat=True))
        if ipix not in in_region:
            continue
        if not position_in_credible_region(prob_map, ra_f, dec_f, level=credible_level):
            continue
        hit = dict(row)
        hit["ra_deg"] = ra_f
        hit["dec_deg"] = dec_f
        hit["p_sky"] = _p_sky_at(prob_map, ra_f, dec_f)
        if skymap.simulated:
            hit["simulated"] = True
        out.append(hit)
    return out
