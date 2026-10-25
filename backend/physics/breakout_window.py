"""Per-class breakout countdown (estimate).

Maps progenitor class → class_window label. Values and citations live in
``backend.config.CLASS_WINDOWS`` (ADS bibcodes in comments). countdown_from is
the burst ``t0`` from the Alert. UI must label these as estimates — they are
order-of-magnitude windows, not star-specific inventions.

Non-stellar sources (BLAZAR) skip the breakout clock: class_window = "n/a".
"""

from __future__ import annotations

from typing import cast

from backend.config import CLASS_WINDOWS, settings
from backend.schemas import Breakout, BreakoutClassWindow, StarClass

_VALID_WINDOWS: set[str] = {"minutes", "hours", "about 1 day", "n/a"}

NON_STELLAR_CLASSES: frozenset[str] = frozenset({"BLAZAR"})


def is_non_stellar(star_class: str) -> bool:
    """True when the candidate is not a stellar progenitor (no breakout clock)."""
    return str(star_class) in NON_STELLAR_CLASSES


def class_window(star_class: StarClass | str) -> BreakoutClassWindow:
    """Return the breakout class window label for a progenitor class."""
    if is_non_stellar(str(star_class)):
        return "n/a"
    windows = settings.class_windows or CLASS_WINDOWS
    key = str(star_class)
    raw = windows.get(key) or CLASS_WINDOWS.get(key) or CLASS_WINDOWS["RSG"]
    if raw not in _VALID_WINDOWS:
        raw = CLASS_WINDOWS.get(key, "about 1 day")
    return cast(BreakoutClassWindow, raw)


def breakout_countdown(
    star_class: StarClass | str,
    *,
    t0_utc: str,
) -> Breakout:
    """Build Breakout with countdown_from = burst t0 (labeled estimate in UI).

    For non-stellar classes, returns class_window=\"n/a\" so the UI skips the
    optical-breakout clock.
    """
    return Breakout(class_window=class_window(star_class), countdown_from=t0_utc)
