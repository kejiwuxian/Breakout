"""Event → scripted line → Grok TTS audio, pushed to the UI.

Spoken lines come from data/voice/announcer_lines.json filled only with real
payload fields; say "simulated" when the payload is simulated.
Runs after the pipeline and never blocks it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.config import ROOT

LINES_PATH = ROOT / "data" / "voice" / "announcer_lines.json"


def load_announcer_lines(path: Path = LINES_PATH) -> dict[str, str]:
    """Load Barron's announcer script templates."""
    raise NotImplementedError("load_announcer_lines is filled in a later prompt.")


def render_line(template: str, payload: dict[str, Any]) -> str:
    """Fill a template only with real payload fields; never invent numbers."""
    raise NotImplementedError("render_line is filled in a later prompt.")


def speak(
    event_type: str,
    payload: dict[str, Any],
    *,
    voice_mode: str,
    voice_id: str = "eve",
) -> dict[str, Any]:
    """Produce announcer audio/caption for an event.

    voice_mode=live calls xAI TTS; cached plays pre-rendered clips; off is
    captions only. Returns a voice event dict for /ws/events.
    """
    raise NotImplementedError("speak is filled in a later prompt.")
