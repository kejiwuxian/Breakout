"""GCN Kafka consumer for IceCube high-energy neutrino notices.

Input → output: Live GCN Kafka IceCube notices → Alert
(kind=HE_NEUTRINO, source=gcn_kafka).
Topic: gcn.notices.icecube.gold_bronze_track_alerts
(schema: nasa-gcn/gcn-schema single_neutrino_alerts).

When USE_CACHED_STREAM=True no network is opened.
Live notices set simulated=false and keep the original payload in raw.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Iterator
from typing import Any

from backend.config import settings
from backend.ingest.gcn_common import (
    TOPIC_ICECUBE_GOLD_BRONZE,
    detector_hit,
    iter_json_messages,
    make_consumer,
    network_allowed,
)
from backend.schemas import Alert, Pointing


def normalize_gcn_payload(payload: dict[str, Any], *, simulated: bool) -> Alert:
    """Normalize an IceCube GCN JSON notice into Alert (HE_NEUTRINO).

    Supports the public gold/bronze track alert example fields:
    event_name / id, trigger_time, ra, dec, ra_dec_error, number_of_events,
    p_astro, far.
    """
    raw = copy.deepcopy(payload)
    t0 = payload.get("trigger_time") or payload.get("alert_datetime")
    if not t0:
        raise ValueError("IceCube GCN payload missing trigger_time / alert_datetime")

    event_names = payload.get("event_name") or []
    ids = payload.get("id") or []
    if isinstance(event_names, list) and event_names:
        alert_id = str(event_names[0])
    elif isinstance(ids, list) and ids:
        alert_id = str(ids[0])
    else:
        alert_id = str(payload.get("alert_id") or f"icecube-{t0}")

    pointing: Pointing | None = None
    if payload.get("ra") is not None and payload.get("dec") is not None:
        err = payload.get("ra_dec_error")
        pointing = Pointing(
            ra_deg=float(payload["ra"]),
            dec_deg=float(payload["dec"]),
            err_deg=float(err) if err is not None else 0.0,
        )

    n_events = int(payload.get("number_of_events") or 1)
    hit = detector_hit(
        "IceCube",
        t_arrival_utc=str(t0),
        n_events=n_events,
        pointing=pointing,
    )

    far = payload.get("far")
    p_astro = payload.get("p_astro")
    if "significance" in payload and payload["significance"] is not None:
        significance = float(payload["significance"])
    elif far is not None and float(far) > 0:
        significance = float(-math.log10(float(far)))
    elif p_astro is not None:
        significance = float(p_astro)
    else:
        significance = 0.0

    return Alert(
        alert_id=alert_id,
        kind="HE_NEUTRINO",
        source="gcn_kafka",
        simulated=bool(simulated),
        t0_utc=str(t0),
        detectors=[hit],
        significance=significance,
        raw=raw,
    )


def listen_gcn_alerts(*, live: bool | None = None) -> Iterator[Alert]:
    """Yield HE_NEUTRINO Alerts from IceCube GCN Kafka topics.

    Requires GCN_CLIENT_ID / GCN_CLIENT_SECRET only in live mode.
    When USE_CACHED_STREAM=True, yields nothing and opens no network connection.
    """
    want_live = (not settings.use_cached_stream) if live is None else bool(live)
    if settings.use_cached_stream or not want_live or not network_allowed():
        return
        yield  # pragma: no cover

    consumer = make_consumer([TOPIC_ICECUBE_GOLD_BRONZE])
    for payload in iter_json_messages(consumer):
        yield normalize_gcn_payload(payload, simulated=False)
