"""SNEWS 2.0 alert listener.

Input → output: Live SNEWS stream → Alert.
Libraries: gcn-kafka / SNEWS 2.0 client; no network when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

from typing import Any, Iterator

from backend.schemas import Alert


def listen_snews_alerts(*, live: bool = False) -> Iterator[Alert]:
    """Yield Alerts from the SNEWS 2.0 stream.

    Offline mode must not open network sockets; use cache replay instead.
    """
    if not live:
        return
        yield  # pragma: no cover
    raise NotImplementedError("Live SNEWS listener is filled in a later prompt.")


def normalize_snews_payload(payload: dict[str, Any], *, simulated: bool) -> Alert:
    """Normalize a raw SNEWS payload into an Alert schema object."""
    raise NotImplementedError("normalize_snews_payload is filled in a later prompt.")
