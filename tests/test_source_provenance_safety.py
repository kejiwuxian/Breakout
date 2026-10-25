"""Source receipts describe observed traffic, never configured or simulated detections."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from scipy.integrate import quad

from backend.config import settings
from backend.ingest import live_channels, source_status
from backend.ingest.gcn_common import TOPIC_ICECUBE_GOLD_BRONZE, TOPIC_SUPERK_SN
from backend.ingest.observatory_notices import (
    notice_category,
    normalize_cascade_text,
    normalize_superk_payload,
)


# Values from NASA GCN's Super-K schema format example. This is a test fixture,
# not a recorded supernova detection and never delivered to the running app.
# https://gcn.nasa.gov/schema/stable/gcn/notices/superk/sn_alert.real.example.json
SUPERK_FORMAT_EXAMPLE = {
    "id": "SN.095001.000001",
    "alert_datetime": "2023-08-01T00:00:21.00Z",
    "alert_tense": "current",
    "alert_type": "initial",
    "trigger_time": "2023-08-01T00:00:01.000000Z",
    "n_events": 64176,
    "ra": 270.82,
    "dec": 31.46,
    "ra_dec_error": 0.91,
    "containment_probability": 0.68,
}

# Selection of fields from the collaboration's published format demonstration:
# https://gcn.gsfc.nasa.gov/doc/High_Energy_Neutrino_Cascade_Alerts.pdf, page 9.
CASCADE_FORMAT_EXAMPLE = """NOTICE_TYPE: ICECUBE Cascade
EVENT_NAME: IceCubeCascade-200701b
SRC_RA: 220.0434d {+14h 40m 10s} (J2000),
        220.2371d {+14h 40m 57s} (current),
SRC_DEC: +43.1731d {+43d 10' 23\"} (J2000),
SRC_ERROR: 44.06 [deg radius, stat+systematic, 90% containment]
DISCOVERY_DATE: 19031 TJD; 183 DOY; 20/07/01 (yy/mm/dd)
DISCOVERY_TIME: 69893 SOD {19:24:53.44} UT
REVISION: 0
ENERGY: 10.99 [TeV]
SIGNALNESS: 8.7016e-01 [dn]
FAR: 0.4021 [yr^-1]
"""


@pytest.fixture(autouse=True)
def clear_source_receipts():
    source_status.reset_source_activity()
    yield
    source_status.reset_source_activity()


@pytest.mark.parametrize("tense", ["test", "injection", "injections"])
def test_declared_test_traffic_never_becomes_a_science_alert(tense):
    payload = {**SUPERK_FORMAT_EXAMPLE, "alert_tense": tense}
    assert notice_category(payload) == "test"
    assert live_channels._route_gcn_message(TOPIC_SUPERK_SN, payload) is None


def test_retraction_is_excluded_even_when_the_notice_has_coordinates():
    payload = {**SUPERK_FORMAT_EXAMPLE, "alert_type": "retraction"}
    assert notice_category(payload) == "retraction"
    assert live_channels._route_gcn_message(TOPIC_SUPERK_SN, payload) is None
    with pytest.raises(ValueError):
        normalize_superk_payload(payload)


@pytest.mark.parametrize("field", ["ra", "dec", "ra_dec_error", "trigger_time", "id"])
def test_superk_missing_measurements_are_rejected_instead_of_filled(field):
    payload = dict(SUPERK_FORMAT_EXAMPLE)
    del payload[field]
    with pytest.raises((ValueError, TypeError)):
        normalize_superk_payload(payload)


def _spherical_probability(radius_deg: float, sigma_deg: float) -> float:
    radius, sigma = math.radians(radius_deg), math.radians(sigma_deg)
    density = lambda theta: math.exp(-theta * theta / (2 * sigma * sigma)) * math.sin(theta)
    return quad(density, 0, radius)[0] / quad(density, 0, math.pi)[0]


def test_superk_preserves_published_measurements_and_containment():
    original = copy.deepcopy(SUPERK_FORMAT_EXAMPLE)
    alert = normalize_superk_payload(original)
    assert original == SUPERK_FORMAT_EXAMPLE
    assert alert.simulated is False
    assert alert.t0_utc == original["trigger_time"]
    assert alert.raw["ra_dec_error"] == 0.91
    assert alert.raw["containment_probability"] == 0.68
    assert alert.detectors[0].n_events == 64176
    pointing = alert.detectors[0].pointing
    assert pointing is not None
    assert pointing.ra_deg == 270.82
    assert pointing.dec_deg == 31.46
    assert _spherical_probability(0.91, pointing.err_deg) == pytest.approx(0.68, abs=1e-6)
    assert "not the collaboration's full sky map" in alert.raw["localization_model"]


def test_cascade_uses_j2000_coordinates_and_keeps_original_uncertainty():
    alert = normalize_cascade_text(CASCADE_FORMAT_EXAMPLE)
    pointing = alert.detectors[0].pointing
    assert pointing is not None
    assert pointing.ra_deg == 220.0434
    assert pointing.dec_deg == 43.1731
    assert alert.t0_utc == "2020-07-01T19:24:53.44Z"
    assert alert.raw["ra_dec_error"] == 44.06
    assert _spherical_probability(44.06, pointing.err_deg) == pytest.approx(0.9, abs=1e-6)
    assert alert.raw["far_per_year"] == 0.4021
    assert alert.raw["p_astro"] == pytest.approx(0.87016)


def test_missing_credentials_and_cached_mode_never_claim_receipts(monkeypatch):
    monkeypatch.setattr(settings, "gcn_client_id", "")
    monkeypatch.setattr(settings, "gcn_client_secret", "")
    monkeypatch.setattr(settings, "hop_username", "")
    monkeypatch.setattr(settings, "hop_password", "")
    monkeypatch.setattr(settings, "use_cached_stream", False)
    snapshot = source_status.data_sources_snapshot()
    live_sources = [row for row in snapshot["sources"] if row["transport"] != "reference"]
    assert all(row["state"] == "unconfigured" for row in live_sources)
    assert all(row["last_received_at"] is None and row["science_alerts"] == 0 for row in live_sources)
    monkeypatch.setattr(settings, "use_cached_stream", True)
    assert all(row["state"] in {"disabled", "reference"} for row in source_status.data_sources_snapshot()["sources"])


def test_configured_credentials_are_not_published_or_treated_as_receipts(monkeypatch):
    monkeypatch.setattr(settings, "use_cached_stream", False)
    monkeypatch.setattr(settings, "gcn_client_id", "private-client-id")
    monkeypatch.setattr(settings, "gcn_client_secret", "private-client-secret")
    snapshot = source_status.data_sources_snapshot()
    assert snapshot["last_science_alert_received_at"] is None
    gcn_sources = [row for row in snapshot["sources"] if row["transport"] == "gcn"]
    assert all(row["state"] == "starting" and row["last_received_at"] is None for row in gcn_sources)
    public = json.dumps(snapshot)
    assert "private-client-id" not in public
    assert "private-client-secret" not in public


def test_live_listener_separates_tests_retractions_and_valid_science(monkeypatch):
    monkeypatch.setattr(settings, "use_cached_stream", False)
    monkeypatch.setattr(settings, "gcn_client_id", "configured")
    monkeypatch.setattr(settings, "gcn_client_secret", "configured")
    consumer = MagicMock()
    monkeypatch.setattr(live_channels, "make_consumer", lambda topics: consumer)
    payloads = [
        {**SUPERK_FORMAT_EXAMPLE, "alert_tense": "test"},
        {**SUPERK_FORMAT_EXAMPLE, "alert_tense": "injections"},
        {**SUPERK_FORMAT_EXAMPLE, "alert_type": "retraction"},
        SUPERK_FORMAT_EXAMPLE,
    ]
    monkeypatch.setattr(live_channels, "iter_topic_messages", lambda source: iter((TOPIC_SUPERK_SN, row) for row in payloads))
    emitted = list(live_channels.listen_gcn_live_alerts())
    assert len(emitted) == 1
    assert emitted[0].raw["ingest_topic"] == TOPIC_SUPERK_SN
    consumer.close.assert_called_once()
    superk = next(row for row in source_status.data_sources_snapshot()["sources"] if row["id"] == "superk")
    assert superk["test_notices"] == 2
    assert superk["retractions"] == 1
    assert superk["science_alerts"] == 1
    assert superk["last_science_alert_at"] is not None


def test_invalid_received_payload_does_not_count_as_a_science_detection(monkeypatch):
    monkeypatch.setattr(settings, "use_cached_stream", False)
    monkeypatch.setattr(settings, "gcn_client_id", "configured")
    monkeypatch.setattr(settings, "gcn_client_secret", "configured")
    consumer = MagicMock()
    monkeypatch.setattr(live_channels, "make_consumer", lambda topics: consumer)
    monkeypatch.setattr(live_channels, "iter_topic_messages", lambda source: iter([(TOPIC_ICECUBE_GOLD_BRONZE, {"mission": "IceCube"})]))
    assert list(live_channels.listen_gcn_live_alerts()) == []
    icecube = next(row for row in source_status.data_sources_snapshot()["sources"] if row["id"] == "icecube_tracks")
    assert icecube["state"] == "receiving"
    assert icecube["last_received_at"] is not None
    assert icecube["science_alerts"] == 0
    assert icecube["last_science_alert_at"] is None
