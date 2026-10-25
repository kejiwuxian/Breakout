"""Parse GCN Classic text SNEWS notices (Kafka ``gcn.classic.text.SNEWS``).

Classic notices carry coincidence/individual flags, optional Super-K
RA/Dec, and an EXPT detector list — but **not** per-detector arrival
times, so DiffPointing is not available from this channel alone.
SNEWS2 JSON coincidence notices (``gcn.notices.snews2.coincidence``)
remain the timing path for self-localization.
"""

from __future__ import annotations

import re
from typing import Any

from backend.ingest.gcn_common import canonical_detector_name, detector_hit
from backend.schemas import Alert, DetectorHit, Pointing

# Public sample fields from https://gcn.gsfc.nasa.gov/snews.html (not invented).
_RA_RE = re.compile(
    r"^EVENT_RA:\s*(?P<val>Undefined|[+-]?\d+(?:\.\d+)?)d?",
    re.IGNORECASE | re.MULTILINE,
)
_DEC_RE = re.compile(
    r"^EVENT_DEC:\s*(?P<val>Undefined|[+-]?\d+(?:\.\d+)?)d?",
    re.IGNORECASE | re.MULTILINE,
)
_ERR_RE = re.compile(
    r"^EVENT_ERROR:\s*(?P<val>\d+(?:\.\d+)?)",
    re.IGNORECASE | re.MULTILINE,
)
_TRIG_RE = re.compile(
    r"^TRIGGER_NUM:\s*(?P<val>\S+)",
    re.IGNORECASE | re.MULTILINE,
)
_TYPE_RE = re.compile(
    r"^NOTICE_TYPE:\s*(?P<val>.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_TIME_RE = re.compile(
    r"^EVENT_TIME:\s*[^\n]*\{(?P<val>\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\}",
    re.IGNORECASE | re.MULTILINE,
)
_DATE_RE = re.compile(
    r"^EVENT_DATE:\s*[^\n]*?(?P<val>\d{2}/\d{2}/\d{2})",
    re.IGNORECASE | re.MULTILINE,
)
_EXPT_RE = re.compile(
    r"^EXPT:\s*(?P<val>.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_FLUENCE_RE = re.compile(
    r"^EVENT_FLUENCE:\s*(?P<val>\d+)",
    re.IGNORECASE | re.MULTILINE,
)

# Map classic EXPT tokens onto DETECTOR_TABLE names when possible.
_EXPT_ALIASES: dict[str, str] = {
    "super-k": "Super-K",
    "superk": "Super-K",
    "super-kamiokande": "Super-K",
    "icecube": "IceCube",
    "kamland": "KamLAND",
    "sno+": "SNO+",
    "snoplus": "SNO+",
    "juno": "JUNO",
}


def _field(text: str, pattern: re.Pattern[str]) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    return str(m.group("val")).strip()


def _parse_expt(raw: str | None) -> list[str]:
    if not raw:
        return []
    # "Super-K Good, LVD Good, IceCube Possible, Daya_Bay Possible"
    names: list[str] = []
    for part in raw.split(","):
        token = part.strip().split()
        if not token:
            continue
        key = token[0].replace("_", "-").lower()
        mapped = _EXPT_ALIASES.get(key) or canonical_detector_name(token[0])
        if mapped and mapped not in names:
            names.append(mapped)
    return names


def _t0_utc(text: str) -> str | None:
    """Best-effort ISO time from EVENT_DATE (yy/mm/dd) + EVENT_TIME HMS."""
    ymd = _field(text, _DATE_RE)
    hms = _field(text, _TIME_RE)
    if not ymd or not hms:
        return None
    yy, mm, dd = ymd.split("/")
    year = 2000 + int(yy) if int(yy) < 80 else 1900 + int(yy)
    return f"{year:04d}-{int(mm):02d}-{int(dd):02d}T{hms}"


def parse_classic_snews_text(text: str, *, simulated: bool | None = None) -> Alert:
    """Normalize a classic GCN/SNEWS text notice into Alert (SN_BURST)."""
    notice_type = (_field(text, _TYPE_RE) or "").upper()
    is_test = "TEST" in notice_type
    if simulated is None:
        # TEST notices are still real pipeline traffic; mark simulated only
        # when the notice itself is a declared test (not a live SN).
        simulated = is_test

    t0 = _t0_utc(text)
    if not t0:
        raise ValueError("classic SNEWS notice missing EVENT_DATE / EVENT_TIME")

    trig = _field(text, _TRIG_RE) or "unknown"
    alert_id = f"SNEWS-classic-{trig}"

    ra_raw = _field(text, _RA_RE)
    dec_raw = _field(text, _DEC_RE)
    pointing: Pointing | None = None
    if (
        ra_raw
        and dec_raw
        and ra_raw.lower() != "undefined"
        and dec_raw.lower() != "undefined"
    ):
        err_raw = _field(text, _ERR_RE)
        pointing = Pointing(
            ra_deg=float(ra_raw),
            dec_deg=float(dec_raw),
            err_deg=float(err_raw) if err_raw is not None else 0.0,
        )

    det_names = _parse_expt(_field(text, _EXPT_RE))
    if not det_names:
        # Coincidence without recognizable EXPT names — still emit IceCube-less
        # alert only if Super-K pointing exists; else require ≥1 known detector.
        if pointing is not None:
            det_names = ["Super-K"]
        else:
            raise ValueError("classic SNEWS notice has no recognized detectors")

    fluence = _field(text, _FLUENCE_RE)
    n_events = int(fluence) if fluence else 0

    hits: list[DetectorHit] = []
    for name in det_names:
        hits.append(
            detector_hit(
                name,  # type: ignore[arg-type]
                t_arrival_utc=t0,
                n_events=n_events if len(det_names) == 1 else 0,
                pointing=pointing if name == "Super-K" else None,
            )
        )

    raw: dict[str, Any] = {
        "channel": "gcn.classic.text.SNEWS",
        "notice_type": notice_type,
        "trigger_num": trig,
        "text": text,
        "has_timing_deltas": False,
        "note": (
            "Classic SNEWS has no per-detector arrival times; "
            "localization uses Super-K pointing when present. "
            "Prefer SNEWS2 JSON coincidence for DiffPointing."
        ),
    }
    return Alert(
        alert_id=alert_id,
        kind="SN_BURST",
        source="snews2",
        simulated=bool(simulated),
        t0_utc=t0,
        detectors=hits,
        significance=0.0 if is_test else 2.0,
        raw=raw,
    )


def try_parse_classic_snews(payload: Any, *, simulated: bool | None = None) -> Alert | None:
    """Return Alert when payload is classic SNEWS text; else None."""
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(payload, str):
        return None
    if "SNEWS" not in payload.upper() and "EVENT_RA:" not in payload:
        return None
    if "TITLE:" not in payload and "NOTICE_TYPE:" not in payload:
        return None
    try:
        return parse_classic_snews_text(payload, simulated=simulated)
    except ValueError:
        return None
