"""Realtime channel routing + classic SNEWS + epoch position."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.candidates.epoch_position import (
    current_icrs,
    helps_skymap_ranking,
    propagate_icrs,
)
from backend.config import settings
from backend.ingest import gcn_common, live_channels, snews
from backend.ingest.snews_classic import parse_classic_snews_text
from backend.localize.external_skymap import healpix_url_from_alert
from backend.localize.fuse import fuse
from backend.schemas import Alert

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLASSIC = FIXTURES / "snews_classic_position_notice.txt"
SNEWS2 = FIXTURES / "snews2_coincidence_public_example.json"


def test_live_gcn_topics_include_documented_public_streams_only() -> None:
    topics = live_channels.live_gcn_topics()
    assert "gcn.notices.icecube.gold_bronze_track_alerts" in topics
    assert "gcn.classic.text.SNEWS" in topics
    assert "gcn.notice.superk.sn_alert" in topics
    assert "gcn.classic.text.ICECUBE_CASCADE" in topics
    assert "gcn.notices.snews2.coincidence" not in topics
    assert "gcn.notices.presn.kamland_superk" not in topics


def test_classic_snews_parse_and_pointing_fuse(tmp_path: Path) -> None:
    text = CLASSIC.read_text(encoding="utf-8")
    alert = parse_classic_snews_text(text, simulated=False)
    assert alert.kind == "SN_BURST"
    assert alert.simulated is False
    assert alert.raw.get("has_timing_deltas") is False
    assert {d.name for d in alert.detectors} >= {"Super-K", "IceCube"}
    sk = next(d for d in alert.detectors if d.name == "Super-K")
    assert sk.pointing is not None
    assert sk.pointing.ra_deg == pytest.approx(273.34)
    assert sk.pointing.dec_deg == pytest.approx(44.60)

    skymap = fuse(alert, nside=64, out_root=tmp_path)
    assert "timing:snews_diffpointing" not in skymap.components
    assert "superk_pointing" in skymap.components
    assert skymap.simulated is False


def test_route_snews2_json() -> None:
    payload = json.loads(SNEWS2.read_text(encoding="utf-8"))
    # The published fixture is explicitly a test. Only a current science
    # variant may be routed into the science pipeline.
    assert live_channels._route_gcn_message("gcn.notices.snews2.coincidence", payload) is None
    payload["alert_tense"] = "current"
    alert = live_channels._route_gcn_message(
        "gcn.notices.snews2.coincidence", payload
    )
    assert alert is not None
    assert alert.source == "snews2"
    assert alert.kind == "SN_BURST"


def test_route_classic_text() -> None:
    text = CLASSIC.read_text(encoding="utf-8")
    alert = live_channels._route_gcn_message("gcn.classic.text.SNEWS", text)
    assert alert is not None
    assert alert.alert_id.startswith("SNEWS-classic-")


def test_listen_gcn_no_network_when_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "use_cached_stream", True)
    monkeypatch.setattr(gcn_common.settings, "use_cached_stream", True)
    monkeypatch.setattr(live_channels.settings, "use_cached_stream", True)
    with patch("backend.ingest.live_channels.make_consumer") as make_consumer:
        assert list(live_channels.listen_gcn_live_alerts(live=True)) == []
        make_consumer.assert_not_called()


def test_hop_skips_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "use_cached_stream", False)
    monkeypatch.setattr(live_channels.settings, "use_cached_stream", False)
    monkeypatch.setattr(live_channels.settings, "hop_username", "")
    monkeypatch.setattr(live_channels.settings, "hop_password", "")
    assert list(live_channels.listen_hop_snews_alerts(live=True)) == []


def test_placeholder_healpix_url_ignored() -> None:
    payload = json.loads(SNEWS2.read_text(encoding="utf-8"))
    alert = snews.normalize_snews_payload(payload, simulated=False)
    assert healpix_url_from_alert(alert) is None


def test_epoch_propagate_linear() -> None:
    # 3600 mas/yr = 0.001 deg/yr; over 10 yr → 0.01 deg in Dec.
    ra, dec = propagate_icrs(
        10.0,
        20.0,
        pmra_mas_yr=0.0,
        pmdec_mas_yr=3600.0,
        epoch_year=2015.0,
        target_year=2025.0,
    )
    assert ra == pytest.approx(10.0)
    assert dec == pytest.approx(20.01, abs=1e-9)


def test_current_icrs_noop_without_pm() -> None:
    ra, dec = current_icrs({"ra_deg": 88.79, "dec_deg": 7.41})
    assert ra == pytest.approx(88.79)
    assert dec == pytest.approx(7.41)


def test_pm_does_not_help_nside64_ranking() -> None:
    # Typical RSG PM ≪ HEALPix pixel → do not expect ranking changes.
    assert helps_skymap_ranking(nside=64, pm_mas_yr=50.0, years=30.0) is False


def test_snews2_diffpointing_still_preferred(tmp_path: Path) -> None:
    """Multi-detector SN_BURST with distinct times → DiffPointing component."""
    from backend.ingest.gcn_common import detector_hit

    t0 = "2020-01-01T00:00:00"
    alert = Alert(
        alert_id="live-snews-dp",
        kind="SN_BURST",
        source="snews2",
        simulated=False,
        t0_utc=t0,
        detectors=[
            detector_hit("Super-K", t_arrival_utc=t0, n_events=10),
            detector_hit(
                "IceCube",
                t_arrival_utc="2020-01-01T00:00:00.020",
                n_events=100,
            ),
            detector_hit(
                "SNO+",
                t_arrival_utc="2020-01-01T00:00:00.010",
                n_events=5,
            ),
        ],
        significance=3.0,
        raw={"has_timing_deltas": True},
    )
    skymap = fuse(alert, nside=32, out_root=tmp_path)
    assert "timing:snews_diffpointing" in skymap.components
