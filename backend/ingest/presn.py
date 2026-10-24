"""Stage 0: pre-SN alert listener (KamLAND + Super-K joint alert).

Input → output: Pre-SN alert → Alert (kind=PRESN).
Libraries: gcn-kafka (live); no network when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

from typing import Any, Iterator

from backend.schemas import Alert


def listen_presn_alerts(*, live: bool = False) -> Iterator[Alert]:
    """Yield PRESN Alerts from the KamLAND + Super-K joint alert path.

    When live is False (cached / offline mode), this stub yields nothing;
    use ingest.cache.replay_scenario instead.
    """
    if not live:
        return
        yield  # pragma: no cover
    raise NotImplementedError("Live pre-SN listener is filled in a later prompt.")


def normalize_presn_payload(payload: dict[str, Any], *, simulated: bool) -> Alert:
    """Normalize a raw pre-SN payload into an Alert schema object."""
    raise NotImplementedError("normalize_presn_payload is filled in a later prompt.")
