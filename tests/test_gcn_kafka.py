"""Tests for backend.ingest.gcn_kafka (IceCube HE_NEUTRINO)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import settings
from backend.ingest import gcn_common, gcn_kafka
from backend.ingest.gcn_common import CachedStreamError
from backend.schemas import Alert

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PUBLIC = FIXTURES / "gcn_icecube_gold_bronze_public_example.json"


def test_normalize_icecube_public_example() -> None:
    payload = json.loads(PUBLIC.read_text(encoding="utf-8"))
    alert = gcn_kafka.normalize_gcn_payload(payload, simulated=False)
    assert isinstance(alert, Alert)
    assert alert.kind == "HE_NEUTRINO"
    assert alert.source == "gcn_kafka"
    assert alert.simulated is False
    assert alert.alert_id == "IceCube-230416A"
    assert alert.t0_utc == "2023-04-16T05:22:26.150574Z"
    assert len(alert.detectors) == 1
    hit = alert.detectors[0]
    assert hit.name == "IceCube"
    assert hit.pointing is not None
    assert hit.pointing.ra_deg == pytest.approx(345.82)
    assert hit.pointing.dec_deg == pytest.approx(9.01)
    assert hit.pointing.err_deg == pytest.approx(0.5)
    assert hit.n_events == 1
    assert alert.raw["pipeline"] == "Bronze Track Alert"
    assert alert.raw["p_astro"] == pytest.approx(0.34064)
    # far from public example → −log10(far)
    assert alert.significance == pytest.approx(-__import__("math").log10(8.029e-08))


def test_listen_gcn_no_network_when_cached_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "use_cached_stream", True)
    monkeypatch.setattr(gcn_common.settings, "use_cached_stream", True)

    with patch("backend.ingest.gcn_kafka.make_consumer") as make_consumer:
        assert list(gcn_kafka.listen_gcn_alerts(live=True)) == []
        make_consumer.assert_not_called()

    with pytest.raises(CachedStreamError):
        gcn_common.make_consumer(["gcn.notices.icecube.gold_bronze_track_alerts"])
