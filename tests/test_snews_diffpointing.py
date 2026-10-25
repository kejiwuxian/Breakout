"""SNEWS DiffPointing joint-χ² localization (ported from snewpdag)."""

from __future__ import annotations

from pathlib import Path

import healpy as hp
import numpy as np
import pytest

from backend.ingest.snewpy_sim import simulate_burst
from backend.localize.fuse import (
    build_component_maps,
    fuse,
    position_in_credible_region,
)
from backend.localize.snews_diffpointing import (
    can_use_diffpointing,
    chi2_map,
    prob_map,
    usable_pairs,
    weight_matrix,
)
T0 = "2026-10-24T21:46:00"
NSIDE = 64
TRUE_RA = 88.7929
TRUE_DEC = 7.4071


def _fake_counts(distance_kpc: float, model: str, detectors) -> dict[str, int]:
    return {d: 100 for d in detectors}


def _burst_alert():
    return simulate_burst(
        TRUE_RA,
        TRUE_DEC,
        0.2,
        "Nakazato_2013",
        T0,
        event_count_fn=_fake_counts,
        detectors=["Super-K", "IceCube", "SNO+", "JUNO"],
        pointing_err_deg=3.0,
    )[0]


def test_usable_pairs_are_reference_baselines() -> None:
    alert = _burst_alert()
    usable = usable_pairs(alert)
    assert len(usable) >= 2
    assert all(p["baseline_m"] >= 1.0e5 for p in usable)
    # All pairs share one reference detector.
    refs = {p["det_a"] for p in usable}
    assert len(refs) == 1


def test_weight_matrix_positive_definite() -> None:
    alert = _burst_alert()
    # Two synthetic correlated pairs sharing Super-K.
    rows = [
        {
            "det_a": "Super-K",
            "det_b": "IceCube",
            "dt": 0.0,
            "bias": 0.0,
            "var": 1e-6,
            "dsig1": 1e-3,
            "dsig2": -1e-3,
            "p1": np.zeros(3),
            "p2": np.zeros(3),
        },
        {
            "det_a": "Super-K",
            "det_b": "SNO+",
            "dt": 0.0,
            "bias": 0.0,
            "var": 2e-6,
            "dsig1": 1e-3,
            "dsig2": -2e-3,
            "p1": np.zeros(3),
            "p2": np.zeros(3),
        },
    ]
    w = weight_matrix(rows)
    assert w.shape == (2, 2)
    assert np.allclose(w, w.T, atol=1e-12)
    assert float(np.min(np.linalg.eigvalsh(w))) > 0.0
    # Off-diagonal must be non-zero (shared Super-K).
    assert abs(float(w[0, 1])) > 0.0
    _ = alert  # ensure alert builder stays exercised if sigmas change


def test_prob_map_sums_to_one_and_covers_truth() -> None:
    alert = _burst_alert()
    assert can_use_diffpointing(alert)
    prob = prob_map(alert, nside=NSIDE)
    assert float(prob.sum()) == pytest.approx(1.0, rel=1e-6, abs=1e-6)
    assert position_in_credible_region(prob, TRUE_RA, TRUE_DEC, level=0.9)


def test_chi2_min_is_zero() -> None:
    alert = _burst_alert()
    chi2, ndof = chi2_map(alert, nside=NSIDE)
    assert ndof == 2
    assert float(np.min(chi2)) == pytest.approx(0.0, abs=1e-12)


def test_fuse_prefers_snews_component(tmp_path: Path) -> None:
    alert = _burst_alert()
    maps, comps = build_component_maps(alert, nside=NSIDE, include_pointing=False)
    assert comps == ["timing:snews_diffpointing"]
    assert len(maps) == 1

    skymap = fuse(alert, nside=NSIDE, out_root=tmp_path, include_pointing=False)
    assert "timing:snews_diffpointing" in skymap.components
    prob = hp.read_map(str(tmp_path / alert.alert_id / "skymap.fits"), nest=True)
    assert position_in_credible_region(np.asarray(prob), TRUE_RA, TRUE_DEC, level=0.9)


def test_legacy_rings_still_available(tmp_path: Path) -> None:
    alert = _burst_alert()
    maps, comps = build_component_maps(
        alert,
        nside=NSIDE,
        include_pointing=False,
        use_snews_diffpointing=False,
    )
    assert all(c.startswith("timing:") and "snews" not in c for c in comps)
    assert len(maps) >= 2
    skymap = fuse(
        alert,
        nside=NSIDE,
        out_root=tmp_path,
        include_pointing=False,
        use_snews_diffpointing=False,
    )
    assert "timing:snews_diffpointing" not in skymap.components
