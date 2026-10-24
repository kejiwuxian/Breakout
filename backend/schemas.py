"""Pydantic models for Alert, SkyMap, and CandidateScore v1.

Contract freeze between Light's pipeline and Tony's ranking code.
Any later field change needs a version bump and a note in docs/schemas.md.

Every module reads and writes these shapes. Any value from a simulation
carries simulated=true (UI shows a Simulated badge).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Bump this and document the change in docs/schemas.md when fields change.
CONTRACT_VERSION = "v1"

AlertKind = Literal["PRESN", "SN_BURST", "HE_NEUTRINO"]
AlertSource = Literal["presn", "snews2", "gcn_kafka", "snewpy_sim", "cache"]
DetectorName = Literal["Super-K", "SNO+", "IceCube", "KamLAND", "JUNO"]
StarClass = Literal["RSG", "BSG", "YSG", "WR", "LBV"]
BreakoutClassWindow = Literal["minutes", "hours", "about 1 day"]


class Pointing(BaseModel):
    """Directional estimate in ICRS degrees."""

    ra_deg: float
    dec_deg: float
    err_deg: float


class DetectorHit(BaseModel):
    """One detector's contribution to an Alert (WGS84 position + arrival)."""

    name: DetectorName
    lat_deg: float
    lon_deg: float
    height_m: float
    t_arrival_utc: str
    t_err_ms: float
    n_events: int
    pointing: Pointing | None = None


class Alert(BaseModel):
    """Emitted by every ingest source; consumed by localize/."""

    alert_id: str
    kind: AlertKind
    source: AlertSource
    simulated: bool = Field(
        ...,
        description="True when any value is from a simulation; UI must label it.",
    )
    t0_utc: str
    detectors: list[DetectorHit]
    significance: float
    raw: dict[str, Any] = Field(default_factory=dict)


class SkyPeak(BaseModel):
    """Peak of a fused HEALPix sky map (ICRS degrees)."""

    ra_deg: float
    dec_deg: float


class SkyMap(BaseModel):
    """Output of localize/fuse.py (healpy NESTED map, sums to 1)."""

    alert_id: str
    nside: int = 64
    ordering: Literal["NESTED"] = "NESTED"
    frame: Literal["ICRS"] = "ICRS"
    prob_path: str
    components: list[str]
    credible_90_deg2: float
    peak: SkyPeak
    simulated: bool = False


class Evidence(BaseModel):
    """One literature claim; bibcode is required (no bibcode, no claim)."""

    bibcode: str = Field(..., min_length=1, description="ADS bibcode")
    claim: str = Field(..., min_length=1)


class Literature(BaseModel):
    """Precomputed offline literature scores (each 0..1) plus evidence."""

    mass_loss: float = Field(..., ge=0.0, le=1.0)
    variability: float = Field(..., ge=0.0, le=1.0)
    evolved_stage: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)


class Breakout(BaseModel):
    """Per-class breakout countdown window (estimate; label as such in UI)."""

    class_window: BreakoutClassWindow
    countdown_from: str = Field(..., description="ISO-8601 UTC")


class CandidateScore(BaseModel):
    """One row per star; output of literature/rerank.py (CandidateScore v1)."""

    star_id: str
    ra_deg: float
    dec_deg: float
    class_: StarClass = Field(..., alias="class")
    spectral_type: str
    distance_kpc: float | None = None
    extinction_av_mag: float | None = None
    p_sky: float
    lit: Literature
    presn_watch: bool = False
    posterior: float
    breakout: Breakout
    ir_followup: bool = False
    simulated: bool = Field(
        default=False,
        description="True when scores/values are simulated; UI must label it.",
    )

    model_config = {"populate_by_name": True}


# Backward-compatible aliases (prefer Evidence / Literature / Breakout).
LiteratureEvidence = Evidence
LiteratureScores = Literature
BreakoutInfo = Breakout


def export_json_schemas() -> dict[str, dict[str, Any]]:
    """Return JSON Schema drafts for the frozen contract models."""
    return {
        "Alert": Alert.model_json_schema(),
        "SkyMap": SkyMap.model_json_schema(),
        "CandidateScore": CandidateScore.model_json_schema(),
    }


class WsHelloEvent(BaseModel):
    """First event sent on /ws/events."""

    type: Literal["hello"] = "hello"
    service: str = "breakout"
    version: str = "0.1.0"
    use_cached_stream: bool
    scenario: str
    simulated: bool = False
