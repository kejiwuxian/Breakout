"""Parse the official IceCube historical alert catalog (real data).

Source (do not invent coordinates):
https://icecube.wisc.edu/data-releases/2018/07/icecube-catalog-of-alert-events-up-through-icecube-170922a/

File shipped at ``data/cache/icecube_alert_catalog/catalog_of_alerts.txt``.
Events with ``(-)`` angular errors are retained as catalog rows but marked
``well_localized=False`` (IceCube notes they would have been retracted).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astropy.time import Time

from backend.config import ROOT
from backend.ingest.gcn_common import detector_hit
from backend.schemas import Alert, Pointing

CATALOG_PATH = ROOT / "data" / "cache" / "icecube_alert_catalog" / "catalog_of_alerts.txt"

# MJD  RA  (RA_ERR)  Dec  (DEC_ERR)  [# comment]
_LINE_RE = re.compile(
    r"""
    ^\s*
    (?P<mjd>\d+(?:\.\d+)?)
    \s+
    (?P<ra>[+-]?\d+(?:\.\d+)?)
    \s+
    \(
      (?P<ra_err>
        - |
        [+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?
      )
    \)
    \s+
    (?P<dec>[+-]?\d+(?:\.\d+)?)
    \s+
    \(
      (?P<dec_err>
        - |
        [+-]?\d+(?:\.\d+)?\s*,\s*[+-]?\d+(?:\.\d+)?
      )
    \)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class CatalogRow:
    mjd: float
    ra_deg: float
    dec_deg: float
    ra_err_plus: float | None
    ra_err_minus: float | None
    dec_err_plus: float | None
    dec_err_minus: float | None
    selection: str  # HESE | EHE
    realtime: bool
    well_localized: bool
    comment: str
    raw_line: str


def _parse_asym(token: str) -> tuple[float | None, float | None]:
    token = token.strip()
    if token == "-":
        return None, None
    # "+0.80,-0.37" or "+0.5,0.5" (missing sign on second → treat as +)
    parts = [p.strip() for p in token.split(",")]
    if len(parts) != 2:
        raise ValueError(f"bad asymmetric error {token!r}")
    plus = float(parts[0])
    minus_raw = parts[1]
    if minus_raw[0] not in "+-":
        minus_raw = "+" + minus_raw
    minus = float(minus_raw)
    return abs(plus), abs(minus)


def parse_catalog(path: Path | None = None) -> list[CatalogRow]:
    """Parse ``catalog_of_alerts.txt`` into rows (all values from the file)."""
    text = (path or CATALOG_PATH).read_text(encoding="utf-8")
    selection = "HESE"
    realtime = False
    rows: list[CatalogRow] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## Selected under HESE"):
            selection = "HESE"
            realtime = False
            continue
        if stripped.startswith("## Selected under EHE"):
            selection = "EHE"
            realtime = False
            continue
        if stripped.startswith("#realtime") or stripped.startswith("# realtime"):
            realtime = True
            continue
        if stripped.startswith("#"):
            continue
        comment = ""
        if "#" in line:
            code, _, comment = line.partition("#")
            line = code
            comment = comment.strip()
        m = _LINE_RE.match(line)
        if not m:
            continue
        ra_p, ra_m = _parse_asym(m.group("ra_err"))
        dec_p, dec_m = _parse_asym(m.group("dec_err"))
        well = ra_p is not None and dec_p is not None
        rows.append(
            CatalogRow(
                mjd=float(m.group("mjd")),
                ra_deg=float(m.group("ra")),
                dec_deg=float(m.group("dec")),
                ra_err_plus=ra_p,
                ra_err_minus=ra_m,
                dec_err_plus=dec_p,
                dec_err_minus=dec_m,
                selection=selection,
                realtime=realtime,
                well_localized=well,
                comment=comment,
                raw_line=stripped,
            )
        )
    return rows


def _err_deg(row: CatalogRow) -> float:
    """Conservative 90% radius ≈ max of published asymmetric RA/Dec errors."""
    vals = [
        row.ra_err_plus,
        row.ra_err_minus,
        row.dec_err_plus,
        row.dec_err_minus,
    ]
    present = [float(v) for v in vals if v is not None]
    if not present:
        return 0.0
    return float(max(present))


def row_to_alert(row: CatalogRow) -> Alert:
    """Convert one catalog row into a real HE_NEUTRINO Alert (simulated=false)."""
    t0 = Time(row.mjd, format="mjd", scale="utc")
    t0_utc = t0.utc.isot
    # Stable id from MJD + selection (catalog has no event names except IC-170922A note).
    alert_id = f"IceCube-catalog-{row.selection}-{row.mjd:.5f}"
    if abs(row.mjd - 58018.87118) < 1e-5:
        alert_id = "IceCube-170922A"

    pointing: Pointing | None = None
    if row.well_localized:
        pointing = Pointing(
            ra_deg=row.ra_deg,
            dec_deg=row.dec_deg,
            err_deg=_err_deg(row),
        )

    hit = detector_hit(
        "IceCube",
        t_arrival_utc=t0_utc,
        n_events=1,
        pointing=pointing,
    )
    raw: dict[str, Any] = {
        "source": "IceCube catalog of alert events up through IceCube-170922A",
        "url": (
            "https://icecube.wisc.edu/data-releases/2018/07/"
            "icecube-catalog-of-alert-events-up-through-icecube-170922a/"
        ),
        "mjd": row.mjd,
        "ra": row.ra_deg,
        "dec": row.dec_deg,
        "selection": row.selection,
        "realtime": row.realtime,
        "well_localized": row.well_localized,
        "comment": row.comment,
        "raw_line": row.raw_line,
    }
    return Alert(
        alert_id=alert_id,
        kind="HE_NEUTRINO",
        source="gcn_kafka",
        simulated=False,
        t0_utc=t0_utc,
        detectors=[hit],
        significance=0.0,
        raw=raw,
    )


def load_well_localized_alerts(path: Path | None = None) -> list[Alert]:
    """Alerts with published angular errors (usable for pointing validation)."""
    return [row_to_alert(r) for r in parse_catalog(path) if r.well_localized]


def load_all_alerts(path: Path | None = None) -> list[Alert]:
    """Every catalog row as an Alert (including poorly localized)."""
    return [row_to_alert(r) for r in parse_catalog(path)]
