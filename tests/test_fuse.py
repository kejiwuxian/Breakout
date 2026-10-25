"""Tests for backend.localize.fuse."""

from __future__ import annotations

from pathlib import Path

import healpy as hp
import numpy as np
import pytest

from backend.ingest.snewpy_sim import simulate_burst
from backend.localize.fuse import (
    build_component_maps,
    fuse,
    fuse_maps,
    position_in_credible_region,
)
from backend.schemas import SkyMap


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


def test_fuse_map_sums_to_one_and_writes_artifacts(tmp_path: Path) -> None:
    alert = _burst_alert()
    assert alert.simulated is True
    skymap = fuse(alert, nside=NSIDE, out_root=tmp_path)
    assert isinstance(skymap, SkyMap)
    assert skymap.ordering == "NESTED"
    assert skymap.frame == "ICRS"
    assert skymap.simulated is True
    assert skymap.nside == NSIDE
    fits = tmp_path / alert.alert_id / "skymap.fits"
    png = tmp_path / alert.alert_id / "skymap.png"
    assert fits.is_file()
    assert png.is_file()
    prob, _header = hp.read_map(str(fits), nest=True, h=True)
    assert float(np.asarray(prob).sum()) == pytest.approx(1.0, rel=1e-6, abs=1e-6)


def test_true_position_inside_90_percent_region(tmp_path: Path) -> None:
    alert = _burst_alert()
    skymap = fuse(alert, nside=NSIDE, out_root=tmp_path)
    prob = hp.read_map(str(tmp_path / alert.alert_id / "skymap.fits"), nest=True)
    assert position_in_credible_region(np.asarray(prob), TRUE_RA, TRUE_DEC, level=0.9)


def test_pointing_shrinks_credible_region(tmp_path: Path) -> None:
    alert = _burst_alert()
    maps_timing, comps_timing = build_component_maps(
        alert, nside=NSIDE, include_pointing=False
    )
    maps_full, comps_full = build_component_maps(
        alert, nside=NSIDE, include_pointing=True
    )
    assert "superk_pointing" not in comps_timing
    assert "superk_pointing" in comps_full

    timing_only = fuse_maps(
        maps_timing,
        alert=alert,
        components=comps_timing,
        out_dir=tmp_path / "timing_only",
        nside=NSIDE,
    )
    with_pointing = fuse_maps(
        maps_full,
        alert=alert,
        components=comps_full,
        out_dir=tmp_path / "with_pointing",
        nside=NSIDE,
    )
    assert with_pointing.credible_90_deg2 < timing_only.credible_90_deg2
