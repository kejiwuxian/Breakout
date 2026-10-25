"""Unified realtime ingest: every public channel BREAKOUT can subscribe to.

Channels (when ``USE_CACHED_STREAM=False`` and credentials are present):

1. GCN Kafka JSON — IceCube gold/bronze and Super-K burst notices
2. GCN Classic-over-Kafka text — SNEWS and IceCube cascades
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
    TOPIC_ICECUBE_CASCADE,
    TOPIC_SUPERK_SN,
    TOPIC_PRESN_COMBINED,
    TOPIC_SNEWS2_COINCIDENCE,
    iter_topic_messages,
    make_consumer,
    network_allowed,
)
from backend.ingest.snews_classic import try_parse_classic_snews
from backend.ingest.observatory_notices import notice_category, normalize_cascade_text, normalize_superk_payload
from backend.ingest.source_status import TOPIC_SOURCE, mark_source_state, note_source_message
from backend.schemas import Alert

logger = logging.getLogger("breakout.ingest.live_channels")

# Production GCN topics we can consume without inventing credentials/topics.
LIVE_GCN_TOPICS: tuple[str, ...] = (
    TOPIC_ICECUBE_GOLD_BRONZE,
    TOPIC_ICECUBE_CASCADE,
    TOPIC_SUPERK_SN,
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
    if notice_category(payload, topic) != "science":
        return None
    if topic == TOPIC_ICECUBE_CASCADE and isinstance(payload, str):
        return normalize_cascade_text(payload)
    if topic == TOPIC_CLASSIC_SNEWS_TEXT or (
        isinstance(payload, str) and "SNEWS" in payload.upper()
    ):
        return try_parse_classic_snews(payload, simulated=None)

    if not isinstance(payload, dict):
        # Classic text already handled; binary/unknown skipped.
        return None

    schema = str(payload.get("$schema") or "").lower()
    mission = str(payload.get("mission") or "").lower()

    if topic == TOPIC_SUPERK_SN:
        return normalize_superk_payload(payload)

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
    source_ids = list({TOPIC_SOURCE[topic] for topic in topics if topic in TOPIC_SOURCE})
    mark_source_state(source_ids, "starting")
    consumer = None
    try:
        consumer = make_consumer(topics)
        for topic, payload in iter_topic_messages(consumer):
            source_id = TOPIC_SOURCE.get(topic)
            category = notice_category(payload, topic)
            if source_id:
                note_source_message(source_id, category=category if category != "science" else "traffic")
            if category != "science":
                logger.info("gcn_non_science_notice topic=%s category=%s", topic, category)
                continue
            try:
                alert = _route_gcn_message(topic, payload)
            except Exception:
                logger.exception("gcn_route_failed topic=%s", topic)
                continue
            if alert is None or alert.simulated:
                logger.debug("gcn_skip topic=%s", topic)
                continue
            if source_id:
                note_source_message(source_id, category="science")
            alert.raw["ingest_topic"] = topic
            logger.info("gcn_alert topic=%s id=%s kind=%s simulated=%s", topic, alert.alert_id, alert.kind, alert.simulated)
            yield alert
    except Exception:
        mark_source_state(source_ids, "error")
        raise
    finally:
        if consumer is not None:
            consumer.close()


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
        mark_source_state(["snews_hop"], "error")
        return
        yield  # pragma: no cover

    topic = (getattr(settings, "hop_snews_topic", "") or "kafka://kafka.scimma.org/snews2.alert").strip()
    auth = Auth(user, password)
    logger.info("hop_snews_subscribe topic=%s", topic)
    mark_source_state(["snews_hop"], "starting")
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
                        category = notice_category(payload)
                        note_source_message("snews_hop", category=category if category != "science" else "traffic")
                        if alert is not None and not alert.simulated and category == "science":
                            note_source_message("snews_hop", category="science")
                            yield alert
                        continue
                if not isinstance(payload, dict):
                    continue
                category = notice_category(payload)
                note_source_message("snews_hop", category=category if category != "science" else "traffic")
                if category != "science":
                    continue
                try:
                    alert = snews.normalize_snews_payload(payload, simulated=False)
                    note_source_message("snews_hop", category="science")
                    yield alert
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
