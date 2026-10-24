"""Runtime configuration from environment / .env.

Defaults match the Offline cache and run section of the Phase 1 plan Page.
Secrets stay in .env (gitignored); empty keys are fine when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def _load_dotenv(path: Path = ENV_PATH) -> None:
    """Load KEY=VALUE pairs from .env into os.environ if the file exists."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Do not override variables already set in the process environment.
        if key and key not in os.environ:
            os.environ[key] = value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip()


VoiceMode = Literal["live", "cached", "off"]


class Settings(BaseModel):
    """Application settings read once at process start."""

    use_cached_stream: bool = Field(
        default=True,
        description="Replay data/cache/; no network on the trigger path.",
    )
    scenario: str = Field(
        default="scenario_a_galactic_ccsn",
        description="Cache scenario directory name under data/cache/.",
    )
    lcogt_dry_run: bool = Field(
        default=True,
        description="Build LCOGT RequestGroup JSON without submitting.",
    )
    voice_mode: VoiceMode = Field(
        default="live",
        description="Grok Voice mode: live | cached | off.",
    )
    xai_voice_model: str = Field(
        default="grok-voice-latest",
        description="Realtime voice model alias.",
    )
    xai_tts_voice: str = Field(
        default="eve",
        description="TTS voice_id for the announcer.",
    )
    ads_api_token: str = ""
    xai_api_key: str = ""
    gcn_client_id: str = ""
    gcn_client_secret: str = ""
    lcogt_api_token: str = ""
    lcogt_proposal: str = ""

    # Detector table, class windows, and ranking weights are filled in later
    # prompts; placeholders keep the settings object complete for stubs.
    detector_table: dict[str, dict[str, float]] = Field(default_factory=dict)
    class_windows: dict[str, str] = Field(
        default_factory=lambda: {
            "WR": "minutes",
            "BSG": "hours",
            "RSG": "about 1 day",
        }
    )
    ranking_weights: dict[str, float] = Field(default_factory=dict)


def load_settings() -> Settings:
    """Read .env (if present) and return typed Settings."""
    _load_dotenv()
    voice_raw = _env_str("VOICE_MODE", "live").lower()
    voice_mode: VoiceMode
    if voice_raw in ("live", "cached", "off"):
        voice_mode = voice_raw  # type: ignore[assignment]
    else:
        voice_mode = "live"

    return Settings(
        use_cached_stream=_env_bool("USE_CACHED_STREAM", True),
        scenario=_env_str("SCENARIO", "scenario_a_galactic_ccsn"),
        lcogt_dry_run=_env_bool("LCOGT_DRY_RUN", True),
        voice_mode=voice_mode,
        xai_voice_model=_env_str("XAI_VOICE_MODEL", "grok-voice-latest"),
        xai_tts_voice=_env_str("XAI_TTS_VOICE", "eve"),
        ads_api_token=_env_str("ADS_API_TOKEN", ""),
        xai_api_key=_env_str("XAI_API_KEY", ""),
        gcn_client_id=_env_str("GCN_CLIENT_ID", ""),
        gcn_client_secret=_env_str("GCN_CLIENT_SECRET", ""),
        lcogt_api_token=_env_str("LCOGT_API_TOKEN", ""),
        lcogt_proposal=_env_str("LCOGT_PROPOSAL", ""),
    )


settings = load_settings()
