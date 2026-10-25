"""SVG-first localization layers for interactive skymaps.

Derives a **smooth oval** (probability-weighted covariance ellipse) for the
90% credible region from the fused NESTED HEALPix map, plus public-catalog
field stars and a galactic-plane guide. Also writes ``region.json`` (and a
legacy focus PNG for classic UI).

Never invents coordinates: localization from the fused map; background star
positions from the committed Yale Bright Star Catalogue subset
(``data/stars/sky_background.json``, CDS V/50 / NASA HEASARC BSC5P). Ranked
SN progenitors remain a separate overlay from the curated inventory.
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

from backend.config import ROOT
from backend.localize.fuse import credible_region_area_deg2, credible_region_pixels, peak_ra_dec

logger = logging.getLogger("breakout.localize.region")

SVG_RENDER_VERSION = "svg_v1"
CURATED_STARS_PATH = ROOT / "data" / "stars" / "curated_stars.json"
SKY_BACKGROUND_PATH = ROOT / "data" / "stars" / "sky_background.json"


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


def load_public_field_stars(
    *,
    path: Path | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """All-sky background stars for SVG rendering (Yale BSC5 / HEASARC BSC5P).

    Prefers the committed compact catalog at ``SKY_BACKGROUND_PATH`` (thousands
    of magnitude-limited stars spanning the whole sky). Falls back to the
    curated progenitor list only when the background file is missing so cold
    start never invents coordinates.
    """
    bg = Path(path) if path is not None else SKY_BACKGROUND_PATH
    if bg.is_file():
        try:
            payload = json.loads(bg.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("failed_reading_sky_background path=%s", bg)
            payload = None
        rows: list[Any]
        if isinstance(payload, dict):
            rows = payload.get("stars") if isinstance(payload.get("stars"), list) else []
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                ra = float(row["ra_deg"])
                dec = float(row["dec_deg"])
            except Exception:
                continue
            item: dict[str, Any] = {
                "star_id": str(row.get("star_id") or ""),
                "common_name": row.get("common_name"),
                "ra_deg": ra,
                "dec_deg": dec,
                "source": "yale_bsc5_v50",
            }
            if row.get("vmag") is not None:
                try:
                    item["vmag"] = float(row["vmag"])
                except Exception:
                    pass
            if row.get("class"):
                item["class"] = str(row["class"])
            out.append(item)
            if limit is not None and len(out) >= int(limit):
                break
        if out:
            return out

    # Offline fallback: curated progenitors (sparse — not a uniform sky).
    path = CURATED_STARS_PATH
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed_reading_curated_stars path=%s", path)
        return []
    out = []
    if not isinstance(rows, list):
        return out
    cap = 80 if limit is None else int(limit)
    for row in rows[:cap]:
        if not isinstance(row, dict):
            continue
        try:
            ra = float(row["ra_deg"])
            dec = float(row["dec_deg"])
        except Exception:
            continue
        out.append(
            {
                "star_id": str(row.get("star_id") or ""),
                "common_name": row.get("common_name"),
                "ra_deg": ra,
                "dec_deg": dec,
                "class": str(row.get("class") or ""),
                "source": "curated_public_simbad",
            }
        )
    return out


def galactic_plane_icrs(n_points: int = 180) -> list[list[float]]:
    """Sample the galactic plane (b=0) in ICRS using Astropy public frames."""
    try:
        from astropy import units as u
        from astropy.coordinates import SkyCoord
    except Exception:
        logger.warning("astropy unavailable; skipping galactic plane guide")
        return []
    lon = np.linspace(0.0, 360.0, int(n_points), endpoint=False)
    gal = SkyCoord(l=lon * u.deg, b=np.zeros_like(lon) * u.deg, frame="galactic")
    icrs = gal.icrs
    return [
        [float(ra % 360.0), float(np.clip(dec, -90.0, 90.0))]
        for ra, dec in zip(icrs.ra.deg, icrs.dec.deg, strict=False)
    ]


def healpix_prob_cells(
    prob: np.ndarray,
    *,
    level: float = 0.9,
    max_cells: int = 600,
) -> list[dict[str, Any]]:
    """HEALPix pixel polygons inside the credible region for SVG fills."""
    prob = np.asarray(prob, dtype=float)
    nside = hp.npix2nside(len(prob))
    pix = np.asarray(credible_region_pixels(prob, level=level), dtype=int)
    if pix.size == 0:
        return []
    if pix.size > max_cells:
        order = np.argsort(prob[pix])[::-1][:max_cells]
        pix = pix[order]
    pmax = float(np.max(prob[pix])) if pix.size else 1.0
    pmax = max(pmax, 1e-12)
    cells: list[dict[str, Any]] = []
    for ipix in pix.tolist():
        ipix_i = int(ipix)
        try:
            corners_xyz = hp.boundaries(nside, ipix_i, step=1, nest=True)
        except Exception:
            continue
        # corners_xyz: shape (3, 4)
        theta, phi = hp.vec2ang(np.asarray(corners_xyz).T)
        ra = np.rad2deg(phi) % 360.0
        dec = 90.0 - np.rad2deg(theta)
        corners = [
            [float(ra[i]), float(np.clip(dec[i], -90.0, 90.0))]
            for i in range(len(ra))
        ]
        if len(corners) < 3:
            continue
        corners.append(corners[0][:])
        cells.append(
            {
                "prob": float(prob[ipix_i]),
                "weight": float(prob[ipix_i] / pmax),
                "corners": corners,
            }
        )
    return cells


def public_sky_base() -> dict[str, Any]:
    """Layers that do not require an alert: BSC5 background + galactic plane."""
    field = load_public_field_stars()
    source = (
        "yale_bsc5_v50+astropy_galactic"
        if field and field[0].get("source") == "yale_bsc5_v50"
        else "curated_fallback+astropy_galactic"
    )
    return {
        "frame": "ICRS",
        "render": SVG_RENDER_VERSION,
        "field_stars": field,
        "galactic_plane": galactic_plane_icrs(),
        "source": source,
        "field_catalog": (
            "Yale Bright Star Catalogue 5th Ed. (Hoffleit+1991) V<=6.5"
            if source.startswith("yale_bsc5")
            else "curated_stars.json fallback"
        ),
        "n_field_stars": len(field),
    }


def build_region_payload(
    prob: np.ndarray,
    *,
    alert_id: str,
    simulated: bool,
    level: float = 0.9,
) -> dict[str, Any]:
    """JSON-serializable SVG sky layers for the interactive skymap."""
    ellipse = credible_region_ellipse(prob, level=level)
    outline = sample_ellipse_outline(ellipse)
    peak = peak_ra_dec(prob)
    fov = focus_fov_deg(ellipse)
    nested = []
    for lvl in (0.5, 0.9):
        ell = credible_region_ellipse(prob, level=lvl)
        nested.append(
            {
                "level": lvl,
                "ellipse": ell,
                "outline": sample_ellipse_outline(ell, n_points=72),
            }
        )
    base = public_sky_base()
    # Do not embed the full ~8k-star background in every region.json — the UI
    # loads field stars once from ``/api/sky/base``. Keep an empty list so
    # older clients still see the key.
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
        "render": SVG_RENDER_VERSION,
        "nested_ellipses": nested,
        "prob_cells": healpix_prob_cells(prob, level=level),
        "field_stars": [],
        "field_stars_via": "/api/sky/base",
        "n_field_stars_base": int(base.get("n_field_stars") or 0),
        "galactic_plane": base["galactic_plane"],
        "simulated": bool(simulated),
        "survey_hint": "yale_bsc5_svg",
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
            if (
                cached.get("shape") != "ellipse"
                or "ellipse" not in cached
                or cached.get("render") != SVG_RENDER_VERSION
                or "field_stars" not in cached
                or "prob_cells" not in cached
            ):
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
