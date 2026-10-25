"""Unified realtime ingest: every public channel BREAKOUT can subscribe to.

Channels (when ``USE_CACHED_STREAM=False`` and credentials are present):

1. GCN Kafka JSON — SNEWS2 coincidence, IceCube gold/bronze, pre-SN combined
2. GCN Classic-over-Kafka text — legacy ``gcn.classic.text.SNEWS``
3. Optional SCiMMA Hopskotch — ``snews2.alert`` when ``HOP_USERNAME`` /
   ``HOP_PASSWORD`` are set (``hop`` optional dependency)

Per-detector SNEWS experiment feeds are **member-only** and are not
subscribed here. Localization for multi-detector SNEWS2 JSON alerts uses
DiffPointing inside ``localize.fuse``; classic notices use Super-K pointing
when RA/Dec are present.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from backend.config import settings
from backend.ingest import gcn_kafka, presn, snews
from backend.ingest.gcn_common import (
    TOPIC_CLASSIC_SNEWS_TEXT,
    TOPIC_ICECUBE_GOLD_BRONZE,
    TOPIC_PRESN_COMBINED,
    TOPIC_SNEWS2_COINCIDENCE,
    iter_topic_messages,
    make_consumer,
    network_allowed,
)
from backend.ingest.snews_classic import try_parse_classic_snews
from backend.schemas import Alert

logger = logging.getLogger("breakout.ingest.live_channels")

# Production GCN topics we can consume without inventing credentials/topics.
LIVE_GCN_TOPICS: tuple[str, ...] = (
    TOPIC_SNEWS2_COINCIDENCE,
    TOPIC_ICECUBE_GOLD_BRONZE,
    TOPIC_PRESN_COMBINED,
    TOPIC_CLASSIC_SNEWS_TEXT,
)

# Optional IceCube test stream (firedrills); enabled via env.
TOPIC_ICECUBE_TEST = "gcn.notices.icecube.test.gold_bronze_track_alerts"


def live_gcn_topics() -> list[str]:
    """Return the GCN Kafka topic list for this process."""
    topics = list(LIVE_GCN_TOPICS)
    if getattr(settings, "subscribe_icecube_test", False):
        topics.append(TOPIC_ICECUBE_TEST)
    return topics


def _route_gcn_message(topic: str, payload: Any) -> Alert | None:
    """Map one Kafka message onto an Alert, or None if unusable."""
    if topic == TOPIC_CLASSIC_SNEWS_TEXT or (
        isinstance(payload, str) and "SNEWS" in payload.upper()
    ):
        return try_parse_classic_snews(payload, simulated=None)

    if not isinstance(payload, dict):
        # Classic text already handled; binary/unknown skipped.
        return None

    schema = str(payload.get("$schema") or "").lower()
    mission = str(payload.get("mission") or "").lower()

    if topic == TOPIC_SNEWS2_COINCIDENCE or "snews2" in schema or mission == "snews":
        if payload.get("snews2_tier") or "detector_status" in payload or "detector_names" in payload:
            return snews.normalize_snews_payload(payload, simulated=False)

    if topic in (TOPIC_ICECUBE_GOLD_BRONZE, TOPIC_ICECUBE_TEST) or "icecube" in schema:
        if payload.get("ra") is not None and payload.get("dec") is not None:
            return gcn_kafka.normalize_gcn_payload(payload, simulated=False)

    if topic == TOPIC_PRESN_COMBINED or "presn" in schema:
        return presn.normalize_presn_payload(payload, simulated=False)

    # Fallback heuristics for mis-routed JSON.
    if payload.get("snews2_tier") or mission == "snews":
        return snews.normalize_snews_payload(payload, simulated=False)
    if payload.get("ra") is not None and mission == "icecube":
        return gcn_kafka.normalize_gcn_payload(payload, simulated=False)
    return None


def listen_gcn_live_alerts(*, live: bool | None = None) -> Iterator[Alert]:
    """Yield Alerts from all configured GCN Kafka topics (one consumer)."""
    want_live = (not settings.use_cached_stream) if live is None else bool(live)
    if settings.use_cached_stream or not want_live or not network_allowed():
        return
        yield  # pragma: no cover

    topics = live_gcn_topics()
    logger.info("gcn_live_subscribe topics=%s", topics)
    consumer = make_consumer(topics)
    for topic, payload in iter_topic_messages(consumer):
        try:
            alert = _route_gcn_message(topic, payload)
        except Exception:
            logger.exception("gcn_route_failed topic=%s", topic)
            continue
        if alert is None:
            logger.debug("gcn_skip topic=%s", topic)
            continue
        logger.info(
            "gcn_alert topic=%s id=%s kind=%s simulated=%s",
            topic,
            alert.alert_id,
            alert.kind,
            alert.simulated,
        )
        yield alert


def listen_hop_snews_alerts(*, live: bool | None = None) -> Iterator[Alert]:
    """Yield Alerts from SCiMMA Hopskotch ``snews2.alert`` when configured.

    Requires optional ``hop`` package and ``HOP_USERNAME`` / ``HOP_PASSWORD``.
    No-ops when credentials or package are missing (does not invent a stream).
    """
    want_live = (not settings.use_cached_stream) if live is None else bool(live)
    if settings.use_cached_stream or not want_live or not network_allowed():
        return
        yield  # pragma: no cover

    user = (getattr(settings, "hop_username", "") or "").strip()
    password = (getattr(settings, "hop_password", "") or "").strip()
    if not user or not password:
        logger.info("hop_snews_skip reason=missing_credentials")
        return
        yield  # pragma: no cover

    try:
        from hop import stream  # type: ignore[import-untyped]
        from hop.auth import Auth  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("hop_snews_skip reason=hop_not_installed")
        return
        yield  # pragma: no cover

    topic = (getattr(settings, "hop_snews_topic", "") or "kafka://kafka.scimma.org/snews2.alert").strip()
    auth = Auth(user, password)
    logger.info("hop_snews_subscribe topic=%s", topic)
    with stream.open(topic, "r", auth=auth) as s:
        for message in s:
            content = message.content
            payloads = content if isinstance(content, list) else [content]
            for payload in payloads:
                if isinstance(payload, (bytes, bytearray)):
                    try:
                        payload = json.loads(payload.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except json.JSONDecodeError:
                        alert = try_parse_classic_snews(payload)
                        if alert is not None:
                            yield alert
                        continue
                if not isinstance(payload, dict):
                    continue
                try:
                    yield snews.normalize_snews_payload(payload, simulated=False)
                except Exception:
                    logger.exception("hop_snews_normalize_failed")


def listen_all_live_alerts(*, live: bool | None = None) -> Iterator[tuple[str, Alert]]:
    """Yield ``(channel, Alert)`` from every configured realtime source.

    GCN is the primary path. Hopskotch is an additional channel when wired.
    Callers that need a single multiplexed pump should run each listener in
    its own thread (see ``backend.app._start_live_listeners``).
    """
    for alert in listen_gcn_live_alerts(live=live):
        yield ("gcn", alert)
    for alert in listen_hop_snews_alerts(live=live):
        yield ("hop_snews", alert)
