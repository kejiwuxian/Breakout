"""SNEWS-style joint χ² differential pointing for multi-detector timing.

``SNEWS_Coincidence_System`` only decides *when* an alert fires — it does not
build a skymap. SNEWS pointing lives in ``SNEWS2/snewpdag``:

* ``Chi2Calculator`` — (N−1) arrival deltas vs the best-timed reference
  detector, with the shared-reference covariance (well-conditioned).
* ``DiffPointing`` — same physics over an arbitrary pair list; the full
  pair clique is singular (only N−1 independent Δt), so we follow
  ``Chi2Calculator`` for the production map.

Independent timing rings treat correlated pairs as independent; the joint
χ² is statistically better. Adapted from SNEWS2/snewpdag (BSD-3-Clause):
https://github.com/SNEWS2/snewpdag

Detector bias is 0 (our Alert schema has no bias field).
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

# Skip detectors that cannot form a ≥100 km baseline with the reference
# (same floor as legacy pairwise rings in fuse).
_MIN_BASELINE_M = 1.0e5


def _normalize(prob: np.ndarray) -> np.ndarray:
    out = np.asarray(prob, dtype=float)
    total = float(out.sum())
    if total <= 0.0 or not np.isfinite(total):
        return np.full(out.shape, 1.0 / out.size, dtype=float)
    return out / total


def _arrival_s(det: Any) -> float:
    return float(Time(det.t_arrival_utc, scale="utc").unix)


def _sigma_s(det: Any) -> float:
    return float(det.t_err_ms) * 1e-3


def select_reference(alert: Alert) -> tuple[Any, list[Any]]:
    """Pick the smallest-σ detector as reference; return (ref, others).

    Matches snewpdag ``Chi2Calculator.get_time_dicts``.
    """
    dets = list(alert.detectors)
    if len(dets) < 2:
        raise ValueError("Need ≥2 detectors for DiffPointing")
    ref = min(dets, key=_sigma_s)
    others = [d for d in dets if d.name != ref.name]
    return ref, others


def usable_others(
    alert: Alert,
    *,
    min_baseline_m: float = _MIN_BASELINE_M,
) -> tuple[Any, list[Any]]:
    """Reference plus others with a long enough baseline to the reference."""
    ref, others = select_reference(alert)
    t0 = Time(alert.t0_utc, scale="utc")
    r0 = detector_position_m(ref.name, t0)
    kept: list[Any] = []
    for d in others:
        r = detector_position_m(d.name, t0)
        if float(np.linalg.norm(r - r0)) >= min_baseline_m:
            kept.append(d)
    return ref, kept


def precision_matrix(ref_sigma: float, other_sigmas: list[float]) -> np.ndarray:
    """Inverse covariance for (t_i − t_ref) sharing the reference detector.

    ``V_ii = σ_ref² + σ_i²``, ``V_ij = σ_ref²`` (i≠j) — snewpdag Chi2Calculator.
    """
    n = len(other_sigmas)
    if n < 1:
        raise ValueError("Need ≥1 non-reference detector")
    v = np.full((n, n), float(ref_sigma) ** 2, dtype=float)
    for i, s in enumerate(other_sigmas):
        v[i, i] = float(ref_sigma) ** 2 + float(s) ** 2
    return np.linalg.inv(v)


def weight_matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    """Test helper: inverse cov for synthetic DiffPointing-style pair rows."""
    n = len(rows)
    v = np.zeros((n, n), dtype=float)
    for i, r1 in enumerate(rows):
        for j, r2 in enumerate(rows):
            if i == j:
                v[i, j] = float(r1["var"])
            elif r1["det_a"] == r2["det_a"]:
                v[i, j] = float(r1["dsig1"]) * float(r2["dsig1"])
            elif r1["det_b"] == r2["det_b"]:
                v[i, j] = float(r1["dsig2"]) * float(r2["dsig2"])
            elif r1["det_a"] == r2["det_b"]:
                v[i, j] = float(r1["dsig1"]) * float(r2["dsig2"])
            elif r1["det_b"] == r2["det_a"]:
                v[i, j] = float(r1["dsig2"]) * float(r2["dsig1"])
    return np.linalg.inv(v)


def chi2_map(
    alert: Alert,
    *,
    nside: int | None = None,
    min_baseline_m: float = _MIN_BASELINE_M,
) -> tuple[np.ndarray, int]:
    """NESTED HEALPix χ² map (min-subtracted) and ndof = n_other − 0 → sky DOF 2.

    Returns
    -------
    chi2 :
        Non-negative map with minimum 0 (snewpdag convention).
    ndof :
        2 (sky direction), matching DiffPointing / Chi2CL usage for maps.
    """
    nside = int(nside if nside is not None else getattr(settings, "healpix_nside", HEALPIX_NSIDE))
    ref, others = usable_others(alert, min_baseline_m=min_baseline_m)
    if len(others) < 1:
        raise ValueError("SNEWS DiffPointing needs ≥1 long baseline to the reference")

    t0 = Time(alert.t0_utc, scale="utc")
    r_ref = np.asarray(detector_position_m(ref.name, t0), dtype=float)
    t_ref = _arrival_s(ref)
    sig_ref = _sigma_s(ref)

    ddt = np.zeros(len(others), dtype=float)
    dp = np.zeros((len(others), 3), dtype=float)  # (r_i − r_ref) / c
    sigmas: list[float] = []
    c_m_s = float(speed_of_light.value)
    for i, det in enumerate(others):
        r_i = np.asarray(detector_position_m(det.name, t0), dtype=float)
        # residual = (t_i − t_ref) + (r_i − r_ref)·n̂ / c
        ddt[i] = (_arrival_s(det) - t_ref) - 0.0  # bias=0
        dp[i] = (r_i - r_ref) / c_m_s
        sigmas.append(_sigma_s(det))

    w = precision_matrix(sig_ref, sigmas)

    npix = hp.nside2npix(nside)
    directions = np.asarray(hp.pix2vec(nside, np.arange(npix), nest=True), dtype=float)
    # directions: (3, npix); geom: (npix, n_other)
    geom = directions.T @ dp.T
    resid = geom + ddt
    wr = resid @ w
    chi2 = np.einsum("ij,ij->i", wr, resid)
    chi2 = np.asarray(chi2, dtype=float)
    chi2 -= float(np.min(chi2))
    return chi2, 2


def prob_map(
    alert: Alert,
    *,
    nside: int | None = None,
    min_baseline_m: float = _MIN_BASELINE_M,
) -> np.ndarray:
    """Convert joint χ² into a NESTED probability map (sums to 1)."""
    chi2, _ndof = chi2_map(alert, nside=nside, min_baseline_m=min_baseline_m)
    log_l = -0.5 * chi2
    log_l -= float(np.max(log_l))
    return _normalize(np.exp(log_l))


def has_independent_arrival_times(alert: Alert) -> bool:
    """False when the notice explicitly lacks per-detector timing (classic SNEWS).

    SNEWS2 JSON coincidence notices carry ``event_times_utc`` (may be equal
    within ms). Classic GCN text shares one EVENT_TIME across EXPT — those
    set ``raw.has_timing_deltas=False`` so we do not invent Δt geometry.
    """
    raw = alert.raw if isinstance(alert.raw, dict) else {}
    if raw.get("has_timing_deltas") is False:
        return False
    return len(alert.detectors) >= 2


def can_use_diffpointing(alert: Alert, *, min_baseline_m: float = _MIN_BASELINE_M) -> bool:
    """True when ≥2 long baselines to the reference exist (joint χ² beats a ring)."""
    if not has_independent_arrival_times(alert):
        return False
    try:
        _ref, others = usable_others(alert, min_baseline_m=min_baseline_m)
    except ValueError:
        return False
    return len(others) >= 2


def usable_pairs(alert: Alert, *, min_baseline_m: float = _MIN_BASELINE_M) -> list[dict[str, Any]]:
    """Legacy helper for tests: reference–other pairs used in the χ²."""
    ref, others = usable_others(alert, min_baseline_m=min_baseline_m)
    t0 = Time(alert.t0_utc, scale="utc")
    r0 = detector_position_m(ref.name, t0)
    out: list[dict[str, Any]] = []
    for d in others:
        r = detector_position_m(d.name, t0)
        dt = _arrival_s(ref) - _arrival_s(d)  # t_ref − t_other (pair order)
        out.append(
            {
                "det_a": ref.name,
                "det_b": d.name,
                "baseline_m": float(np.linalg.norm(r - r0)),
                "dt_s": dt,
                "dt_err_s": float(np.hypot(_sigma_s(ref), _sigma_s(d))),
            }
        )
    return out
