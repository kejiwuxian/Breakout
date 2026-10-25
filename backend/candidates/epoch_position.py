"""Epoch-propagate catalog star positions with public proper motion.

Galactic CCSN progenitors move ~mas/yr. At HEALPix nside=64 (~0.9° pixels)
this does **not** change ``p_sky`` ranking for decade-scale epochs — so this
module does not invent PM values and is a no-op when ``pmra_mas_yr`` /
``pmdec_mas_yr`` are absent.

When catalog rows *do* carry published proper motion (e.g. Gaia/SIMBAD fields
populated offline), we propagate to the alert epoch for telescope drafts
(LCOGT) and for filter coordinates. Linear ICRS approximation only — not a
full barycentric orbit (stars of interest are not Solar System bodies).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

# mas/yr → deg/yr
_MAS_YR_TO_DEG_YR = 1.0 / 3_600_000.0


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def parse_epoch_year(value: Any, *, default: float = 2000.0) -> float:
    """Return catalog epoch as Julian/calendar year float (e.g. 2016.0)."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        pass
    # ISO date → fractional year (UTC).
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        start = datetime(dt.year, 1, 1, tzinfo=timezone.utc)
        end = datetime(dt.year + 1, 1, 1, tzinfo=timezone.utc)
        frac = (dt - start).total_seconds() / (end - start).total_seconds()
        return float(dt.year) + frac
    except ValueError:
        return default


def utc_to_year(t_utc: str | None) -> float:
    """Convert alert ``t0_utc`` ISO string to fractional year; else now (UTC)."""
    if t_utc:
        try:
            return parse_epoch_year(t_utc)
        except Exception:
            pass
    now = datetime.now(timezone.utc)
    return parse_epoch_year(now.isoformat())


def propagate_icrs(
    ra_deg: float,
    dec_deg: float,
    *,
    pmra_mas_yr: float | None,
    pmdec_mas_yr: float | None,
    epoch_year: float,
    target_year: float,
) -> tuple[float, float]:
    """Linear ICRS proper-motion propagation.

    ``pmra_mas_yr`` is Gaia-style μ_α* = μ_α cos δ (mas/yr).
    Returns (ra_deg, dec_deg) at ``target_year``.
    """
    if pmra_mas_yr is None and pmdec_mas_yr is None:
        return float(ra_deg), float(dec_deg)
    dt = float(target_year) - float(epoch_year)
    if abs(dt) < 1e-9:
        return float(ra_deg), float(dec_deg)

    mu_ra_star = float(pmra_mas_yr or 0.0)
    mu_dec = float(pmdec_mas_yr or 0.0)
    cos_dec = math.cos(math.radians(dec_deg))
    # Guard near poles: cos δ → 0 makes Δα unstable; skip RA term.
    if abs(cos_dec) < 1e-6:
        dra = 0.0
    else:
        dra = (mu_ra_star / cos_dec) * _MAS_YR_TO_DEG_YR * dt
    ddec = mu_dec * _MAS_YR_TO_DEG_YR * dt

    ra = (float(ra_deg) + dra) % 360.0
    dec = float(dec_deg) + ddec
    dec = max(-90.0, min(90.0, dec))
    return ra, dec


def current_icrs(
    row: dict[str, Any],
    *,
    at_utc: str | None = None,
) -> tuple[float, float]:
    """Return (ra_deg, dec_deg) for a catalog row at ``at_utc`` (or now).

    Uses ``pmra_mas_yr`` / ``pmdec_mas_yr`` / ``epoch_year`` when present.
    Without PM fields, returns the catalog RA/Dec unchanged (no invention).
    """
    ra = _as_float(row.get("ra_deg"))
    dec = _as_float(row.get("dec_deg"))
    if ra is None or dec is None:
        raise ValueError("catalog row missing ra_deg/dec_deg")

    pmra = _as_float(row.get("pmra_mas_yr") if "pmra_mas_yr" in row else row.get("pmra"))
    pmdec = _as_float(
        row.get("pmdec_mas_yr") if "pmdec_mas_yr" in row else row.get("pmdec")
    )
    if pmra is None and pmdec is None:
        return ra, dec

    epoch = parse_epoch_year(row.get("epoch_year") or row.get("ref_epoch") or row.get("epoch"))
    target = utc_to_year(at_utc)
    return propagate_icrs(
        ra,
        dec,
        pmra_mas_yr=pmra,
        pmdec_mas_yr=pmdec,
        epoch_year=epoch,
        target_year=target,
    )


def helps_skymap_ranking(*, nside: int = 64, pm_mas_yr: float = 50.0, years: float = 30.0) -> bool:
    """True only if typical PM shift rivals a HEALPix pixel (usually False at nside=64)."""
    pix_deg = math.degrees(math.sqrt(4.0 * math.pi / (12.0 * nside * nside)))
    shift_deg = abs(pm_mas_yr) * years * _MAS_YR_TO_DEG_YR
    return shift_deg >= 0.1 * pix_deg
