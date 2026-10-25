"""Shared GCN Kafka helpers for live ingest modules.

Credentials come only from Settings / .env (GCN_CLIENT_ID, GCN_CLIENT_SECRET).
When USE_CACHED_STREAM=True, no Consumer is constructed and no sockets open.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from backend.config import DETECTOR_TABLE, DEFAULT_T_ERR_MS, settings
from backend.schemas import DetectorHit, DetectorName, Pointing

# Canonical Kafka topics (GCN Unified Schema / mission docs).
TOPIC_SNEWS2_COINCIDENCE = "gcn.notices.snews2.coincidence"
TOPIC_ICECUBE_GOLD_BRONZE = "gcn.notices.icecube.gold_bronze_track_alerts"
TOPIC_ICECUBE_CASCADE = "gcn.classic.text.ICECUBE_CASCADE"
TOPIC_SUPERK_SN = "gcn.notice.superk.sn_alert"
# Pre-SN combined alert is documented as GCN circular + registered text feed
# (arXiv:2404.09920); Kafka topic name reserved for when GCN publishes JSON.
TOPIC_PRESN_COMBINED = "gcn.notices.presn.kamland_superk"
# GCN Classic-over-Kafka (legacy SNEWS POSITION / EVENT notices).
TOPIC_CLASSIC_SNEWS_TEXT = "gcn.classic.text.SNEWS"

DETECTOR_NAME_ALIASES: dict[str, DetectorName] = {
    "super-k": "Super-K",
    "superk": "Super-K",
    "super-kamiokande": "Super-K",
    "sk": "Super-K",
    "kamland": "KamLAND",
    "icecube": "IceCube",
    "ice cube": "IceCube",
    "sno+": "SNO+",
    "snoplus": "SNO+",
    "juno": "JUNO",
}


class CachedStreamError(RuntimeError):
    """Raised when live ingest is requested while USE_CACHED_STREAM=True."""


def network_allowed() -> bool:
    """False when offline/cached mode is on — callers must not open sockets."""
    return not settings.use_cached_stream


def require_live_network() -> None:
    """Refuse to connect when USE_CACHED_STREAM=True."""
    if settings.use_cached_stream:
        raise CachedStreamError(
            "USE_CACHED_STREAM=True: live GCN Kafka ingest is disabled; "
            "use backend.ingest.cache.replay_scenario instead."
        )


def gcn_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) from settings/.env only."""
    client_id = (settings.gcn_client_id or "").strip()
    client_secret = (settings.gcn_client_secret or "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "Live GCN ingest requires GCN_CLIENT_ID and GCN_CLIENT_SECRET in .env"
        )
    return client_id, client_secret


def make_consumer(topics: list[str]) -> Any:
    """Construct a gcn_kafka.Consumer subscribed to topics (live only)."""
    require_live_network()
    client_id, client_secret = gcn_credentials()
    from gcn_kafka import Consumer  # local import: avoid import side effects offline

    consumer = Consumer(client_id=client_id, client_secret=client_secret)
    consumer.subscribe(topics)
    return consumer


def _decode_message_value(raw: Any) -> Any:
    """Decode Kafka message value to dict (JSON) or str (classic text)."""
    if raw is None:
        return None
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    elif isinstance(raw, str):
        text = raw
    elif isinstance(raw, dict):
        return raw
    else:
        return raw
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def iter_json_messages(consumer: Any, *, timeout_s: float = 1.0) -> Iterator[dict[str, Any]]:
    """Yield decoded JSON dicts from a gcn-kafka Consumer."""
    for _topic, payload in iter_topic_messages(consumer, timeout_s=timeout_s):
        if isinstance(payload, dict):
            yield payload


def iter_topic_messages(
    consumer: Any, *, timeout_s: float = 1.0
) -> Iterator[tuple[str, Any]]:
    """Yield ``(topic, payload)`` for JSON objects or classic text strings."""
    while True:
        for message in consumer.consume(timeout=timeout_s):
            if message.error():
                continue
            raw = message.value()
            if raw is None:
                continue
            payload = _decode_message_value(raw)
            topic = ""
            try:
                topic = str(message.topic())
            except Exception:
                topic = ""
            yield topic, payload


def canonical_detector_name(name: str) -> DetectorName | None:
    """Map free-text detector labels onto Alert DetectorName values."""
    key = name.strip().lower()
    if name in DETECTOR_TABLE:
        return name  # type: ignore[return-value]
    return DETECTOR_NAME_ALIASES.get(key)


def detector_hit(
    name: DetectorName,
    *,
    t_arrival_utc: str,
    n_events: int = 0,
    pointing: Pointing | None = None,
    t_err_ms: float | None = None,
) -> DetectorHit:
    """Build a DetectorHit using WGS84 coordinates from DETECTOR_TABLE."""
    row = DETECTOR_TABLE[name]
    return DetectorHit(
        name=name,
        lat_deg=float(row["lat_deg"]),
        lon_deg=float(row["lon_deg"]),
        height_m=float(row["height_m"]),
        t_arrival_utc=t_arrival_utc,
        t_err_ms=float(DEFAULT_T_ERR_MS[name] if t_err_ms is None else t_err_ms),
        n_events=int(n_events),
        pointing=pointing,
    )
