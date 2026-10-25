"""Credible-region ellipse + zoomed focus PNG for interactive skymaps.

Derives a **smooth oval** (probability-weighted covariance ellipse) for the
90% credible region from the fused NESTED HEALPix map — not a jagged pixel
boundary. Also writes ``region.json`` and ``skymap_focus.png``.

Never invents coordinates: everything comes from the fused map on disk.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import healpy as hp
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np

from backend.localize.fuse import credible_region_area_deg2, credible_region_pixels, peak_ra_dec

logger = logging.getLogger("breakout.localize.region")


def _unwrap_ra(ras: np.ndarray, *, center_deg: float) -> np.ndarray:
    """Unwrap RA (deg) around ``center_deg`` so differences do not wrap at 0/360."""
    return ((ras - center_deg + 180.0) % 360.0) - 180.0 + center_deg


def credible_region_ellipse(
    prob: np.ndarray,
    *,
    level: float = 0.9,
) -> dict[str, float]:
    """Fit a smooth ICRS oval to the localization credible region.

    Uses pixels inside the ``level`` credible region. Center is the
    probability-weighted mean; axes come from the covariance, scaled so
    ``π · a · b`` matches the credible area (deg²). Position angle is
    east of north (degrees): 0 = major axis toward increasing Dec.
    """
    prob = np.asarray(prob, dtype=float)
    nside = hp.npix2nside(len(prob))
    pix = np.asarray(credible_region_pixels(prob, level=level), dtype=int)
    area = credible_region_area_deg2(prob, level=level)
    peak = peak_ra_dec(prob)

    if pix.size < 3:
        r = max(float(np.sqrt(max(area, 1e-6) / np.pi)), 0.5)
        return {
            "ra_deg": float(peak.ra_deg),
            "dec_deg": float(peak.dec_deg),
            "semi_major_deg": r,
            "semi_minor_deg": r,
            "pa_deg": 0.0,
            "area_deg2": float(area),
        }

    ra, dec = hp.pix2ang(nside, pix, nest=True, lonlat=True)
    ra = np.asarray(ra, dtype=float)
    dec = np.asarray(dec, dtype=float)
    w = np.asarray(prob[pix], dtype=float)
    w_sum = float(w.sum())
    if not np.isfinite(w_sum) or w_sum <= 0.0:
        w = np.full(pix.size, 1.0 / pix.size, dtype=float)
    else:
        w = w / w_sum

    # Weighted mean RA with unwrap around the peak.
    ra_u = _unwrap_ra(ra, center_deg=float(peak.ra_deg))
    ra0 = float(np.sum(w * ra_u) % 360.0)
    dec0 = float(np.sum(w * dec))
    cosd = max(float(np.cos(np.deg2rad(dec0))), 0.15)

    # Local tangent plane: +x = east (RA), +y = north (Dec), degrees.
    x = ((ra_u - ra0 + 180.0) % 360.0 - 180.0) * cosd
    y = dec - dec0
    cxx = float(np.sum(w * x * x))
    cyy = float(np.sum(w * y * y))
    cxy = float(np.sum(w * x * y))
    cov = np.array([[cxx, cxy], [cxy, cyy]], dtype=float)
    evals, evecs = np.linalg.eigh(cov)
    evals = np.clip(evals, 1e-12, None)

    # Scale so ellipse area matches the credible region area.
    # Unscaled 1σ area is π √(λ0 λ1); k stretches both axes.
    base_area = float(np.pi * np.sqrt(evals[0] * evals[1]))
    k = float(np.sqrt(max(area, 1e-6) / max(base_area, 1e-12)))
    # evecs columns correspond to evals; largest eigenvalue → major axis.
    order = int(np.argmax(evals))
    major_vec = evecs[:, order]
    a = k * float(np.sqrt(evals[order]))
    b = k * float(np.sqrt(evals[1 - order]))
    # PA east of north: angle of major axis from +y (north) toward +x (east).
    # major_vec = (east, north) = (x, y)
    pa = float(np.rad2deg(np.arctan2(major_vec[0], major_vec[1])) % 180.0)

    return {
        "ra_deg": float(ra0 % 360.0),
        "dec_deg": float(np.clip(dec0, -90.0, 90.0)),
        "semi_major_deg": float(max(a, b)),
        "semi_minor_deg": float(min(a, b)),
        "pa_deg": pa,
        "area_deg2": float(area),
    }


def sample_ellipse_outline(
    ellipse: dict[str, float],
    *,
    n_points: int = 96,
) -> list[list[float]]:
    """Closed [[ra, dec], ...] ring sampling a smooth localization oval."""
    ra0 = float(ellipse["ra_deg"])
    dec0 = float(ellipse["dec_deg"])
    a = float(ellipse["semi_major_deg"])
    b = float(ellipse["semi_minor_deg"])
    pa = np.deg2rad(float(ellipse["pa_deg"]))
    cosd = max(float(np.cos(np.deg2rad(dec0))), 0.15)
    # PA is east of north: rotate local (major along north initially).
    # Point on axis-aligned ellipse in (east, north) after PA rotation.
    ring: list[list[float]] = []
    for i in range(n_points):
        t = 2.0 * np.pi * i / n_points
        # Ellipse in major/minor frame (major along +north before PA).
        dm = a * np.cos(t)  # along major
        dn = b * np.sin(t)  # along minor
        # Rotate: major axis at PA east of north → components in (east, north).
        east = dm * np.sin(pa) + dn * np.cos(pa)
        north = dm * np.cos(pa) - dn * np.sin(pa)
        ra = (ra0 + east / cosd) % 360.0
        dec = float(np.clip(dec0 + north, -90.0, 90.0))
        ring.append([float(ra), dec])
    ring.append(ring[0][:])
    return ring


def credible_region_outline(
    prob: np.ndarray,
    *,
    level: float = 0.9,
    max_points: int = 96,
) -> list[list[float]]:
    """Smooth oval outline of the credible region (closed RA/Dec ring)."""
    ellipse = credible_region_ellipse(prob, level=level)
    return sample_ellipse_outline(ellipse, n_points=max_points)


def focus_fov_deg(
    ellipse: dict[str, float] | float,
    *,
    min_fov: float = 6.0,
    max_fov: float = 90.0,
) -> float:
    """Angular diameter (deg) that frames the oval with margin."""
    if isinstance(ellipse, dict):
        major = float(ellipse["semi_major_deg"])
        fov = 2.6 * 2.0 * major
    else:
        radius = float(np.sqrt(max(float(ellipse), 1e-6) / np.pi))
        fov = 2.4 * 2.0 * radius
    return float(np.clip(fov, min_fov, max_fov))


def build_region_payload(
    prob: np.ndarray,
    *,
    alert_id: str,
    simulated: bool,
    level: float = 0.9,
) -> dict[str, Any]:
    """JSON-serializable region summary for the interactive skymap."""
    ellipse = credible_region_ellipse(prob, level=level)
    outline = sample_ellipse_outline(ellipse)
    peak = peak_ra_dec(prob)
    fov = focus_fov_deg(ellipse)
    return {
        "alert_id": alert_id,
        "level": level,
        "frame": "ICRS",
        "ordering": "NESTED",
        "nside": int(hp.npix2nside(len(prob))),
        "peak": {"ra_deg": float(peak.ra_deg), "dec_deg": float(peak.dec_deg)},
        "ellipse": ellipse,
        "credible_deg2": float(ellipse["area_deg2"]),
        "fov_deg": float(fov),
        "outline": outline,
        "shape": "ellipse",
        "simulated": bool(simulated),
        "survey_hint": "P/DSS2/color",
    }


def write_focus_png(
    prob: np.ndarray,
    *,
    out_path: Path,
    alert_id: str,
    simulated: bool,
    level: float = 0.9,
) -> Path:
    """Write a gnomonic zoom PNG with a smooth red oval around the region."""
    payload = build_region_payload(prob, alert_id=alert_id, simulated=simulated, level=level)
    peak = payload["peak"]
    fov = float(payload["fov_deg"])
    xsize = 800
    reso = (fov * 60.0) / xsize

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(8, 8))
    hp.gnomview(
        prob,
        nest=True,
        coord="C",
        rot=(float(peak["ra_deg"]), float(peak["dec_deg"]), 0.0),
        reso=reso,
        xsize=xsize,
        title=f"BREAKOUT focus {alert_id}",
        unit="probability / pixel",
        notext=False,
        cmap="viridis",
    )
    ax = plt.gca()
    outline = payload["outline"]
    if len(outline) >= 2:
        try:
            proj = ax.proj
            xs: list[float] = []
            ys: list[float] = []
            for ra, dec in outline:
                theta = np.deg2rad(90.0 - float(dec))
                phi = np.deg2rad(float(ra))
                x, y = proj.ang2xy(theta, phi)
                if np.isfinite(x) and np.isfinite(y):
                    xs.append(float(x))
                    ys.append(float(y))
            if len(xs) >= 2:
                ax.plot(xs, ys, color="#e23b3b", linewidth=2.2, solid_capstyle="round")
        except Exception:
            logger.exception("focus_outline_overlay_failed alert_id=%s", alert_id)

    if simulated:
        plt.figtext(0.02, 0.02, "Simulated", color="C1", fontsize=11)
    plt.savefig(out_path, dpi=120, bbox_inches="tight", facecolor="black")
    plt.close("all")
    return out_path


def write_region_artifacts(
    prob: np.ndarray,
    *,
    out_dir: Path,
    alert_id: str,
    simulated: bool,
    level: float = 0.9,
) -> dict[str, Any]:
    """Write ``region.json`` + ``skymap_focus.png`` next to the fused map."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_region_payload(
        prob, alert_id=alert_id, simulated=simulated, level=level
    )
    region_path = out_dir / "region.json"
    region_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_focus_png(
        prob,
        out_path=out_dir / "skymap_focus.png",
        alert_id=alert_id,
        simulated=simulated,
        level=level,
    )
    return payload


def load_prob_from_alert_dir(alert_dir: Path) -> np.ndarray:
    """Load NESTED probability map from ``skymap.fits`` in an alert run dir."""
    fits = Path(alert_dir) / "skymap.fits"
    if not fits.is_file():
        raise FileNotFoundError(f"missing skymap.fits under {alert_dir}")
    return np.asarray(hp.read_map(str(fits), nest=True), dtype=float)


def ensure_region_artifacts(
    alert_dir: Path,
    *,
    alert_id: str,
    simulated: bool | None = None,
) -> dict[str, Any]:
    """Return region payload, regenerating when FITS is newer or shape is stale."""
    alert_dir = Path(alert_dir)
    fits = alert_dir / "skymap.fits"
    region_path = alert_dir / "region.json"
    focus_path = alert_dir / "skymap_focus.png"
    if not fits.is_file():
        raise FileNotFoundError(f"missing skymap.fits under {alert_dir}")

    fits_mtime = fits.stat().st_mtime
    need = (
        not region_path.is_file()
        or not focus_path.is_file()
        or region_path.stat().st_mtime < fits_mtime
        or focus_path.stat().st_mtime < fits_mtime
    )
    if not need and region_path.is_file():
        try:
            cached = json.loads(region_path.read_text(encoding="utf-8"))
            if cached.get("shape") != "ellipse" or "ellipse" not in cached:
                need = True
            else:
                return cached
        except Exception:
            need = True
    if not need:
        return json.loads(region_path.read_text(encoding="utf-8"))

    prob = load_prob_from_alert_dir(alert_dir)
    if simulated is None:
        if region_path.is_file():
            try:
                simulated = bool(json.loads(region_path.read_text(encoding="utf-8")).get("simulated"))
            except Exception:
                simulated = str(alert_id).startswith("sim-")
        else:
            simulated = str(alert_id).startswith("sim-")
    return write_region_artifacts(
        prob,
        out_dir=alert_dir,
        alert_id=alert_id,
        simulated=bool(simulated),
    )
