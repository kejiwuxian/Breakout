"""Super-K directional estimate as a HEALPix map."""

from __future__ import annotations

import numpy as np

from backend.schemas import Alert, Pointing


def pointing_map(
    pointing: Pointing,
    *,
    nside: int = 64,
) -> np.ndarray:
    """Convert a Super-K pointing + error into a NESTED HEALPix map (sums to 1)."""
    raise NotImplementedError("pointing_map is filled in a later prompt.")


def extract_superk_pointing(alert: Alert) -> Pointing | None:
    """Return the Super-K pointing from an Alert, if present."""
    for det in alert.detectors:
        if det.name == "Super-K" and det.pointing is not None:
            return det.pointing
    return None
