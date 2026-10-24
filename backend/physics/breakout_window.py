"""Per-class breakout countdown (estimate).

Class windows (with citations filled when config is completed):
Wolf-Rayet ~ minutes; blue supergiant ~ hours (SN 1987A ~3 h);
red supergiant ~ about 1 day.
"""

from __future__ import annotations

from backend.schemas import BreakoutClassWindow, BreakoutInfo, StarClass


def class_window(star_class: StarClass) -> BreakoutClassWindow:
    """Return the breakout class window label for a progenitor class."""
    raise NotImplementedError("class_window is filled in a later prompt.")


def breakout_countdown(
    star_class: StarClass,
    *,
    t0_utc: str,
) -> BreakoutInfo:
    """Build BreakoutInfo countdown_from the burst time (labeled estimate in UI)."""
    raise NotImplementedError("breakout_countdown is filled in a later prompt.")
