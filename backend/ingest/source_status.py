"""Public provenance and process-local receipt evidence. Never expose credentials.

Configured credentials / a consumer subscribe call are not proof of a working
broker connection. Only a received message advances a source to ``receiving``.
Replays never update these live-receipt counters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from backend.config import settings

_lock = Lock()
_activity: dict[str, dict[str, Any]] = {}

SOURCE_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "id": "icecube_tracks", "name": "IceCube · Gold / Bronze tracks",
        "description": "High-energy neutrino candidates distributed by NASA GCN. A candidate is not a confirmed astrophysical source or supernova.",
        "cadence": "About 26 alerts per year; typically distributed within a minute. Rates are estimates, not a schedule.",
        "url": "https://gcn.nasa.gov/missions/icecube",
        "transport": "gcn", "topic": "gcn.notices.icecube.gold_bronze_track_alerts",
    },
    {
        "id": "icecube_cascades", "name": "IceCube · Cascade alerts",
        "description": "Additional high-energy neutrino events, with wider directional uncertainty than tracks. Public GCN Classic notices.",
        "cadence": "About 8 alerts per year, in addition to the track stream.",
        "url": "https://gcn.nasa.gov/missions/icecube",
        "transport": "gcn", "topic": "gcn.classic.text.ICECUBE_CASCADE",
    },
    {
        "id": "superk", "name": "Super-Kamiokande · Direct burst alerts",
        "description": "The observatory's own supernova-neutrino burst notices, including declared service tests. Tests never trigger science ranking or community alerts here.",
        "cadence": "Real Galactic bursts are rare. Regular test notices verify the service; they are not detections.",
        "url": "https://gcn.nasa.gov/missions/sksn",
        "transport": "gcn", "topic": "gcn.notice.superk.sn_alert",
    },
    {
        "id": "snews", "name": "SNEWS · Detector-network coincidences",
        "description": "A collaboration of neutrino observatories looking for a shared core-collapse burst. Consumed through GCN Classic.",
        "cadence": "Real alerts are exceptionally rare; routine tests are separate from science detections.",
        "url": "https://gcn.nasa.gov/missions/snews",
        "transport": "gcn", "topic": "gcn.classic.text.SNEWS",
    },
    {
        "id": "snews_hop", "name": "SNEWS · Optional Hopskotch channel",
        "description": "An optional SNEWS transport, requiring a separate authorized account and client. It is not a second independent detector network.",
        "cadence": "Event driven; depends on the account's access to the configured SNEWS topic.",
        "url": "https://snews2.org/",
        "transport": "hop", "topic": "snews2.alert",
    },
    {
        "id": "bsc5", "name": "Yale Bright Star Catalogue · Sky background",
        "description": "Yale BSC5 supplies the background star positions. Catalog stars are not neutrino detections.",
        "cadence": "Static catalog snapshot, not a live event stream.",
        "url": "https://heasarc.gsfc.nasa.gov/W3Browse/star-catalog/bsc5p.html",
        "transport": "reference", "topic": "",
    },
    {
        "id": "ads", "name": "NASA ADS · Literature evidence",
        "description": "Candidate evidence links to existing literature records. Rankings are model outputs; they are not observatory measurements or predictions of when a star will explode.",
        "cadence": "Precomputed literature index; citations remain attached to the candidate.",
        "url": "https://ui.adsabs.harvard.edu/",
        "transport": "reference", "topic": "",
    },
)

TOPIC_SOURCE = {row["topic"]: row["id"] for row in SOURCE_DEFINITIONS if row["topic"]}
TOPIC_SOURCE["gcn.notices.icecube.test.gold_bronze_track_alerts"] = "icecube_tracks"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def reset_source_activity() -> None:
    with _lock:
        _activity.clear()


def mark_source_state(source_ids: list[str], state: str) -> None:
    with _lock:
        for source_id in source_ids:
            _activity.setdefault(source_id, {})["state"] = state


def note_source_message(source_id: str, *, category: str) -> None:
    """Record broker traffic separately from accepted science/test notices."""
    now = _now()
    with _lock:
        row = _activity.setdefault(source_id, {})
        row.update(state="receiving", last_received_at=now)
        if category == "science":
            row["last_science_alert_at"] = now
            row["science_alerts"] = row.get("science_alerts", 0) + 1
        elif category == "test":
            row["last_test_at"] = now
            row["test_notices"] = row.get("test_notices", 0) + 1
        elif category == "retraction":
            row["retractions"] = row.get("retractions", 0) + 1


def data_sources_snapshot() -> dict[str, Any]:
    cached = bool(settings.use_cached_stream)
    gcn_ready = bool((settings.gcn_client_id or "").strip() and (settings.gcn_client_secret or "").strip())
    hop_ready = bool((settings.hop_username or "").strip() and (settings.hop_password or "").strip())
    with _lock:
        activity = {key: dict(value) for key, value in _activity.items()}
    sources = []
    for definition in SOURCE_DEFINITIONS:
        row: dict[str, Any] = dict(definition)
        observed = activity.get(row["id"], {})
        ready = gcn_ready if row["transport"] == "gcn" else hop_ready
        if row["transport"] == "reference":
            state = "reference"
        elif cached:
            state = "disabled"
        elif not ready:
            state = "unconfigured"
        else:
            state = observed.get("state", "starting")
        row.update(
            state=state,
            last_received_at=observed.get("last_received_at"),
            last_science_alert_at=observed.get("last_science_alert_at"),
            last_test_at=observed.get("last_test_at"),
            science_alerts=observed.get("science_alerts", 0),
            test_notices=observed.get("test_notices", 0),
            retractions=observed.get("retractions", 0),
        )
        sources.append(row)
    last_science = max((row["last_science_alert_at"] for row in sources if row["last_science_alert_at"]), default=None)
    return {
        "mode": "cached" if cached else "live",
        "live_enabled": not cached,
        "generated_at": _now(),
        "last_science_alert_received_at": last_science,
        "sources": sources,
    }
