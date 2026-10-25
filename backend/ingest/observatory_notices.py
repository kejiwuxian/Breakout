"""Normalize documented Super-K JSON and IceCube cascade Classic notices.

Primary specifications:
https://gcn.nasa.gov/missions/sksn
https://gcn.gsfc.nasa.gov/doc/High_Energy_Neutrino_Cascade_Alerts.pdf
Official examples are format demonstrations, not actual detections.
"""

from __future__ import annotations

import copy
from datetime import datetime
import math
import re
from typing import Any

from backend.ingest.gcn_common import detector_hit
from backend.schemas import Alert, Pointing


def notice_category(payload: Any, topic: str = "") -> str:
    """Tests/injections/retractions must never enter the science pipeline."""
    if ".test." in topic.lower():
        return "test"
    if isinstance(payload, dict):
        if str(payload.get("alert_type", "")).lower() == "retraction" or payload.get("retracted") is True:
            return "retraction"
        tense = str(payload.get("alert_tense", "current")).lower()
        if tense in {"test", "injection", "injections", "planned", "commanded", "archival"} or payload.get("test") is True:
            return "test"
    elif isinstance(payload, str):
        notice_type = re.search(r"^NOTICE_TYPE:\s*(.*)$", payload, re.MULTILINE | re.IGNORECASE)
        label = notice_type.group(1).upper() if notice_type else ""
        if "RETRACT" in label or re.search(r"^COMMENTS:.*(?:RETRACTION|RETRACTED)", payload, re.MULTILINE | re.IGNORECASE):
            return "retraction"
        if "TEST" in label or re.search(r"^COMMENTS:.*(?:TEST NOTICE|TEST EVENT|NOT A REAL EVENT)", payload, re.MULTILINE | re.IGNORECASE):
            return "test"
    return "science"


def _position(ra: Any, dec: Any, radius: Any) -> Pointing:
    values = [float(value) for value in (ra, dec, radius)]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Non-finite localization")
    if not (0 <= values[0] < 360 and -90 <= values[1] <= 90 and 0 < values[2] <= 180):
        raise ValueError("Invalid localization bounds")
    return Pointing(ra_deg=values[0], dec_deg=values[1], err_deg=values[2])


def containment_to_sigma(radius_deg: float, probability: float) -> float:
    """Match an angular containment radius to the existing spherical Gaussian.

    The raw radius/confidence stay in provenance. This is a circular model,
    not a reproduction of a collaboration's potentially asymmetric sky map.
    Integrating sin(theta) avoids the small-angle approximation for cascades.
    """
    from scipy.integrate import quad
    from scipy.optimize import brentq

    radius = math.radians(radius_deg)
    if not (0 < probability < 1 and 0 < radius < math.pi):
        raise ValueError("Invalid containment probability/radius")
    if probability <= (1 - math.cos(radius)) / 2:
        raise ValueError("Containment is not representable by a centered Gaussian")
    def cdf(sigma: float) -> float:
        def density(u: float) -> float:
            return math.exp(-u * u / 2) * math.sin(sigma * u)
        total = quad(density, 0, min(math.pi / sigma, 12))[0]
        enclosed = quad(density, 0, min(radius / sigma, 12))[0]
        return enclosed / total
    sigma = brentq(lambda width: cdf(width) - probability, radius / 100, 100 * math.pi)
    return math.degrees(sigma)


def normalize_superk_payload(payload: dict[str, Any]) -> Alert:
    if notice_category(payload) != "science":
        raise ValueError("Super-K test/retraction is not a science alert")
    t0 = payload.get("trigger_time")
    identity = payload.get("id")
    if not t0 or not identity:
        raise ValueError("Super-K notice requires trigger_time and id")
    datetime.fromisoformat(str(t0).replace("Z", "+00:00"))
    pointing = _position(payload.get("ra"), payload.get("dec"), payload.get("ra_dec_error"))
    n_events = int(payload.get("n_events", 0))
    if n_events < 0:
        raise ValueError("Negative event count")
    raw = copy.deepcopy(payload)
    confidence = float(payload.get("containment_probability", 0.9))
    raw["localization_model"] = "circular spherical Gaussian matched to published containment; not the collaboration's full sky map"
    pointing.err_deg = containment_to_sigma(pointing.err_deg, confidence)
    raw["provenance"] = {"observatory": "Super-Kamiokande", "notice_url": "https://gcn.nasa.gov/missions/sksn"}
    return Alert(
        alert_id=f"SuperK-{identity}", kind="SN_BURST", source="gcn_kafka", simulated=False,
        t0_utc=str(t0), detectors=[detector_hit("Super-K", t_arrival_utc=str(t0), n_events=n_events, pointing=pointing)],
        # No significance is fabricated when the notice does not provide one.
        significance=float(payload.get("significance") or 0), raw=raw,
    )


def _field(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if not match:
        raise ValueError(f"Cascade notice missing {name}")
    return match.group(1).strip()


def normalize_cascade_text(text: str) -> Alert:
    if notice_category(text) != "science":
        raise ValueError("Cascade test/retraction is not a science alert")
    if "CASCADE" not in _field(text, "NOTICE_TYPE").upper():
        raise ValueError("Not a cascade notice")
    day = re.search(r"(\d{2}/\d{2}/\d{2})", _field(text, "DISCOVERY_DATE"))
    clock = re.search(r"\{(\d{2}:\d{2}:\d{2}(?:\.\d+)?)\}", _field(text, "DISCOVERY_TIME"))
    if not day or not clock:
        raise ValueError("Cascade notice missing discovery timestamp")
    date = datetime.strptime(day.group(1), "%y/%m/%d").date().isoformat()
    t0 = f"{date}T{clock.group(1)}Z"
    datetime.fromisoformat(t0.replace("Z", "+00:00"))
    def numeric(name: str) -> float:
        match = re.match(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", _field(text, name))
        if not match:
            raise ValueError(f"Invalid {name}")
        return float(match.group(0))
    pointing = _position(numeric("SRC_RA"), numeric("SRC_DEC"), numeric("SRC_ERROR"))
    published_radius = pointing.err_deg
    pointing.err_deg = containment_to_sigma(published_radius, 0.9)
    raw: dict[str, Any] = {
        "notice_text": text, "alert_topology": "Cascade", "containment_probability": 0.9,
        "ra_dec_error": published_radius,
        "localization_model": "circular spherical Gaussian matched to published 90% containment; published HEALPix preferred when available",
        "provenance": {"observatory": "IceCube", "notice_url": "https://gcn.nasa.gov/missions/icecube"},
    }
    for name, key in (("SIGNALNESS", "p_astro"), ("ENERGY", "nu_energy"), ("FAR", "far_per_year")):
        try:
            raw[key] = numeric(name)
        except ValueError:
            pass
    for name, key in (("REVISION", "record_number"), ("SKYMAP_FITS_URL", "healpix_url")):
        try:
            raw[key] = _field(text, name)
        except ValueError:
            pass
    return Alert(
        alert_id=_field(text, "EVENT_NAME"), kind="HE_NEUTRINO", source="gcn_kafka", simulated=False,
        t0_utc=t0, detectors=[detector_hit("IceCube", t_arrival_utc=t0, n_events=1, pointing=pointing)],
        significance=float(raw.get("p_astro", 0)), raw=raw,
    )
