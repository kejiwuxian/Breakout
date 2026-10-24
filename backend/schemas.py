"""Pydantic models for Alert, SkyMap, and CandidateScore v1.

Every module reads and writes these shapes; see docs/schemas.md.
Any value from a simulation carries simulated=true.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class LiteratureEvidence(BaseModel):
    """One literature claim; bibcode is required (no bibcode, no claim)."""

    bibcode: str
    claim: str


class LiteratureScores(BaseModel):
    """Precomputed offline literature scores (0..1 each) plus evidence."""

    mass_loss: float
    variability: float
    evolved_stage: float
    confidence: float
    evidence: list[LiteratureEvidence] = Field(default_factory=list)


class BreakoutInfo(BaseModel):
    """Per-class breakout countdown window (estimate)."""

    class_window: BreakoutClassWindow
    countdown_from: str


class CandidateScore(BaseModel):
    """One row per star; output of literature/rerank.py."""

    star_id: str
    ra_deg: float
    dec_deg: float
    class_: StarClass = Field(..., alias="class")
    spectral_type: str
    distance_kpc: float | None = None
    extinction_av_mag: float | None = None
    p_sky: float
    lit: LiteratureScores
    presn_watch: bool = False
    posterior: float
    breakout: BreakoutInfo
    ir_followup: bool = False
    simulated: bool = False

    model_config = {"populate_by_name": True}


class WsHelloEvent(BaseModel):
    """First event sent on /ws/events."""

    type: Literal["hello"] = "hello"
    service: str = "breakout"
    version: str = "0.1.0"
    use_cached_stream: bool
    scenario: str
    simulated: bool = False
