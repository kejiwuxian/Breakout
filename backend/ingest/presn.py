"""Stage 0: pre-SN alert listener (KamLAND + Super-K joint alert).

Input → output: Pre-SN alert → Alert (kind=PRESN, source=presn).
Live path uses gcn-kafka; when USE_CACHED_STREAM=True no network is opened
(use ingest.cache.replay_scenario instead).

The combined KamLAND + Super-K system is documented in arXiv:2404.09920:
alarms go to GCN as email circulars, and registered users get a text file with
false-alarm rate, timestamp, and a search code (KamLAND-only / SK-only /
combined). This module normalizes a JSON form of those fields for Kafka when
available. Live notices set simulated=false and keep the original payload in
raw.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from typing import Any

from backend.config import settings
from backend.ingest.gcn_common import (
    TOPIC_PRESN_COMBINED,
    canonical_detector_name,
    detector_hit,
    iter_json_messages,
    make_consumer,
    network_allowed,
)
from backend.schemas import Alert, DetectorHit, DetectorName

# Search codes described in arXiv:2404.09920 §VII.
SEARCH_CODE_COMBINED = "combined"
SEARCH_CODE_KAMLAND = "kamland_only"
SEARCH_CODE_SK = "sk_only"

DEFAULT_PRESN_DETECTORS: tuple[DetectorName, ...] = ("KamLAND", "Super-K")


def _detectors_for_search_code(code: str) -> list[DetectorName]:
    normalized = code.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"combined", "combination", "joint"}:
        return list(DEFAULT_PRESN_DETECTORS)
    if normalized in {"kamland_only", "kamland", "kl_only"}:
        return ["KamLAND"]
    if normalized in {"sk_only", "super_k_only", "superk_only", "sk"}:
        return ["Super-K"]
    # Explicit detector list preferred over guessing unknown codes.
    return list(DEFAULT_PRESN_DETECTORS)


def normalize_presn_payload(payload: dict[str, Any], *, simulated: bool) -> Alert:
    """Normalize a pre-SN payload into an Alert (kind=PRESN).

    Expected fields (JSON mirror of the registered text feed / future Kafka):
    - timestamp_utc or trigger_time / alert_datetime
    - false_alarm_rate_per_century (or far_per_century)
    - search_code: combined | kamland_only | sk_only
    - optional detectors: list of detector names
    - optional n_events_kamland / n_events_sk

    Live messages use simulated=False; synthetic fixtures pass simulated=True.
    The untouched input is stored in ``raw``.
    """
    raw = copy.deepcopy(payload)
    t0 = (
        payload.get("timestamp_utc")
        or payload.get("trigger_time")
        or payload.get("alert_datetime")
        or payload.get("t0_utc")
    )
    if not t0:
        raise ValueError("pre-SN payload missing timestamp_utc / trigger_time")

    search_code = str(
        payload.get("search_code")
        or payload.get("search")
        or payload.get("code")
        or SEARCH_CODE_COMBINED
    )
    det_names: list[DetectorName] = []
    if isinstance(payload.get("detectors"), list) and payload["detectors"]:
        for name in payload["detectors"]:
            canon = canonical_detector_name(str(name))
            if canon is not None:
                det_names.append(canon)
    if not det_names:
        det_names = _detectors_for_search_code(search_code)

    n_kl = int(payload.get("n_events_kamland") or payload.get("n_kl") or 0)
    n_sk = int(payload.get("n_events_sk") or payload.get("n_sk") or 0)
    n_by_name = {"KamLAND": n_kl, "Super-K": n_sk}

    hits: list[DetectorHit] = []
    for name in det_names:
        hits.append(
            detector_hit(
                name,
                t_arrival_utc=str(t0),
                n_events=int(n_by_name.get(name, 0)),
                pointing=None,  # arXiv:2404.09920: no directional info from pre-SN
            )
        )

    far = payload.get("false_alarm_rate_per_century")
    if far is None:
        far = payload.get("far_per_century")
    if far is None:
        far = payload.get("false_alarm_rate")
    # Significance: prefer an explicit field; else invert FAR (per century) when present.
    if "significance" in payload and payload["significance"] is not None:
        significance = float(payload["significance"])
    elif far is not None and float(far) > 0:
        significance = float(1.0 / float(far))
    else:
        significance = 0.0

    alert_id = str(
        payload.get("alert_id")
        or payload.get("id")
        or f"presn-{search_code}-{t0}"
    )

    return Alert(
        alert_id=alert_id,
        kind="PRESN",
        source="presn",
        simulated=bool(simulated),
        t0_utc=str(t0),
        detectors=hits,
        significance=significance,
        raw=raw,
    )


def listen_presn_alerts(*, live: bool | None = None) -> Iterator[Alert]:
    """Yield PRESN Alerts from the KamLAND + Super-K joint alert Kafka topic.

    When USE_CACHED_STREAM=True (default), yields nothing and opens no network
    connection — callers should use cache.replay_scenario.
    """
    want_live = (not settings.use_cached_stream) if live is None else bool(live)
    if settings.use_cached_stream or not want_live or not network_allowed():
        return
        yield  # pragma: no cover

    consumer = make_consumer([TOPIC_PRESN_COMBINED])
    for payload in iter_json_messages(consumer):
        yield normalize_presn_payload(payload, simulated=False)
