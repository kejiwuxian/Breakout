"""Simulated bursts per detector (snewpy).

Input → output: Progenitor model + distance → per-detector Alert.
All outputs MUST set simulated=True.
"""

from __future__ import annotations

from typing import Any

from backend.schemas import Alert


def simulate_burst(
    *,
    progenitor_model: str,
    distance_kpc: float,
    alert_id: str,
) -> Alert:
    """Build a simulated SN_BURST Alert with per-detector arrivals.

    Every numeric field from snewpy is simulated; Alert.simulated must be True.
    """
    raise NotImplementedError("simulate_burst is filled in a later prompt.")


def simulate_presn(
    *,
    star_id: str,
    alert_id: str,
    extras: dict[str, Any] | None = None,
) -> Alert:
    """Build a simulated PRESN Alert (Stage 0) for a nearby progenitor."""
    raise NotImplementedError("simulate_presn is filled in a later prompt.")
