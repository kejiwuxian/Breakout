"""Stars inside the outer AOI of a SkyMap.

``filter_candidates`` / ``candidates_in_region`` consume a frozen v1 ``SkyMap``
and return catalog row dicts (with ``p_sky``) for ``literature.rerank``.

Membership is the union of the HEALPix credible region and a circular outer
AOI aperture (larger of credible/nested ellipse semi-major vs the IceCube-scale
peak-ring floor). That way tiny localizations still rank every star under the
visual outer mark, not only the inner ellipse.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import healpy as hp
import numpy as np

from backend.candidates.catalog import load_curated_stars
from backend.candidates.epoch_position import current_icrs
from backend.config import ROOT
from backend.localize.fuse import credible_region_pixels, peak_ra_dec, position_in_credible_region
from backend.localize.region import (
    credible_region_ellipse,
    outer_aoi_radius_deg,
    peak_ring_drawn,
)
from backend.schemas import SkyMap


def _angsep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Approximate great-circle separation in degrees."""
    dra = (ra1 - ra2) * math.cos(math.radians(0.5 * (dec1 + dec2)))
    ddec = dec1 - dec2
    return math.hypot(dra, ddec)


def _load_star_rows(
    star_table_path: Path | str | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(star_table_path, list):
        return [r for r in star_table_path if isinstance(r, dict)]
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
    star_table: Path | str | list[dict[str, Any]],
    level: float = 0.9,
    *,
    prob: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Return catalog stars inside the SkyMap outer AOI, each with ``p_sky``.

    Consumes frozen v1 ``SkyMap`` (NESTED HEALPix). Does not invent star
    properties — only filters existing catalog rows and attaches map probability.
    When ``skymap.simulated`` is true, output rows are labeled ``simulated=true``.
    """
    return filter_candidates(
        skymap,
        star_table,
        credible_level=level,
        prob=prob,
    )


def filter_candidates(
    skymap: SkyMap,
    star_table_path: Path | str | list[dict[str, Any]],
    *,
    credible_level: float = 0.9,
    prob: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Return catalog rows inside the outer AOI (credible ∪ peak-ring aperture).

    Uses the fused HEALPix map at ``skymap.prob_path`` (NESTED). Does not
    invent star properties — only filters existing curated/catalog rows.
    For IceCube-scale ellipses the outer mark is the peak ring, so membership
    expands to ``outer_aoi_radius_deg`` around the peak.
    """
    if not isinstance(skymap, SkyMap):
        raise TypeError("filter consumes backend.schemas.SkyMap (v1)")

    prob_map = _resolve_prob(skymap, prob)
    in_region = set(credible_region_pixels(prob_map, level=credible_level).tolist())
    nside = hp.npix2nside(len(prob_map))

    ellipse = credible_region_ellipse(prob_map, level=credible_level)
    nested = []
    for lvl in (0.5, credible_level):
        nested.append(
            {
                "level": lvl,
                "ellipse": credible_region_ellipse(prob_map, level=lvl),
            }
        )
    outer_r = outer_aoi_radius_deg(ellipse, nested_ellipses=nested)
    expand_peak_ring = peak_ring_drawn(ellipse) and outer_r > float(
        ellipse.get("semi_major_deg") or 0.0
    )
    peak = peak_ra_dec(prob_map)

    rows = _load_star_rows(star_table_path)
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
        in_cred = ipix in in_region and position_in_credible_region(
            prob_map, ra_f, dec_f, level=credible_level
        )
        in_outer_ring = False
        if expand_peak_ring:
            in_outer_ring = (
                _angsep_deg(ra_f, dec_f, float(peak.ra_deg), float(peak.dec_deg))
                <= outer_r
            )
        if not (in_cred or in_outer_ring):
            continue
        hit = dict(row)
        hit["ra_deg"] = ra_f
        hit["dec_deg"] = dec_f
        hit["p_sky"] = _p_sky_at(prob_map, ra_f, dec_f)
        if skymap.simulated:
            hit["simulated"] = True
        out.append(hit)
    return out
