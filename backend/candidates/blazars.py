"""Regional blazar catalog for HE_NEUTRINO alerts (astroquery / SIMBAD).

Pull once with ``query_blazars_region`` (network) and cache under
``data/cache/<scenario>/blazars.json``. The trigger path with
``USE_CACHED_STREAM=True`` only reads the cache — no network.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from backend.ingest.cache import scenario_dir

BLAZAR_OTYPES = frozenset({"BLL", "Bla"})
DEFAULT_SCENARIO = "scenario_b_icecube_170922a"


def blazars_path(scenario: str = DEFAULT_SCENARIO) -> Path:
    """Return ``data/cache/<scenario>/blazars.json``."""
    return scenario_dir(scenario) / "blazars.json"


def load_cached_blazars(scenario: str = DEFAULT_SCENARIO) -> list[dict[str, Any]]:
    """Load blazar rows from a previously written cache (offline-safe)."""
    path = blazars_path(scenario)
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing blazar cache {path}; run query_blazars_region once and save."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "blazars" not in data:
        raise ValueError(f"blazars.json must be an object with 'blazars': {path}")
    rows = data["blazars"]
    if not isinstance(rows, list):
        raise ValueError(f"blazars list missing in {path}")
    return [dict(r) for r in rows]


def _prefer_star_id(main_id: str, ids: list[str]) -> str:
    """Prefer a TXS designation when SIMBAD lists one; else main_id."""
    txs = [i for i in ids if i.startswith("TXS ")]
    return txs[0] if txs else main_id


def circularized_r90_deg(
    ra_minus: float,
    ra_plus: float,
    dec_minus: float,
    dec_plus: float,
) -> float:
    """Geometric-mean circularized 90% radius from asymmetric PSF half-widths."""
    ra_avg = 0.5 * (float(ra_minus) + float(ra_plus))
    dec_avg = 0.5 * (float(dec_minus) + float(dec_plus))
    return float(math.sqrt(ra_avg * dec_avg))


def sigma_from_r90_deg(r90_deg: float) -> float:
    """Convert a 2D-Gaussian 90% containment radius to 1-σ (degrees)."""
    return float(r90_deg) / math.sqrt(-2.0 * math.log(0.1))


def query_blazars_region(
    ra_deg: float,
    dec_deg: float,
    *,
    radius_deg: float,
    otypes: frozenset[str] = BLAZAR_OTYPES,
) -> list[dict[str, Any]]:
    """Query SIMBAD once for blazar-like objects in a circular region.

    Requires network. Prefer ``load_cached_blazars`` on the trigger path.
    Object ids come from the catalog response (TXS names are not hardcoded).
    """
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    from astroquery.simbad import Simbad

    simbad = Simbad()
    simbad.TIMEOUT = 120
    simbad.reset_votable_fields()
    simbad.add_votable_fields("otype", "ra", "dec", "ids", "sp_type")
    center = SkyCoord(ra=float(ra_deg) * u.deg, dec=float(dec_deg) * u.deg, frame="icrs")
    table = simbad.query_region(center, radius=float(radius_deg) * u.deg)
    if table is None:
        return []

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in table:
        otype = str(row["otype"])
        if otype not in otypes:
            continue
        main_id = str(row["main_id"]).strip()
        id_field = row["ids"]
        ids = str(id_field).split("|") if id_field is not None else []
        star_id = _prefer_star_id(main_id, ids)
        if star_id in seen:
            continue
        seen.add(star_id)
        sp = row["sp_type"]
        if sp is not None and str(sp).strip() and str(sp).lower() != "nan":
            spectral = str(sp).strip()
        else:
            spectral = otype
        rows.append(
            {
                "star_id": star_id,
                "simbad_main_id": main_id,
                "ra_deg": float(row["ra"]),
                "dec_deg": float(row["dec"]),
                "class": "BLAZAR",
                "spectral_type": spectral,
                "otype": otype,
                "distance_kpc": None,
                "extinction_av_mag": None,
                "simulated": False,
                "source": "SIMBAD (astroquery) otype in {BLL,Bla}",
                "presn_watch": False,
            }
        )
    rows.sort(key=lambda r: r["star_id"])
    return rows


def save_blazars_cache(
    scenario: str,
    blazars: list[dict[str, Any]],
    *,
    query_meta: dict[str, Any] | None = None,
) -> Path:
    """Write blazars.json with simulated=false and optional query metadata."""
    path = blazars_path(scenario)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "simulated": False,
        "query": query_meta or {},
        "blazars": blazars,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def pull_and_cache_scenario_b(
    *,
    ra_deg: float = 77.43,
    dec_deg: float = 5.72,
    ra_90: tuple[float, float] = (0.80, 1.30),
    dec_90: tuple[float, float] = (0.40, 0.70),
    scenario: str = DEFAULT_SCENARIO,
) -> Path:
    """One-shot: SIMBAD pull around IceCube-170922A published region → cache.

    Defaults are GCN Circular 21916 numbers (not invented). Network required.
    """
    r90 = circularized_r90_deg(ra_90[0], ra_90[1], dec_90[0], dec_90[1])
    radius_deg = max(ra_90[1], dec_90[1]) + 0.5
    rows = query_blazars_region(ra_deg, dec_deg, radius_deg=radius_deg)
    return save_blazars_cache(
        scenario,
        rows,
        query_meta={
            "service": "SIMBAD via astroquery.simbad.Simbad.query_region",
            "center_ra_deg": ra_deg,
            "center_dec_deg": dec_deg,
            "radius_deg": radius_deg,
            "otypes": sorted(BLAZAR_OTYPES),
            "center_source": "GCN Circular 21916",
            "circularized_r90_deg": r90,
            "pointing_err_deg_1sigma": sigma_from_r90_deg(r90),
        },
    )


def write_blazar_table_json(rows: list[dict[str, Any]], path: Path) -> Path:
    """Write a plain JSON list usable by ``filter_candidates``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return path


def blazar_table_for_filter(scenario: str = DEFAULT_SCENARIO) -> Path:
    """Materialize cache blazars as a JSON list next to the cache for filter()."""
    rows = load_cached_blazars(scenario)
    out = scenario_dir(scenario) / "blazar_table.json"
    return write_blazar_table_json(rows, out)
