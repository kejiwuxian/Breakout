"""Product of timing rings and pointing, normalize, credible region → SkyMap.

Writes data/run/<alert_id>/skymap.fits and a Mollweide PNG fallback
(data/run/<alert_id>/skymap.png). HEALPix maps are NESTED and sum to 1.
"""

from __future__ import annotations

from pathlib import Path

import healpy as hp
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np

from backend.config import HEALPIX_NSIDE, ROOT, settings
from backend.localize.pointing import extract_superk_pointing, pointing_map
from backend.localize.triangulate import pairwise_baselines, ring_map
from backend.schemas import Alert, SkyMap, SkyPeak


def _normalize(prob: np.ndarray) -> np.ndarray:
    out = np.asarray(prob, dtype=float)
    total = float(out.sum())
    if total <= 0.0 or not np.isfinite(total):
        return np.full(out.shape, 1.0 / out.size, dtype=float)
    return out / total


def credible_region_pixels(prob: np.ndarray, *, level: float = 0.9) -> np.ndarray:
    """Return pixel indices in the highest-probability credible region."""
    order = np.argsort(prob)[::-1]
    csum = np.cumsum(prob[order])
    k = int(np.searchsorted(csum, level, side="left") + 1)
    return order[: max(k, 1)]


def credible_region_area_deg2(prob: np.ndarray, *, level: float = 0.9) -> float:
    """Sky area (deg²) of the credible region at the given probability level."""
    nside = hp.npix2nside(len(prob))
    pix = credible_region_pixels(prob, level=level)
    return float(len(pix) * hp.nside2pixarea(nside, degrees=True))


def peak_ra_dec(prob: np.ndarray) -> SkyPeak:
    """ICRS peak of a NESTED probability map."""
    nside = hp.npix2nside(len(prob))
    ipix = int(np.argmax(prob))
    ra, dec = hp.pix2ang(nside, ipix, nest=True, lonlat=True)
    return SkyPeak(ra_deg=float(ra), dec_deg=float(dec))


def position_in_credible_region(
    prob: np.ndarray,
    ra_deg: float,
    dec_deg: float,
    *,
    level: float = 0.9,
) -> bool:
    """True if (ra, dec) lies inside the credible region."""
    nside = hp.npix2nside(len(prob))
    ipix = int(hp.ang2pix(nside, ra_deg, dec_deg, nest=True, lonlat=True))
    return ipix in set(credible_region_pixels(prob, level=level).tolist())


def fuse_maps(
    maps: list[np.ndarray],
    *,
    alert: Alert,
    components: list[str],
    out_dir: Path,
    nside: int | None = None,
) -> SkyMap:
    """Multiply component maps, normalize to sum 1, write FITS+PNG, return SkyMap."""
    if not maps:
        raise ValueError("fuse_maps requires at least one component map")
    nside = int(nside if nside is not None else getattr(settings, "healpix_nside", HEALPIX_NSIDE))
    prod = np.ones(hp.nside2npix(nside), dtype=float)
    for m in maps:
        if len(m) != len(prod):
            raise ValueError("All maps must share the same Nside")
        prod *= np.asarray(m, dtype=float)
    prob = _normalize(prod)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fits_path = out_dir / "skymap.fits"
    png_path = out_dir / "skymap.png"

    hp.write_map(
        str(fits_path),
        prob,
        nest=True,
        coord="C",
        column_names=["PROB"],
        column_units=["pix-1"],
        extra_header=[
            ("NSIDE", nside, "HEALPix Nside"),
            ("ORDERING", "NESTED", "HEALPix ordering"),
            ("COORDSYS", "C", "ICRS"),
            ("ALERTID", alert.alert_id[:68], "BREAKOUT alert_id"),
            ("SIMULAT", bool(alert.simulated), "True if input Alert is simulated"),
        ],
        overwrite=True,
    )

    # Mollweide 2D fallback for demos when WebGL stutters.
    plt.figure(figsize=(8, 4.5))
    hp.mollview(
        prob,
        nest=True,
        coord="C",
        title=f"BREAKOUT skymap {alert.alert_id}",
        unit="probability / pixel",
        min=0.0,
        notext=False,
    )
    if alert.simulated:
        plt.figtext(0.02, 0.02, "Simulated", color="C1", fontsize=10)
    plt.savefig(png_path, dpi=120, bbox_inches="tight")
    plt.close("all")

    # Prefer repo-relative path in the schema when under ROOT.
    try:
        prob_path = str(fits_path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        prob_path = str(fits_path)

    return SkyMap(
        alert_id=alert.alert_id,
        nside=nside,
        ordering="NESTED",
        frame="ICRS",
        prob_path=prob_path,
        components=list(components),
        credible_90_deg2=credible_region_area_deg2(prob, level=0.9),
        peak=peak_ra_dec(prob),
        simulated=bool(alert.simulated),
    )


def build_component_maps(
    alert: Alert,
    *,
    nside: int | None = None,
    include_pointing: bool = True,
) -> tuple[list[np.ndarray], list[str]]:
    """Build timing-ring (+ optional Super-K pointing) maps for one Alert."""
    nside = int(nside if nside is not None else getattr(settings, "healpix_nside", HEALPIX_NSIDE))
    maps: list[np.ndarray] = []
    components: list[str] = []

    for pair in pairwise_baselines(alert):
        # Skip near-degenerate baselines (e.g. Super-K ↔ KamLAND ~km).
        if pair["baseline_m"] < 1.0e5:  # < 100 km
            continue
        m = ring_map(
            pair["det_a"],
            pair["det_b"],
            pair["dt_s"],
            pair["dt_err_s"],
            alert.t0_utc,
            nside=nside,
        )
        maps.append(m)
        components.append(f"timing:{pair['det_a']}-{pair['det_b']}")

    if include_pointing:
        pointing = extract_superk_pointing(alert)
        if pointing is not None:
            maps.append(
                pointing_map(
                    pointing.ra_deg,
                    pointing.dec_deg,
                    pointing.err_deg,
                    nside=nside,
                )
            )
            components.append("superk_pointing")

    if not maps:
        raise ValueError("No localization components available for this Alert")
    return maps, components


def fuse(
    alerts: Alert | list[Alert],
    *,
    nside: int | None = None,
    out_root: Path | None = None,
    include_pointing: bool = True,
) -> SkyMap:
    """Fuse timing rings (+ Super-K pointing) for Alert(s) into a SkyMap.

    Writes ``data/run/<alert_id>/skymap.fits`` and ``skymap.png``.
    When multiple Alerts are passed, uses the first SN_BURST (else the first).
    """
    alert_list = [alerts] if isinstance(alerts, Alert) else list(alerts)
    if not alert_list:
        raise ValueError("fuse() requires at least one Alert")

    alert = next((a for a in alert_list if a.kind == "SN_BURST"), alert_list[0])
    nside = int(nside if nside is not None else getattr(settings, "healpix_nside", HEALPIX_NSIDE))
    maps, components = build_component_maps(
        alert, nside=nside, include_pointing=include_pointing
    )

    root = Path(out_root) if out_root is not None else ROOT / "data" / "run"
    out_dir = root / alert.alert_id
    return fuse_maps(
        maps,
        alert=alert,
        components=components,
        out_dir=out_dir,
        nside=nside,
    )
