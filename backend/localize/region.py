"""Credible-region outline + zoomed focus PNG for interactive skymaps.

Reads the fused NESTED HEALPix probability map and derives:
- a closed ICRS outline of the 90% credible region (red contour in the UI)
- a gnomonic ``skymap_focus.png`` centered on the peak (offline-friendly)
- a ``region.json`` summary (peak, FOV, outline) for Aladin / SVG overlays

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


def _unwrap_ra(ras: np.ndarray) -> np.ndarray:
    """Unwrap RA (deg) around the sample median so polygons do not wrap at 0/360."""
    med = float(np.median(ras))
    return ((ras - med + 180.0) % 360.0) - 180.0 + med


def credible_region_outline(
    prob: np.ndarray,
    *,
    level: float = 0.9,
    max_points: int = 240,
) -> list[list[float]]:
    """Return a closed [[ra_deg, dec_deg], ...] ring for the credible region.

    Boundary HEALPix pixels (NESTED) are angularly sorted around the region
    centroid. The ring is closed (first point repeated at the end).
    """
    prob = np.asarray(prob, dtype=float)
    nside = hp.npix2nside(len(prob))
    pix = credible_region_pixels(prob, level=level)
    region = set(int(p) for p in pix.tolist())
    if not region:
        peak = peak_ra_dec(prob)
        ra, dec = float(peak.ra_deg), float(peak.dec_deg)
        return [[ra, dec], [ra, dec]]

    boundary: list[tuple[float, float]] = []
    for ipix in region:
        neigh = hp.get_all_neighbours(nside, int(ipix), nest=True)
        if any(int(n) >= 0 and int(n) not in region for n in neigh):
            ra, dec = hp.pix2ang(nside, int(ipix), nest=True, lonlat=True)
            boundary.append((float(ra), float(dec)))

    if len(boundary) < 3:
        # Tiny region — circle a few samples around the peak.
        peak = peak_ra_dec(prob)
        ra0, dec0 = float(peak.ra_deg), float(peak.dec_deg)
        radius = max(np.sqrt(credible_region_area_deg2(prob, level=level) / np.pi), 0.5)
        ring = []
        for k in range(32):
            ang = 2.0 * np.pi * k / 32.0
            ring.append(
                [
                    (ra0 + radius * np.cos(ang) / max(np.cos(np.deg2rad(dec0)), 0.2)) % 360.0,
                    float(np.clip(dec0 + radius * np.sin(ang), -90.0, 90.0)),
                ]
            )
        ring.append(ring[0][:])
        return ring

    ras = np.array([p[0] for p in boundary], dtype=float)
    decs = np.array([p[1] for p in boundary], dtype=float)
    ras_u = _unwrap_ra(ras)
    cx = float(ras_u.mean())
    cy = float(decs.mean())
    ang = np.arctan2(decs - cy, ras_u - cx)
    order = np.argsort(ang)
    ras_s = ras_u[order]
    decs_s = decs[order]

    # Decimate dense boundaries for the browser.
    if len(ras_s) > max_points:
        idx = np.linspace(0, len(ras_s) - 1, max_points).astype(int)
        ras_s = ras_s[idx]
        decs_s = decs_s[idx]

    ring = [[float(ras_s[i] % 360.0), float(decs_s[i])] for i in range(len(ras_s))]
    ring.append(ring[0][:])
    return ring


def focus_fov_deg(area_deg2: float, *, min_fov: float = 6.0, max_fov: float = 90.0) -> float:
    """Angular diameter (deg) that frames the credible region with margin."""
    radius = float(np.sqrt(max(area_deg2, 1e-6) / np.pi))
    fov = 2.4 * 2.0 * radius  # diameter × margin
    return float(np.clip(fov, min_fov, max_fov))


def build_region_payload(
    prob: np.ndarray,
    *,
    alert_id: str,
    simulated: bool,
    level: float = 0.9,
) -> dict[str, Any]:
    """JSON-serializable region summary for the interactive skymap."""
    area = credible_region_area_deg2(prob, level=level)
    peak = peak_ra_dec(prob)
    outline = credible_region_outline(prob, level=level)
    fov = focus_fov_deg(area)
    return {
        "alert_id": alert_id,
        "level": level,
        "frame": "ICRS",
        "ordering": "NESTED",
        "nside": int(hp.npix2nside(len(prob))),
        "peak": {"ra_deg": float(peak.ra_deg), "dec_deg": float(peak.dec_deg)},
        "credible_deg2": float(area),
        "fov_deg": float(fov),
        "outline": outline,
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
    """Write a gnomonic zoom PNG with a red 90% outline around the region."""
    payload = build_region_payload(prob, alert_id=alert_id, simulated=simulated, level=level)
    peak = payload["peak"]
    fov = float(payload["fov_deg"])
    # healpy gnomview reso is arcmin/pixel; aim ~800 px across FOV.
    xsize = 800
    reso = (fov * 60.0) / xsize  # arcmin / pixel

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
    # Project outline into the same gnomonic axes (healpy sets current axes).
    ax = plt.gca()
    outline = payload["outline"]
    if len(outline) >= 2:
        # Convert ICRS outline → gnomonic display by projecting each point
        # with healpy's projector attached to the current moll/gnom axes.
        try:
            proj = ax.proj
            xs: list[float] = []
            ys: list[float] = []
            for ra, dec in outline:
                # healpy projector expects lon/lat in degrees for lonlat=True paths;
                # proj.ang2xy takes theta,phi in radians — use vec2xy via ang2vec.
                theta = np.deg2rad(90.0 - float(dec))
                phi = np.deg2rad(float(ra))
                x, y = proj.ang2xy(theta, phi)
                if np.isfinite(x) and np.isfinite(y):
                    xs.append(float(x))
                    ys.append(float(y))
            if len(xs) >= 2:
                ax.plot(xs, ys, color="#e23b3b", linewidth=2.0, solid_capstyle="round")
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
    """Return region payload, regenerating focus artifacts when missing/stale."""
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
    if not need:
        return json.loads(region_path.read_text(encoding="utf-8"))

    prob = load_prob_from_alert_dir(alert_dir)
    if simulated is None:
        # Prefer existing region.json flag; else True only if filename is sim-*.
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
