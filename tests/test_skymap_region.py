"""Credible-region outline + focus PNG + API."""

from __future__ import annotations

from pathlib import Path

import healpy as hp
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.ingest.snewpy_sim import simulate_burst
from backend.localize.fuse import fuse
from backend.localize.region import (
    PEAK_RING_AOI_RADIUS_DEG,
    build_region_payload,
    credible_region_ellipse,
    credible_region_outline,
    ensure_region_artifacts,
    focus_fov_deg,
    outer_aoi_radius_deg,
)


T0 = "2026-10-24T21:46:00"
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


def test_outline_is_closed_and_near_true_position(tmp_path: Path) -> None:
    alert = _burst_alert()
    skymap = fuse(alert, nside=64, out_root=tmp_path)
    fits = tmp_path / alert.alert_id / "skymap.fits"
    prob = np.asarray(hp.read_map(str(fits), nest=True), dtype=float)
    ell = credible_region_ellipse(prob, level=0.9)
    assert ell["semi_major_deg"] >= ell["semi_minor_deg"] > 0
    assert abs(((ell["ra_deg"] - TRUE_RA + 180) % 360) - 180) < 15.0
    assert abs(ell["dec_deg"] - TRUE_DEC) < 15.0
    ring = credible_region_outline(prob, level=0.9)
    assert len(ring) >= 4
    assert ring[0] == ring[-1]
    # Smooth oval — successive points should not jump wildly.
    steps = [
        abs(((ring[i][0] - ring[i - 1][0] + 180) % 360) - 180)
        + abs(ring[i][1] - ring[i - 1][1])
        for i in range(1, len(ring))
    ]
    assert max(steps) < 25.0
    payload = build_region_payload(prob, alert_id=alert.alert_id, simulated=True)
    assert payload["shape"] == "ellipse"
    assert payload["render"] == "svg_v2"
    assert "ellipse" in payload
    assert payload["prob_cells"]
    # Full BSC5 field lives on /api/sky/base; region keeps the key empty.
    assert payload["field_stars"] == []
    assert payload.get("galactic_plane") == []
    assert payload.get("n_field_stars_base", 0) >= 1000
    assert payload["nested_ellipses"]
    assert payload["fov_deg"] == pytest.approx(focus_fov_deg(payload["ellipse"]))
    assert "outer_aoi_radius_deg" in payload
    assert payload["outer_aoi_radius_deg"] == pytest.approx(
        outer_aoi_radius_deg(
            payload["ellipse"], nested_ellipses=payload["nested_ellipses"]
        )
    )
    assert (tmp_path / alert.alert_id / "region.json").is_file()
    assert (tmp_path / alert.alert_id / "skymap_focus.png").is_file()
    assert skymap.peak.ra_deg == pytest.approx(payload["peak"]["ra_deg"], abs=1e-6)


def test_outer_aoi_radius_tiny_ellipse_uses_peak_ring() -> None:
    tiny = {
        "ra_deg": 77.4,
        "dec_deg": 5.7,
        "semi_major_deg": 1.6,
        "semi_minor_deg": 1.5,
        "pa_deg": 0.0,
        "area_deg2": 7.5,
    }
    nested = [
        {"level": 0.5, "ellipse": {**tiny, "semi_major_deg": 1.0, "semi_minor_deg": 0.7}},
        {"level": 0.9, "ellipse": tiny},
    ]
    assert outer_aoi_radius_deg(tiny, nested_ellipses=nested) == pytest.approx(
        PEAK_RING_AOI_RADIUS_DEG
    )


def test_outer_aoi_radius_large_ellipse_keeps_semi_major() -> None:
    large = {
        "ra_deg": 88.0,
        "dec_deg": 7.0,
        "semi_major_deg": 18.0,
        "semi_minor_deg": 10.0,
        "pa_deg": 30.0,
        "area_deg2": 500.0,
    }
    assert outer_aoi_radius_deg(large) == pytest.approx(18.0)


def test_ensure_region_and_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app as app_mod

    alert = _burst_alert()
    fuse(alert, nside=32, out_root=tmp_path)
    monkeypatch.setattr(app_mod, "_out_root", tmp_path)
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")

    payload = ensure_region_artifacts(
        tmp_path / alert.alert_id, alert_id=alert.alert_id, simulated=True
    )
    assert payload["outline"]
    assert payload["simulated"] is True

    with TestClient(app_mod.app) as client:
        r = client.get(f"/api/skymap/{alert.alert_id}/region")
        assert r.status_code == 200
        body = r.json()
        assert body["alert_id"] == alert.alert_id
        assert body["shape"] == "ellipse"
        assert body["render"] == "svg_v2"
        assert body["ellipse"]["semi_major_deg"] >= body["ellipse"]["semi_minor_deg"]
        assert len(body["outline"]) >= 4
        assert body["prob_cells"]
        assert body["field_stars"] == []
        assert body.get("galactic_plane") == []
        base = client.get("/api/sky/base")
        assert base.status_code == 200
        base_body = base.json()
        field = base_body["field_stars"]
        assert base_body.get("galactic_plane") == []
        assert base_body.get("render") == "svg_v2"
        assert len(field) >= 1000
        assert all("ra_deg" in s and "dec_deg" in s for s in field[:20])
        f = client.get(f"/api/skymap/{alert.alert_id}/focus.png")
        assert f.status_code == 200
        assert f.headers["content-type"].startswith("image/png")
        assert len(f.content) > 1000
