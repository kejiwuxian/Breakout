"""Tests for backend.localize.triangulate."""

from __future__ import annotations

import healpy as hp
import numpy as np
import pytest
from astropy.constants import c as speed_of_light
from astropy.time import Time

from backend.ingest.snewpy_sim import pair_delay_s, simulate_burst
from backend.localize.triangulate import baseline_vector_m, ring_map, timing_ring_map


T0 = "2026-10-24T21:46:00"
NSIDE = 64


def _fake_counts(distance_kpc: float, model: str, detectors) -> dict[str, int]:
    return {d: 10 for d in detectors}


def test_ring_map_sums_to_one() -> None:
    # Use a physical Super-K / IceCube delay from geometry at RA=88.8, Dec=7.4.
    dt = pair_delay_s(88.8, 7.4, "Super-K", "IceCube", Time(T0, scale="utc"))
    prob = ring_map("Super-K", "IceCube", dt, 0.003, T0, nside=NSIDE)
    assert prob.shape == (hp.nside2npix(NSIDE),)
    assert float(prob.sum()) == pytest.approx(1.0, rel=1e-12, abs=1e-12)
    assert np.all(prob >= 0.0)


def test_ring_map_peaks_near_true_cos_theta() -> None:
    ra, dec = 88.7929, 7.4071
    obstime = Time(T0, scale="utc")
    dt = pair_delay_s(ra, dec, "Super-K", "IceCube", obstime)
    d_vec = baseline_vector_m("Super-K", "IceCube", T0)
    d_hat = d_vec / np.linalg.norm(d_vec)
    cos_exp = float(np.clip(speed_of_light.value * dt / np.linalg.norm(d_vec), -1.0, 1.0))

    prob = ring_map("Super-K", "IceCube", dt, 0.002, T0, nside=NSIDE)
    true_pix = hp.ang2pix(NSIDE, ra, dec, nest=True, lonlat=True)
    # True pixel should be among the high-likelihood ring (top 5%).
    thresh = np.quantile(prob, 0.95)
    assert prob[true_pix] >= thresh * 0.5  # on the ring, not necessarily the single max

    x, y, z = hp.pix2vec(NSIDE, int(np.argmax(prob)), nest=True)
    cos_peak = x * d_hat[0] + y * d_hat[1] + z * d_hat[2]
    assert cos_peak == pytest.approx(cos_exp, abs=0.05)


def test_timing_ring_map_from_snewpy_alert() -> None:
    alerts = simulate_burst(
        88.7929,
        7.4071,
        0.2,
        "Nakazato_2013",
        T0,
        event_count_fn=_fake_counts,
        detectors=["Super-K", "IceCube", "SNO+", "JUNO"],
    )
    alert = alerts[0]
    assert alert.simulated is True
    prob = timing_ring_map(alert, pair=("Super-K", "IceCube"), nside=NSIDE)
    assert float(prob.sum()) == pytest.approx(1.0, rel=1e-12, abs=1e-12)
