"""Stars inside the credible region of a SkyMap.

``candidates_in_region`` reads a pre-built star table (parquet) and returns
rows whose ICRS positions fall inside the HEALPix credible region (NESTED),
each annotated with ``p_sky``. When USE_CACHED_STREAM=True the trigger path
only reads the parquet — no SIMBAD/VizieR.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import healpy as hp
import numpy as np
import pandas as pd

from backend.candidates.catalog import STAR_TABLE_PATH, load_curated_stars, load_star_table
from backend.config import ROOT, settings
from backend.localize.fuse import credible_region_pixels, position_in_credible_region
from backend.schemas import SkyMap


def _resolve_prob(skymap: SkyMap, prob: np.ndarray | None) -> np.ndarray:
    if prob is not None:
        return np.asarray(prob, dtype=float)
    fits = Path(skymap.prob_path)
    if not fits.is_file():
        fits = ROOT / skymap.prob_path
    return np.asarray(hp.read_map(str(fits), nest=True), dtype=float)


def _p_sky_at(prob: np.ndarray, ra_deg: float, dec_deg: float) -> float:
    nside = hp.npix2nside(len(prob))
    ipix = int(hp.ang2pix(nside, ra_deg, dec_deg, nest=True, lonlat=True))
    return float(prob[ipix])


def _load_star_rows(star_table: Path | str | list[dict[str, Any]] | pd.DataFrame) -> list[dict[str, Any]]:
    """Load star rows from parquet/JSON/list. Never opens the network."""
    if isinstance(star_table, list):
        return [dict(r) for r in star_table]
    if isinstance(star_table, pd.DataFrame):
        records = star_table.to_dict(orient="records")
        out: list[dict[str, Any]] = []
        for record in records:
            sources = record.get("field_sources")
            if isinstance(sources, str):
                try:
                    record["field_sources"] = json.loads(sources)
                except json.JSONDecodeError:
                    record["field_sources"] = {}
            out.append(record)
        return out

    path = Path(star_table)
    if not path.is_absolute():
        candidate = ROOT / path
        if candidate.is_file():
            path = candidate
    if path.suffix == ".parquet" or path == STAR_TABLE_PATH:
        if not path.is_file():
            raise FileNotFoundError(
                f"star_table parquet not found: {path}. "
                "Run: python -m backend.candidates.catalog  (offline, no --network) "
                "or build_star_table(use_network=False)."
            )
        return load_star_table(path)
    if path.suffix == ".json" and path.is_file():
        return load_curated_stars(path)
    if path.is_file():
        return load_star_table(path)
    # Missing path → curated JSON fallback only when not forcing cached parquet.
    if settings.use_cached_stream:
        raise FileNotFoundError(
            f"USE_CACHED_STREAM=True requires star_table.parquet at {path}; "
            "refusing to fall back to live catalog queries."
        )
    return load_curated_stars()


def candidates_in_region(
    skymap: SkyMap,
    star_table: Path | str | list[dict[str, Any]] | pd.DataFrame = STAR_TABLE_PATH,
    level: float = 0.9,
    *,
    prob: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Return catalog stars inside the SkyMap credible region, each with ``p_sky``.

    Uses the fused HEALPix map at ``skymap.prob_path`` (NESTED ordering).
    Does not invent star properties — only filters existing catalog rows and
    attaches the map probability at each star's pixel.
    """
    prob_map = _resolve_prob(skymap, prob)
    rows = _load_star_rows(star_table)

    # Precompute credible-region membership as a set for O(1) lookups.
    in_region = set(credible_region_pixels(prob_map, level=level).tolist())
    nside = hp.npix2nside(len(prob_map))

    out: list[dict[str, Any]] = []
    for row in rows:
        ra = row.get("ra_deg")
        dec = row.get("dec_deg")
        if ra is None or dec is None:
            continue
        ra_f = float(ra)
        dec_f = float(dec)
        ipix = int(hp.ang2pix(nside, ra_f, dec_f, nest=True, lonlat=True))
        if ipix not in in_region:
            continue
        # Double-check via shared helper (same definition as localize/fuse).
        if not position_in_credible_region(prob_map, ra_f, dec_f, level=level):
            continue
        hit = dict(row)
        hit["p_sky"] = _p_sky_at(prob_map, ra_f, dec_f)
        # Propagate skymap simulated flag onto the candidate row for UI labeling.
        if skymap.simulated:
            hit["simulated"] = True
        out.append(hit)
    return out


def filter_candidates(
    skymap: SkyMap,
    star_table_path: Path,
    *,
    credible_level: float = 0.9,
    prob: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Alias for ``candidates_in_region`` (pipeline compatibility)."""
    return candidates_in_region(
        skymap,
        star_table_path,
        level=credible_level,
        prob=prob,
    )
