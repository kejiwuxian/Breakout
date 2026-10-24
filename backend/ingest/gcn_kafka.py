"""GCN Kafka consumer (gcn-kafka).

Input → output: Live GCN Kafka notices → Alert.
No network when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

from typing import Any, Iterator

from backend.schemas import Alert


def listen_gcn_alerts(*, live: bool = False) -> Iterator[Alert]:
    """Yield Alerts from GCN Kafka topics.

    Requires GCN_CLIENT_ID / GCN_CLIENT_SECRET only in live mode.
    """
    if not live:
        return
        yield  # pragma: no cover
    raise NotImplementedError("Live GCN Kafka consumer is filled in a later prompt.")


def normalize_gcn_payload(payload: dict[str, Any], *, simulated: bool) -> Alert:
    """Normalize a GCN notice payload into an Alert schema object."""
    raise NotImplementedError("normalize_gcn_payload is filled in a later prompt.")
