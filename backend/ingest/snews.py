"""SNEWS 2.0 alert listener.

Input → output: Live SNEWS stream → Alert (kind=SN_BURST, source=snews2).
Uses gcn-kafka on topic gcn.notices.snews2.coincidence.
When USE_CACHED_STREAM=True no network is opened.

Live notices set simulated=false and keep the original payload in raw.
Public schema example: nasa-gcn/gcn-schema SNEWS2 coincidence test_alert example.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Iterator
from typing import Any

from backend.config import settings
from backend.ingest.gcn_common import (
    TOPIC_SNEWS2_COINCIDENCE,
    canonical_detector_name,
    detector_hit,
    iter_json_messages,
    make_consumer,
    network_allowed,
)
from backend.schemas import Alert, DetectorHit, DetectorName, Pointing


def _triggered_detectors(payload: dict[str, Any]) -> list[tuple[DetectorName, str]]:
    """Return (detector, arrival_utc) pairs from a SNEWS2 coincidence payload."""
    t0 = str(
        payload.get("trigger_time")
        or payload.get("alert_datetime")
        or (payload.get("tier_data") or {}).get("neutrino_time_utc")
        or ""
    )
    times = payload.get("event_times_utc") or []
    names_field = payload.get("detector_names")
    status = payload.get("detector_status") or {}

    ordered_names: list[str] = []
    if isinstance(names_field, list) and names_field:
        ordered_names = [str(n) for n in names_field]
    elif isinstance(status, dict) and status:
        # Prefer detectors marked triggered; fall back to all keys (insertion order).
        triggered = [k for k, v in status.items() if str(v).lower() == "triggered"]
        ordered_names = triggered or list(status.keys())

    pairs: list[tuple[DetectorName, str]] = []
    for i, raw_name in enumerate(ordered_names):
        canon = canonical_detector_name(raw_name)
        if canon is None:
            continue
        arrival = str(times[i]) if i < len(times) and times[i] else t0
        if not arrival:
            continue
        pairs.append((canon, arrival))
    return pairs


def normalize_snews_payload(payload: dict[str, Any], *, simulated: bool) -> Alert:
    """Normalize a SNEWS 2.0 coincidence JSON notice into Alert (SN_BURST)."""
    raw = copy.deepcopy(payload)
    t0 = (
        payload.get("trigger_time")
        or payload.get("alert_datetime")
        or (payload.get("tier_data") or {}).get("neutrino_time_utc")
    )
    if not t0:
        raise ValueError("SNEWS payload missing trigger_time / alert_datetime")

    pairs = _triggered_detectors(payload)
    if not pairs:
        raise ValueError("SNEWS payload has no recognized triggered detectors")

    # Optional Super-K pointing from notice RA/Dec when present (classic SNEWS).
    pointing: Pointing | None = None
    if payload.get("ra") is not None and payload.get("dec") is not None:
        err = payload.get("ra_dec_error")
        if err is None:
            err = payload.get("error")
        pointing = Pointing(
            ra_deg=float(payload["ra"]),
            dec_deg=float(payload["dec"]),
            err_deg=float(err) if err is not None else 0.0,
        )

    hits: list[DetectorHit] = []
    for name, arrival in pairs:
        hits.append(
            detector_hit(
                name,
                t_arrival_utc=arrival,
                n_events=int(payload.get("number_of_events") or 0) if len(pairs) == 1 else 0,
                pointing=pointing if name == "Super-K" else None,
            )
        )

    far = payload.get("far")
    if far is None:
        far = (payload.get("tier_data") or {}).get("false_alarm_prob")
    if "significance" in payload and payload["significance"] is not None:
        significance = float(payload["significance"])
    elif far is not None and float(far) > 0:
        significance = float(-math.log10(float(far)))
    else:
        significance = 0.0

    alert_id = str(payload.get("id") or payload.get("alert_id") or f"snews2-{t0}")

    return Alert(
        alert_id=alert_id,
        kind="SN_BURST",
        source="snews2",
        simulated=bool(simulated),
        t0_utc=str(t0),
        detectors=hits,
        significance=significance,
        raw=raw,
    )


def listen_snews_alerts(*, live: bool | None = None) -> Iterator[Alert]:
    """Yield SN_BURST Alerts from the SNEWS 2.0 GCN Kafka topic.

    When USE_CACHED_STREAM=True, yields nothing and opens no network connection.
    """
    want_live = (not settings.use_cached_stream) if live is None else bool(live)
    if settings.use_cached_stream or not want_live or not network_allowed():
        return
        yield  # pragma: no cover

    consumer = make_consumer([TOPIC_SNEWS2_COINCIDENCE])
    for payload in iter_json_messages(consumer):
        yield normalize_snews_payload(payload, simulated=False)
