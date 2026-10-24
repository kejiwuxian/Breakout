"""Per-class breakout countdown (estimate).

Class windows from the plan science basis (not star-specific inventions):
Wolf-Rayet ~ minutes; blue supergiant ~ hours (SN 1987A light ~3 h after
neutrinos); red supergiant ~ about 1 day. UI must label these as estimates.
"""

from __future__ import annotations

from backend.schemas import Breakout, BreakoutClassWindow, StarClass

# Documented class → window mapping (BREAKOUT plan / SN 1987A BSG precedent).
CLASS_WINDOWS: dict[StarClass, BreakoutClassWindow] = {
    "WR": "minutes",
    "BSG": "hours",
    "YSG": "hours",
    "RSG": "about 1 day",
    "LBV": "hours",
}


def class_window(star_class: StarClass) -> BreakoutClassWindow:
    """Return the breakout class window label for a progenitor class."""
    return CLASS_WINDOWS[star_class]


def breakout_countdown(
    star_class: StarClass,
    *,
    t0_utc: str,
) -> Breakout:
    """Build Breakout countdown_from the burst time (labeled estimate in UI)."""
    return Breakout(class_window=class_window(star_class), countdown_from=t0_utc)
