"""Pairwise timing rings from detector arrival differences.

Triangulation is light-travel time across Earth (at most about 42 ms).
cos θ = (c · Δt) / d for baseline d and arrival difference Δt.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.schemas import Alert


def pairwise_baselines(alert: Alert) -> list[dict[str, Any]]:
    """Return detector-pair baselines and Δt (ms) for an Alert."""
    raise NotImplementedError("pairwise_baselines is filled in a later prompt.")


def timing_ring_map(
    alert: Alert,
    *,
    pair: tuple[str, str],
    nside: int = 64,
) -> np.ndarray:
    """Build a NESTED HEALPix probability band for one detector pair.

    The returned map must sum to 1. Uses light-travel geometry only.
    """
    raise NotImplementedError("timing_ring_map is filled in a later prompt.")
