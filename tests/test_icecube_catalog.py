"""Real-data validation against the official IceCube alert catalog."""

from __future__ import annotations

from pathlib import Path

import healpy as hp
import numpy as np
import pytest

from backend.config import ROOT
from backend.ingest.icecube_catalog import (
    CATALOG_PATH,
    load_all_alerts,
    load_well_localized_alerts,
    parse_catalog,
)
from backend.localize.fuse import fuse, position_in_credible_region
from backend.localize.pointing import pointing_map


def test_catalog_file_is_present() -> None:
    assert CATALOG_PATH.is_file()
    text = CATALOG_PATH.read_text(encoding="utf-8")
    assert "58018.87118" in text
    assert "MJD" in text


def test_parse_catalog_counts() -> None:
    rows = parse_catalog()
    assert len(rows) == 50
    assert sum(1 for r in rows if r.well_localized) == 45
    assert sum(1 for r in rows if not r.well_localized) == 5
    assert sum(1 for r in rows if r.realtime) == 10
    assert {r.selection for r in rows} == {"HESE", "EHE"}


def test_all_catalog_alerts_are_real() -> None:
    alerts = load_all_alerts()
    assert len(alerts) == 50
    assert all(a.simulated is False for a in alerts)
    assert all(a.kind == "HE_NEUTRINO" for a in alerts)
    assert all(a.source == "gcn_kafka" for a in alerts)


def test_icecube_170922a_matches_scenario_b_direction() -> None:
    """Catalog IC-170922A RA/Dec must match Scenario B / GCN 21916."""
    rows = [r for r in parse_catalog() if abs(r.mjd - 58018.87118) < 1e-5]
    assert len(rows) == 1
    row = rows[0]
    assert row.ra_deg == pytest.approx(77.43, abs=1e-6)
    assert row.dec_deg == pytest.approx(5.72, abs=1e-6)

    scenario_b = ROOT / "data" / "cache" / "scenario_b_icecube_170922a" / "alerts.jsonl"
    alert_b = __import__("json").loads(scenario_b.read_text(encoding="utf-8").splitlines()[0])
    assert alert_b["simulated"] is False
    assert alert_b["raw"]["ra"] == pytest.approx(77.43, abs=1e-6)
    assert alert_b["raw"]["dec"] == pytest.approx(5.72, abs=1e-6)

    hit = next(a for a in load_well_localized_alerts() if a.alert_id == "IceCube-170922A")
    assert hit.detectors[0].pointing is not None
    assert hit.detectors[0].pointing.ra_deg == pytest.approx(77.43)
    assert hit.detectors[0].pointing.dec_deg == pytest.approx(5.72)


def test_pointing_maps_cover_all_well_localized_directions() -> None:
    """Every well-localized catalog direction sits in its own 90% pointing map."""
    alerts = load_well_localized_alerts()
    assert len(alerts) == 45
    for alert in alerts:
        p = alert.detectors[0].pointing
        assert p is not None
        prob = pointing_map(p.ra_deg, p.dec_deg, p.err_deg, nside=64)
        assert float(prob.sum()) == pytest.approx(1.0, abs=1e-6)
        assert position_in_credible_region(prob, p.ra_deg, p.dec_deg, level=0.9)


def test_fuse_icecube_170922a_from_catalog(tmp_path: Path) -> None:
    """End-to-end fuse on catalog IC-170922A (pointing only; DiffPointing N/A)."""
    alert = next(a for a in load_well_localized_alerts() if a.alert_id == "IceCube-170922A")
    skymap = fuse(alert, nside=64, out_root=tmp_path, include_pointing=True)
    assert skymap.simulated is False
    assert "timing:snews_diffpointing" not in skymap.components
    assert any("pointing" in c for c in skymap.components)
    prob = np.asarray(hp.read_map(str(tmp_path / alert.alert_id / "skymap.fits"), nest=True))
    p = alert.detectors[0].pointing
    assert p is not None
    assert position_in_credible_region(prob, p.ra_deg, p.dec_deg, level=0.9)
