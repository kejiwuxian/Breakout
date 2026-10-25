"""Source transparency and strict science/test separation; no network traffic."""

from __future__ import annotations

import copy
import json
import math
from unittest.mock import MagicMock

import pytest

from backend.config import settings
from backend.ingest import live_channels, source_status
from backend.ingest.gcn_common import TOPIC_ICECUBE_CASCADE, TOPIC_SUPERK_SN
from backend.ingest.observatory_notices import (
    containment_to_sigma,
    normalize_cascade_text,
    normalize_superk_payload,
    notice_category,
)

# Format example published by NASA's gcn-schema project. These fixture values
# are not a real supernova detection and are used only to test the parser.
SUPERK_EXAMPLE = {
    "mission": "Super-Kamiokande", "id": "SN.095001.000001", "record_number": 1,
    "trigger_time": "2023-08-01T00:00:01.000000Z", "alert_tense": "current",
    "alert_type": "initial", "pipeline": "snwatch", "n_events": 64176,
    "ra": 270.82, "dec": 31.46, "ra_dec_error": 0.91, "containment_probability": 0.68,
}

# Format sample from IceCube Collaboration's cascade alert specification
# https://gcn.gsfc.nasa.gov/doc/High_Energy_Neutrino_Cascade_Alerts.pdf, p. 9.
CASCADE_EXAMPLE = """NOTICE_TYPE: ICECUBE Cascade
EVENT_NAME: IceCubeCascade-200701b
SRC_RA: 220.0434d {+14h 40m 10s} (J2000),
SRC_DEC: +43.1731d {+43d 10' 23\"} (J2000),
SRC_ERROR: 44.06 [deg radius, stat+systematic, 90% containment]
DISCOVERY_DATE: 19031 TJD; 183 DOY; 20/07/01 (yy/mm/dd)
DISCOVERY_TIME: 69893 SOD {19:24:53.44} UT
SIGNALNESS: 8.7016e-01 [dn]
ENERGY: 10.99 [TeV]
FAR: 0.4021 [yr^-1]
REVISION: 0
SKYMAP_FITS_URL: https://roc.icecube.wisc.edu/public/hese_cascades/hese_59031_run00134244.evt000034406854.fits
"""


@pytest.fixture(autouse=True)
def clean_source_activity():
    source_status.reset_source_activity()
    yield
    source_status.reset_source_activity()


def test_cached_status_never_claims_live_or_exposes_credentials(monkeypatch):
    monkeypatch.setattr(settings, "use_cached_stream", True)
    monkeypatch.setattr(settings, "gcn_client_id", "private-client-id")
    monkeypatch.setattr(settings, "gcn_client_secret", "private-secret-value")
    source_status.note_source_message("superk", category="science")
    snapshot = source_status.data_sources_snapshot()
    assert snapshot["mode"] == "cached"
    assert snapshot["live_enabled"] is False
    assert all(row["state"] == "disabled" for row in snapshot["sources"] if row["transport"] != "reference")
    assert "private-client-id" not in json.dumps(snapshot)
    assert "private-secret-value" not in json.dumps(snapshot)


def test_credentials_are_not_proof_of_receiving_data(monkeypatch):
    monkeypatch.setattr(settings, "use_cached_stream", False)
    monkeypatch.setattr(settings, "gcn_client_id", "configured")
    monkeypatch.setattr(settings, "gcn_client_secret", "configured")
    snapshot = source_status.data_sources_snapshot()
    assert all(row["state"] == "starting" for row in snapshot["sources"] if row["transport"] == "gcn")
    assert snapshot["last_science_alert_received_at"] is None


def test_missing_credentials_and_test_traffic_are_explicit(monkeypatch):
    monkeypatch.setattr(settings, "use_cached_stream", False)
    monkeypatch.setattr(settings, "gcn_client_id", "")
    monkeypatch.setattr(settings, "gcn_client_secret", "")
    snapshot = source_status.data_sources_snapshot()
    assert all(row["state"] == "unconfigured" for row in snapshot["sources"] if row["transport"] == "gcn")
    monkeypatch.setattr(settings, "gcn_client_id", "configured")
    monkeypatch.setattr(settings, "gcn_client_secret", "configured")
    source_status.note_source_message("superk", category="test")
    snapshot = source_status.data_sources_snapshot()
    superk = next(row for row in snapshot["sources"] if row["id"] == "superk")
    assert superk["state"] == "receiving"
    assert superk["test_notices"] == 1 and superk["science_alerts"] == 0
    assert superk["last_received_at"] and superk["last_test_at"]
    assert snapshot["last_science_alert_received_at"] is None


def test_superk_preserves_provenance_and_converts_containment_radius():
    original = copy.deepcopy(SUPERK_EXAMPLE)
    alert = normalize_superk_payload(original)
    assert alert.kind == "SN_BURST" and alert.simulated is False
    hit = alert.detectors[0]
    assert hit.name == "Super-K" and hit.n_events == 64176
    assert hit.pointing.ra_deg == pytest.approx(270.82)
    # .91 degrees encloses 68%; it must not be passed as Gaussian sigma.
    expected_small_angle = 0.91 / math.sqrt(-2 * math.log(1 - 0.68))
    assert hit.pointing.err_deg == pytest.approx(expected_small_angle, rel=0.001)
    assert alert.raw["ra_dec_error"] == 0.91
    assert alert.raw["containment_probability"] == 0.68
    assert original == SUPERK_EXAMPLE


def test_cascade_uses_j2000_position_discovery_time_and_preserves_far_units():
    alert = normalize_cascade_text(CASCADE_EXAMPLE)
    assert alert.kind == "HE_NEUTRINO" and alert.simulated is False
    assert alert.alert_id == "IceCubeCascade-200701b"
    assert alert.t0_utc == "2020-07-01T19:24:53.44Z"
    assert alert.detectors[0].pointing.ra_deg == pytest.approx(220.0434)
    assert alert.detectors[0].pointing.dec_deg == pytest.approx(43.1731)
    assert alert.detectors[0].pointing.err_deg != pytest.approx(44.06)
    assert alert.raw["notice_text"] == CASCADE_EXAMPLE
    assert alert.raw["far_per_year"] == pytest.approx(0.4021)
    assert alert.raw["containment_probability"] == 0.9
    assert alert.raw["healpix_url"].startswith("https://roc.icecube.wisc.edu/")


def test_wide_cascade_containment_matches_spherical_model():
    from scipy.integrate import quad

    sigma = math.radians(containment_to_sigma(44.06, 0.9))
    density = lambda theta: math.exp(-theta ** 2 / (2 * sigma ** 2)) * math.sin(theta)
    contained = quad(density, 0, math.radians(44.06))[0] / quad(density, 0, math.pi)[0]
    assert contained == pytest.approx(0.9, abs=1e-8)


@pytest.mark.parametrize("extra", [
    {"alert_tense": "test"}, {"alert_tense": "injection"}, {"alert_type": "retraction"},
    {"test": True}, {"ra": float("nan")}, {"dec": 91}, {"ra_dec_error": 0},
])
def test_superk_non_science_or_invalid_localization_rejected(extra):
    with pytest.raises(ValueError):
        normalize_superk_payload(SUPERK_EXAMPLE | extra)


def test_live_listener_excludes_tests_retractions_and_malformed_notices(monkeypatch):
    monkeypatch.setattr(settings, "use_cached_stream", False)
    consumer = MagicMock()
    monkeypatch.setattr(live_channels, "make_consumer", lambda _: consumer)
    notices = [
        (TOPIC_SUPERK_SN, SUPERK_EXAMPLE | {"alert_tense": "test"}),
        (TOPIC_SUPERK_SN, SUPERK_EXAMPLE | {"alert_type": "retraction"}),
        (TOPIC_SUPERK_SN, {"not": "a valid notice"}),
        (TOPIC_SUPERK_SN, SUPERK_EXAMPLE),
        (TOPIC_ICECUBE_CASCADE, CASCADE_EXAMPLE),
    ]
    monkeypatch.setattr(live_channels, "iter_topic_messages", lambda _: iter(notices))
    alerts = list(live_channels.listen_gcn_live_alerts(live=True))
    assert len(alerts) == 2
    assert all(not alert.simulated for alert in alerts)
    assert alerts[0].raw["ingest_topic"] == TOPIC_SUPERK_SN
    snapshot = source_status.data_sources_snapshot()
    sk = next(row for row in snapshot["sources"] if row["id"] == "superk")
    assert sk["science_alerts"] == 1 and sk["test_notices"] == 1 and sk["retractions"] == 1
    assert snapshot["last_science_alert_received_at"] is not None
    consumer.close.assert_called_once()


def test_test_topic_and_classic_retractions_never_rank():
    assert notice_category(SUPERK_EXAMPLE, "gcn.notices.icecube.test.gold_bronze_track_alerts") == "test"
    assert live_channels._route_gcn_message(TOPIC_ICECUBE_CASCADE, CASCADE_EXAMPLE.replace("ICECUBE Cascade", "ICECUBE Cascade TEST")) is None
    assert live_channels._route_gcn_message(TOPIC_ICECUBE_CASCADE, CASCADE_EXAMPLE + "COMMENTS: Retraction of this notice\n") is None


def test_data_sources_http_response(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app import app

    monkeypatch.setattr(settings, "use_cached_stream", True)
    with TestClient(app) as client:
        response = client.get("/api/data-sources")
    assert response.status_code == 200
    assert response.json()["mode"] == "cached"
    assert response.json()["last_science_alert_received_at"] is None
