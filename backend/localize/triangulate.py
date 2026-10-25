"""Pairwise timing rings from detector arrival differences.

Triangulation is light-travel time across Earth (at most about 42 ms).
For baseline vector d⃗ = r_b − r_a and Δt = t_a − t_b:

    cos θ = (c · Δt) / |d|

Each HEALPix pixel gets a Gaussian likelihood in cos(θ) around that value.
Maps use healpy NESTED ordering and always sum to 1.
"""

from __future__ import annotations

from typing import Any

import healpy as hp
import numpy as np
from astropy.constants import c as speed_of_light
from astropy.time import Time

from backend.config import HEALPIX_NSIDE, settings
from backend.ingest.snewpy_sim import detector_position_m
from backend.schemas import Alert


def _normalize(prob: np.ndarray) -> np.ndarray:
    """Return a copy that sums to 1 (uniform if empty)."""
    out = np.asarray(prob, dtype=float)
    total = float(out.sum())
    if total <= 0.0 or not np.isfinite(total):
        return np.full(out.shape, 1.0 / out.size, dtype=float)
    return out / total


def baseline_vector_m(det_a: str, det_b: str, t_utc: str | Time) -> np.ndarray:
    """Baseline vector d⃗ = r_b − r_a in meters (GCRS/ICRS at t_utc)."""
    obstime = t_utc if isinstance(t_utc, Time) else Time(t_utc, scale="utc")
    r_a = detector_position_m(det_a, obstime)
    r_b = detector_position_m(det_b, obstime)
    return r_b - r_a


def ring_map(
    det_a: str,
    det_b: str,
    dt_s: float,
    dt_err_s: float,
    t_utc: str | Time,
    *,
    nside: int | None = None,
) -> np.ndarray:
    """Build a NESTED HEALPix timing-ring probability map for one detector pair.

    Parameters
    ----------
    det_a, det_b:
        Detector names (WGS84 via DETECTOR_TABLE).
    dt_s:
        Arrival difference t_a − t_b in seconds.
    dt_err_s:
        Uncertainty on dt_s in seconds (combined timing error).
    t_utc:
        Epoch for EarthLocation → GCRS positions.
    nside:
        HEALPix Nside (default from config, 64).

    Returns
    -------
    np.ndarray
        Probability map (NESTED), sums to 1.
    """
    nside = int(nside if nside is not None else getattr(settings, "healpix_nside", HEALPIX_NSIDE))
    d_vec = baseline_vector_m(det_a, det_b, t_utc)
    d_norm = float(np.linalg.norm(d_vec))
    if d_norm <= 0.0:
        raise ValueError(f"Degenerate baseline between {det_a!r} and {det_b!r}")

    d_hat = d_vec / d_norm
    c_m_s = float(speed_of_light.value)
    cos_exp = float(np.clip(c_m_s * float(dt_s) / d_norm, -1.0, 1.0))
    # Propagate timing error into cos(θ) space; floor avoids zero-width rings.
    sigma_cos = max(c_m_s * float(dt_err_s) / d_norm, 1e-6)

    npix = hp.nside2npix(nside)
    pix = np.arange(npix)
    x, y, z = hp.pix2vec(nside, pix, nest=True)
    cos_obs = x * d_hat[0] + y * d_hat[1] + z * d_hat[2]
    log_l = -0.5 * ((cos_obs - cos_exp) / sigma_cos) ** 2
    # Stabilize before exp.
    log_l -= float(np.max(log_l))
    return _normalize(np.exp(log_l))


def pairwise_baselines(alert: Alert) -> list[dict[str, Any]]:
    """Return detector-pair baselines and Δt for an Alert.

    Each dict has det_a, det_b, baseline_m, dt_s (t_a−t_b), dt_err_s, dt_ms.
    """
    t0 = Time(alert.t0_utc, scale="utc")
    dets = list(alert.detectors)
    out: list[dict[str, Any]] = []
    for i, a in enumerate(dets):
        t_a = Time(a.t_arrival_utc, scale="utc")
        for b in dets[i + 1 :]:
            t_b = Time(b.t_arrival_utc, scale="utc")
            dt_s = float((t_a - t_b).to_value("s"))
            dt_err_s = float(np.hypot(a.t_err_ms, b.t_err_ms) * 1e-3)
            d_vec = baseline_vector_m(a.name, b.name, t0)
            out.append(
                {
                    "det_a": a.name,
                    "det_b": b.name,
                    "baseline_m": float(np.linalg.norm(d_vec)),
                    "dt_s": dt_s,
                    "dt_err_s": dt_err_s,
                    "dt_ms": dt_s * 1e3,
                }
            )
    return out


def timing_ring_map(
    alert: Alert,
    *,
    pair: tuple[str, str],
    nside: int | None = None,
) -> np.ndarray:
    """Build a NESTED HEALPix probability band for one detector pair on an Alert."""
    det_a, det_b = pair
    by_name = {d.name: d for d in alert.detectors}
    if det_a not in by_name or det_b not in by_name:
        raise KeyError(f"Pair {pair} not present in alert detectors")
    a = by_name[det_a]
    b = by_name[det_b]
    dt_s = float(
        (Time(a.t_arrival_utc, scale="utc") - Time(b.t_arrival_utc, scale="utc")).to_value("s")
    )
    dt_err_s = float(np.hypot(a.t_err_ms, b.t_err_ms) * 1e-3)
    return ring_map(det_a, det_b, dt_s, dt_err_s, alert.t0_utc, nside=nside)
