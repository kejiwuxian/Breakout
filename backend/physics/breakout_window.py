"""Per-class breakout countdown (estimate).

Maps progenitor class → class_window label. Values and citations live in
``backend.config.CLASS_WINDOWS`` (ADS bibcodes in comments). countdown_from is
the burst ``t0`` from the Alert. UI must label these as estimates — they are
order-of-magnitude windows, not star-specific inventions.
"""

from __future__ import annotations

from typing import cast

from backend.config import CLASS_WINDOWS, settings
from backend.schemas import Breakout, BreakoutClassWindow, StarClass

_VALID_WINDOWS: set[str] = {"minutes", "hours", "about 1 day", "n/a"}


def class_window(star_class: StarClass | str) -> BreakoutClassWindow:
    """Return the breakout class window label for a progenitor class.

    Unknown / field-catalog classes (``UNK``) resolve to ``n/a`` — not the RSG
    default — so AOI field stars do not inherit Betelgeuse-like life/breakout.
    """
    windows = settings.class_windows or CLASS_WINDOWS
    key = str(star_class)
    raw = windows.get(key) or CLASS_WINDOWS.get(key)
    if raw is None or raw not in _VALID_WINDOWS:
        # Last resort for truly unknown class strings: absent, not RSG clone.
        raw = CLASS_WINDOWS.get(key, "n/a")
        if raw not in _VALID_WINDOWS:
            raw = "n/a"
    return cast(BreakoutClassWindow, raw)


def breakout_countdown(
    star_class: StarClass | str,
    *,
    t0_utc: str,
) -> Breakout:
    """Build Breakout with countdown_from = burst t0 (labeled estimate in UI)."""
    return Breakout(class_window=class_window(star_class), countdown_from=t0_utc)
