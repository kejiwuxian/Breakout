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
DetectorName = Literal["Super-K", "SNO+", "IceCube", "KamLAND", "JUNO"]


# WGS84 lab positions for light-travel triangulation (astropy EarthLocation).
# Underground depth shifts arrival times by only ~µs and is neglected where noted.
# Do not invent coordinates: each entry cites a public source.
DETECTOR_TABLE: dict[str, dict[str, float]] = {
    # Super-Kamiokande, Kamioka Observatory, Japan.
    # Source: Super-Kamiokande site coordinates (36°25′35.3″N 137°18′37.1″E)
    # https://en.wikipedia.org/wiki/Super-Kamiokande (accessed for Cal Hacks build)
    "Super-K": {"lat_deg": 36.426472, "lon_deg": 137.310306, "height_m": 370.0},
    # SNOLAB / SNO+, Creighton Mine, Sudbury, Ontario.
    # Source: SNOLAB location 46°28′30″N 81°11′12″W; lab ~2070 m underground
    # from ~309 m surface elevation → geodetic height ≈ −1761 m.
    # https://www.snolab.ca/ (facility location)
    "SNO+": {"lat_deg": 46.475000, "lon_deg": -81.186667, "height_m": -1761.0},
    # IceCube Neutrino Observatory, geographic South Pole.
    # Source: Amundsen–Scott South Pole Station / IceCube lab elevation ~2835 m.
    # https://icecube.wisc.edu/
    "IceCube": {"lat_deg": -90.0, "lon_deg": 0.0, "height_m": 2835.0},
    # KamLAND, Kamioka Observatory (same complex as Super-K).
    # Source: KamLAND Collaboration coordinates ~36°25′N 137°19′E.
    # https://www.awa.tohoku.ac.jp/kamland/
    "KamLAND": {"lat_deg": 36.422500, "lon_deg": 137.313500, "height_m": 358.0},
    # Jiangmen Underground Neutrino Observatory (JUNO), China.
    # Source: JUNO CDR site 22°07′05.3″N 112°31′07.2″E.
    # https://juno.ihep.ac.cn/
    "JUNO": {"lat_deg": 22.118139, "lon_deg": 112.518667, "height_m": 100.0},
}

# SNOwGLoBES detector configs used by snewpy for expected event counts.
# Mass scales map a SNOwGLoBES config onto our named detector (SIMULATED).
# Super-K ~32.5 kt water vs wc100kt30prct (100 kt); SNO+ ~0.78 kt vs scint20kt;
# KamLAND ~1 kt; JUNO ~20 kt ≈ scint20kt. IceCube maps 1:1.
SNOWGLOBES_DETECTOR_MAP: dict[str, dict[str, float | str]] = {
    "Super-K": {"snowglobes": "wc100kt30prct", "mass_scale": 32.5 / 100.0},
    "SNO+": {"snowglobes": "scint20kt", "mass_scale": 0.78 / 20.0},
    "IceCube": {"snowglobes": "icecube", "mass_scale": 1.0},
    "KamLAND": {"snowglobes": "scint20kt", "mass_scale": 1.0 / 20.0},
    "JUNO": {"snowglobes": "scint20kt", "mass_scale": 1.0},
}

# Timing uncertainty used in simulated Alerts (ms). Not real measured
# resolutions for every channel; labeled via Alert.simulated=true.
DEFAULT_T_ERR_MS: dict[str, float] = {
    "Super-K": 1.0,
    "SNO+": 1.0,
    "IceCube": 5.0,
    "KamLAND": 1.5,
    "JUNO": 1.0,
}

# HEALPix resolution for localization maps (NESTED ordering).
HEALPIX_NSIDE: int = 64

# ---------------------------------------------------------------------------
# Breakout countdown class windows (UI labels; estimates, not star-specific
# inventions). countdown_from is always the burst t0 from the Alert.
#
# Citations (ADS bibcodes — no bibcode, no claim):
# - WR → "minutes": compact/stripped envelopes yield short shock-breakout and
#   early-emission timescales (Nakar & Sari 2010, ADS 2010ApJ...725..904N).
# - BSG → "hours": SN 1987A (BSG progenitor) — neutrino burst then optical
#   discovery on an hours-scale timeline (Hirata et al. 1987,
#   ADS 1987PhRvL..58.1490H; Bionta et al. 1987, ADS 1987PhRvL..58.1494B).
# - RSG → "about 1 day": extended RSG envelopes imply longer diffusion /
#   early optical rise than compact progenitors (Nakar & Sari 2010,
#   ADS 2010ApJ...725..904N).
# YSG/LBV inherit the hours-scale BSG-like label as a conservative plan default
# (same Nakar & Sari compact-vs-extended framing; not a separate measurement).
CLASS_WINDOWS: dict[str, str] = {
    "WR": "minutes",
    "BSG": "hours",
    "YSG": "hours",
    "RSG": "about 1 day",
    "LBV": "hours",
    # AGN/blazar: no CCSN optical breakout; use hours as a follow-up estimate label.
    "AGN": "hours",
}

# IR follow-up when catalog A_V is high enough that optical discovery is likely
# suppressed. Operational BREAKOUT threshold — not a universal published cutoff
# and never used to invent a missing A_V (null → no IR flag).
# Source note: dust-obscured CCSNe motivate IR searches; see e.g. the review
# context in Jencson et al. 2019 (ADS 2019ApJ...886...40J) on IR-selected
# obscured SNe. Threshold value itself is BREAKOUT's follow-up heuristic.
AV_IR_THRESHOLD_MAG: float = 1.0
AV_IR_THRESHOLD_SOURCE: str = (
    "BREAKOUT operational A_V>=1.0 mag heuristic; context ADS 2019ApJ...886...40J; "
    "null extinction_av_mag never invented"
)

# Ranking priors for literature/rerank.py (dimensionless; NOT observational rates).
# Posterior ∝ p_sky × w_class × w_lit × w_watch, then normalized over candidates.
# w_lit = RANKING_W_LIT_FLOOR + RANKING_W_LIT_SCALE * index.confidence
# so zero-confidence stars stay alive but rank below high-confidence ones.
RANKING_CLASS_WEIGHT: dict[str, float] = {
    "RSG": 1.0,
    "BSG": 0.9,
    "YSG": 0.85,
    "WR": 0.8,
    "LBV": 0.75,
    "AGN": 0.7,
}
RANKING_WATCH_BOOST: float = 2.0  # w_watch for presn_watch / watchlist stars
RANKING_W_LIT_FLOOR: float = 0.25
RANKING_W_LIT_SCALE: float = 0.75


class Settings(BaseModel):
    """Application settings read once at process start."""

    use_cached_stream: bool = Field(
        default=True,
        description=(
            "Offline capability: use data/cache/ fixtures with no network on the "
            "trigger path. Does not auto-play; start scenarios manually "
            "(or set BREAKOUT_AUTOSTART=1)."
        ),
    )
    scenario: str = Field(
        default="scenario_a_galactic_ccsn",
        description="Cache scenario directory name under data/cache/ (manual Replay).",
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
    hop_username: str = ""
    hop_password: str = ""
    hop_snews_topic: str = "kafka://kafka.scimma.org/snews2.alert"
    subscribe_icecube_test: bool = False
    lcogt_api_token: str = ""
    lcogt_proposal: str = ""
    notify_dry_run: bool = True
    smtp_host: str = ""

    detector_table: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {k: dict(v) for k, v in DETECTOR_TABLE.items()}
    )
    healpix_nside: int = Field(
        default=HEALPIX_NSIDE,
        description="HEALPix Nside for NESTED localization maps.",
    )
    class_windows: dict[str, str] = Field(
        default_factory=lambda: dict(CLASS_WINDOWS),
        description="Progenitor class → breakout window label (estimates).",
    )
    av_ir_threshold_mag: float = Field(
        default=AV_IR_THRESHOLD_MAG,
        description="A_V (mag) at/above which ir_followup is recommended.",
    )
    ranking_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "watch_boost": RANKING_WATCH_BOOST,
            "w_lit_floor": RANKING_W_LIT_FLOOR,
            "w_lit_scale": RANKING_W_LIT_SCALE,
            **{f"class_{k}": v for k, v in RANKING_CLASS_WEIGHT.items()},
        },
        description="Dimensionless ranking priors for rerank (not rates).",
    )


def load_settings() -> Settings:
    """Read .env (if present) and return typed Settings."""
    _load_dotenv()
    voice_raw = _env_str("VOICE_MODE", "live").lower()
    voice_mode: VoiceMode
    if voice_raw in ("live", "cached", "off"):
        voice_mode = voice_raw  # type: ignore[assignment]
    else:
        voice_mode = "live"

    nside_raw = _env_str("HEALPIX_NSIDE", str(HEALPIX_NSIDE))
    try:
        healpix_nside = int(nside_raw) if nside_raw else HEALPIX_NSIDE
    except ValueError:
        healpix_nside = HEALPIX_NSIDE

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
        hop_username=_env_str("HOP_USERNAME", ""),
        hop_password=_env_str("HOP_PASSWORD", ""),
        hop_snews_topic=_env_str(
            "HOP_SNEWS_TOPIC", "kafka://kafka.scimma.org/snews2.alert"
        ),
        subscribe_icecube_test=_env_bool("SUBSCRIBE_ICECUBE_TEST", False),
        lcogt_api_token=_env_str("LCOGT_API_TOKEN", ""),
        lcogt_proposal=_env_str("LCOGT_PROPOSAL", ""),
        notify_dry_run=_env_bool("NOTIFY_DRY_RUN", True),
        smtp_host=_env_str("SMTP_HOST", ""),
        healpix_nside=healpix_nside,
    )


settings = load_settings()
