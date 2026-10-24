"""Tests for backend.ingest.snews."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import settings
from backend.ingest import gcn_common, snews
from backend.ingest.gcn_common import CachedStreamError
from backend.schemas import Alert

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PUBLIC = FIXTURES / "snews2_coincidence_public_example.json"


def test_normalize_snews2_public_example() -> None:
    payload = json.loads(PUBLIC.read_text(encoding="utf-8"))
    alert = snews.normalize_snews_payload(payload, simulated=False)
    assert isinstance(alert, Alert)
    assert alert.kind == "SN_BURST"
    assert alert.source == "snews2"
    assert alert.simulated is False
    assert alert.t0_utc == "2026-04-03T16:21:07.312Z"
    assert {d.name for d in alert.detectors} == {"Super-K", "IceCube", "KamLAND"}
    assert alert.raw["mission"] == "SNEWS"
    assert alert.raw["snews2_tier"] == "CoincidenceTier"
    # far=1e-4 → −log10(far)=4
    assert alert.significance == pytest.approx(4.0)


def test_listen_snews_no_network_when_cached_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "use_cached_stream", True)
    monkeypatch.setattr(gcn_common.settings, "use_cached_stream", True)

    with patch("backend.ingest.snews.make_consumer") as make_consumer:
        assert list(snews.listen_snews_alerts(live=True)) == []
        make_consumer.assert_not_called()

    with pytest.raises(CachedStreamError):
        gcn_common.make_consumer(["gcn.notices.snews2.coincidence"])
