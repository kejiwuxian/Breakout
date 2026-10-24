"""Replay recorded scenarios from data/cache/.

Input → output: data/cache/<scenario> → timed Alert replay.
No LLM or network calls; used when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from backend.config import ROOT
from backend.schemas import Alert

CACHE_ROOT = ROOT / "data" / "cache"


def scenario_dir(scenario: str) -> Path:
    """Return the absolute path to a named cache scenario."""
    return CACHE_ROOT / scenario


def load_alerts(scenario: str) -> list[Alert]:
    """Load Alert objects from data/cache/<scenario>/alerts.jsonl.

    Each line is one Alert JSON object. Simulated vs real is per-record
    via the simulated field; do not invent values.
    """
    raise NotImplementedError("load_alerts is filled in a later prompt.")


def replay_scenario(
    scenario: str,
    *,
    realtime: bool = True,
) -> Iterator[Alert]:
    """Yield Alerts from a cached scenario, optionally on a timer.

    realtime=True spaces emissions using recorded timestamps; False yields
    immediately for tests.
    """
    raise NotImplementedError("replay_scenario is filled in a later prompt.")
    yield  # pragma: no cover
