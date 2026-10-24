"""Tests for backend.ingest.presn."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.config import settings
from backend.ingest import gcn_common, presn
from backend.ingest.gcn_common import CachedStreamError
from backend.schemas import Alert

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SYNTHETIC = FIXTURES / "presn_combined_synthetic.json"


def test_normalize_synthetic_presn_fixture() -> None:
    payload = json.loads(SYNTHETIC.read_text(encoding="utf-8"))
    assert payload.get("_fixture") == "synthetic"
    assert payload.get("simulated") is True

    alert = presn.normalize_presn_payload(payload, simulated=True)
    assert isinstance(alert, Alert)
    assert alert.kind == "PRESN"
    assert alert.source == "presn"
    assert alert.simulated is True
    assert alert.t0_utc == "2026-10-24T12:00:00Z"
    names = {d.name for d in alert.detectors}
    assert names == {"KamLAND", "Super-K"}
    assert all(d.pointing is None for d in alert.detectors)
    assert alert.raw.get("search_code") == "combined"
    # Significance from 1/FAR (FAR=0.5 per century) — derived, not invented.
    assert alert.significance == pytest.approx(2.0)


def test_listen_presn_no_network_when_cached_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "use_cached_stream", True)
    monkeypatch.setattr(gcn_common.settings, "use_cached_stream", True)

    with patch("backend.ingest.gcn_common.make_consumer") as make_consumer, patch(
        "backend.ingest.presn.make_consumer"
    ) as make_consumer_direct:
        out = list(presn.listen_presn_alerts(live=True))
        assert out == []
        make_consumer.assert_not_called()
        make_consumer_direct.assert_not_called()

    with patch("backend.ingest.gcn_common.Consumer", create=True) as Consumer:
        with pytest.raises(CachedStreamError):
            gcn_common.make_consumer(["gcn.notices.presn.kamland_superk"])
        Consumer.assert_not_called()


def test_make_consumer_blocked_under_cached_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gcn_common.settings, "use_cached_stream", True)
    with patch.dict("sys.modules", {"gcn_kafka": MagicMock()}):
        with pytest.raises(CachedStreamError):
            gcn_common.require_live_network()
