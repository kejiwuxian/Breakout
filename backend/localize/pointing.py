"""Super-K directional estimate as a HEALPix map.

Gaussian on the sphere centered on (ra_deg, dec_deg) with width err_deg.
Maps use healpy NESTED ordering and always sum to 1.
"""

from __future__ import annotations

import healpy as hp
import numpy as np

from backend.config import HEALPIX_NSIDE, settings
from backend.schemas import Alert, Pointing


def _normalize(prob: np.ndarray) -> np.ndarray:
    out = np.asarray(prob, dtype=float)
    total = float(out.sum())
    if total <= 0.0 or not np.isfinite(total):
        return np.full(out.shape, 1.0 / out.size, dtype=float)
    return out / total


def pointing_map(
    ra_deg: float,
    dec_deg: float,
    err_deg: float,
    *,
    nside: int | None = None,
) -> np.ndarray:
    """Gaussian-on-sphere HEALPix map for a directional estimate (NESTED, sums to 1).

    Parameters
    ----------
    ra_deg, dec_deg:
        Center in ICRS degrees.
    err_deg:
        1-σ angular width in degrees (Super-K few-degree scale when simulated).
    """
    nside = int(nside if nside is not None else getattr(settings, "healpix_nside", HEALPIX_NSIDE))
    sigma = max(float(err_deg), 1e-6) * np.pi / 180.0
    center = np.asarray(hp.ang2vec(float(ra_deg), float(dec_deg), lonlat=True), dtype=float)
    npix = hp.nside2npix(nside)
    pix = np.arange(npix)
    x, y, z = hp.pix2vec(nside, pix, nest=True)
    cosang = np.clip(x * center[0] + y * center[1] + z * center[2], -1.0, 1.0)
    ang = np.arccos(cosang)
    log_l = -0.5 * (ang / sigma) ** 2
    log_l -= float(np.max(log_l))
    return _normalize(np.exp(log_l))


def pointing_map_from_pointing(pointing: Pointing, *, nside: int | None = None) -> np.ndarray:
    """Wrapper accepting a Pointing schema object."""
    return pointing_map(pointing.ra_deg, pointing.dec_deg, pointing.err_deg, nside=nside)


def extract_superk_pointing(alert: Alert) -> Pointing | None:
    """Return the Super-K pointing from an Alert, if present."""
    for det in alert.detectors:
        if det.name == "Super-K" and det.pointing is not None:
            return det.pointing
    return None
