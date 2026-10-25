"""Pull RSG / BSG / WR / LBV lists (astroquery).

Offline demos use data/stars/curated_stars.json and star_table.parquet;
network queries (SIMBAD / VizieR) run only in the offline build step
(``build_star_table(use_network=True)``) and must not run on the trigger
path when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

from backend.config import ROOT, settings

logger = logging.getLogger("breakout.candidates.catalog")

STARS_DIR = ROOT / "data" / "stars"
CURATED_PATH = STARS_DIR / "curated_stars.json"
STAR_TABLE_PATH = STARS_DIR / "star_table.parquet"

# Published catalogs (VizieR). Bibcodes are ADS; no bibcode → do not claim.
VIZIER_WR_CATALOG = "III/215"  # 7th Catalog of Galactic WR (van der Hucht 2001)
VIZIER_WR_BIBCODE = "2001NewAR..45..135V"
VIZIER_RSG_CATALOG = "J/AJ/158/20"  # K-M class I candidate RSGs (Messineo+ 2019)
VIZIER_RSG_BIBCODE = "2019AJ....158...20M"

SIMBAD_OTYPE_TO_CLASS: dict[str, str] = {
    "WR*": "WR",
    "s*r": "RSG",
    "s*b": "BSG",
    "s*y": "YSG",
}

# Match stars within this separation when merging catalogs (degrees).
_MATCH_ARCSEC = 2.0
_MATCH_DEG = _MATCH_ARCSEC / 3600.0

_STAR_VALUE_FIELDS = (
    "ra_deg",
    "dec_deg",
    "class",
    "spectral_type",
    "luminosity_class",
    "teff_k",
    "distance_kpc",
    "extinction_av_mag",
)

_LUM_CLASS_RE = re.compile(
    r"(Iab|Ia|Ib|II|III|IV|V)([a-z]*\+?[A-Z0-9./\-]*)?$",
    re.IGNORECASE,
)


def load_curated_stars(path: Path | None = None) -> list[dict[str, Any]]:
    """Load Vincent's curated real stars JSON (citations required for claims)."""
    target = Path(path) if path is not None else CURATED_PATH
    if not target.is_file():
        return []
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"curated_stars must be a JSON list: {target}")
    return data


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        # pandas / numpy NA
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return False


def _as_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    # VizieR / astropy masked columns
    if hasattr(value, "mask") and bool(getattr(value, "mask")):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _as_str(value: Any) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip()
    if not text or text in {"--", "---", "nan", "None"}:
        return None
    return text


def _parse_luminosity_class(spectral_type: str | None) -> str | None:
    """Extract a luminosity class token from a spectral type when clearly present.

    Does not invent a class: returns None if none is present in the string.
    """
    if not spectral_type:
        return None
    # Prefer explicit Ia / Iab / Ib tokens inside the spectral type.
    for token in ("Iab", "Ia", "Ib", "II", "III"):
        if token in spectral_type:
            return token
    match = _LUM_CLASS_RE.search(spectral_type.replace(" ", ""))
    if match:
        return match.group(1)
    return None


def _empty_sources() -> dict[str, str]:
    return {}


def _normalize_row(raw: dict[str, Any], *, default_source: str | None = None) -> dict[str, Any]:
    """Normalize a star dict; missing values stay null (never guessed)."""
    sources: dict[str, str] = {}
    raw_sources = raw.get("field_sources")
    if isinstance(raw_sources, dict):
        sources = {str(k): str(v) for k, v in raw_sources.items() if v}
    elif isinstance(raw_sources, str) and raw_sources.strip():
        try:
            parsed = json.loads(raw_sources)
            if isinstance(parsed, dict):
                sources = {str(k): str(v) for k, v in parsed.items() if v}
        except json.JSONDecodeError:
            sources = {}

    single_source = _as_str(raw.get("source")) or default_source

    spectral_type = _as_str(raw.get("spectral_type"))
    luminosity_class = _as_str(raw.get("luminosity_class"))
    if luminosity_class is None:
        luminosity_class = _parse_luminosity_class(spectral_type)

    row: dict[str, Any] = {
        "star_id": _as_str(raw.get("star_id")) or "",
        "common_name": _as_str(raw.get("common_name")),
        "ra_deg": _as_float(raw.get("ra_deg")),
        "dec_deg": _as_float(raw.get("dec_deg")),
        "class": _as_str(raw.get("class")),
        "spectral_type": spectral_type,
        "luminosity_class": luminosity_class,
        "teff_k": _as_float(raw.get("teff_k")),
        "distance_kpc": _as_float(raw.get("distance_kpc")),
        "extinction_av_mag": _as_float(raw.get("extinction_av_mag")),
        "notes": _as_str(raw.get("notes")),
        "simulated": bool(raw.get("simulated", False)),
        "field_sources": sources,
        "catalog_refs": list(raw.get("catalog_refs") or []),
    }

    if single_source:
        for key in _STAR_VALUE_FIELDS:
            if not _is_missing(row.get(key)) and key not in sources:
                sources[key] = single_source
        if row["star_id"] and "star_id" not in sources:
            sources["star_id"] = single_source

    return row


def _set_field(
    row: dict[str, Any],
    field: str,
    value: Any,
    source: str,
    *,
    overwrite: bool = False,
) -> None:
    """Set a field from a named source. Never invent; skip missing values."""
    if field in {"teff_k", "distance_kpc", "extinction_av_mag", "ra_deg", "dec_deg"}:
        coerced: Any = _as_float(value)
    else:
        coerced = _as_str(value) if not isinstance(value, (int, float)) else value
        if isinstance(coerced, float):
            coerced = _as_float(coerced)

    if _is_missing(coerced):
        return
    if not overwrite and not _is_missing(row.get(field)):
        return
    row[field] = coerced
    sources = row.setdefault("field_sources", _empty_sources())
    sources[field] = source


def _add_catalog_ref(row: dict[str, Any], catalog: str, bibcode: str) -> None:
    refs = row.setdefault("catalog_refs", [])
    entry = {"catalog": catalog, "bibcode": bibcode}
    if entry not in refs:
        refs.append(entry)


def _coord_key(ra_deg: float, dec_deg: float) -> tuple[int, int]:
    """Coarse HEALPix-like grid key for candidate matching (~arcsec cells)."""
    scale = 3600.0 / _MATCH_ARCSEC
    return (int(round(ra_deg * scale)), int(round(dec_deg * scale)))


def _find_match(
    rows_by_key: dict[tuple[int, int], list[int]],
    rows: list[dict[str, Any]],
    ra_deg: float,
    dec_deg: float,
) -> int | None:
    key = _coord_key(ra_deg, dec_deg)
    candidates: list[int] = []
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            candidates.extend(rows_by_key.get((key[0] + di, key[1] + dj), []))
    best_i: int | None = None
    best_d2 = _MATCH_DEG * _MATCH_DEG
    for i in candidates:
        other = rows[i]
        ora = other.get("ra_deg")
        odec = other.get("dec_deg")
        if ora is None or odec is None:
            continue
        # Small-angle approx; adequate for ≤2″ matching.
        dra = (float(ora) - ra_deg) * math.cos(math.radians(dec_deg))
        ddec = float(odec) - dec_deg
        d2 = dra * dra + ddec * ddec
        if d2 <= best_d2:
            best_d2 = d2
            best_i = i
    return best_i


def _index_rows(rows: list[dict[str, Any]]) -> dict[tuple[int, int], list[int]]:
    index: dict[tuple[int, int], list[int]] = {}
    for i, row in enumerate(rows):
        ra = row.get("ra_deg")
        dec = row.get("dec_deg")
        if ra is None or dec is None:
            continue
        key = _coord_key(float(ra), float(dec))
        index.setdefault(key, []).append(i)
    return index


def _merge_row(
    rows: list[dict[str, Any]],
    index: dict[tuple[int, int], list[int]],
    incoming: dict[str, Any],
    *,
    prefer_incoming: bool = False,
) -> None:
    """Merge incoming into rows by sky position; fill nulls only unless prefer_incoming."""
    ra = incoming.get("ra_deg")
    dec = incoming.get("dec_deg")
    if ra is None or dec is None:
        return
    match = _find_match(index, rows, float(ra), float(dec))
    if match is None:
        rows.append(incoming)
        key = _coord_key(float(ra), float(dec))
        index.setdefault(key, []).append(len(rows) - 1)
        return

    target = rows[match]
    overwrite = prefer_incoming
    for field in _STAR_VALUE_FIELDS:
        src = (incoming.get("field_sources") or {}).get(field)
        if src is None:
            continue
        _set_field(target, field, incoming.get(field), src, overwrite=overwrite)
    if _is_missing(target.get("common_name")) and not _is_missing(incoming.get("common_name")):
        target["common_name"] = incoming["common_name"]
    if _is_missing(target.get("star_id")) and incoming.get("star_id"):
        target["star_id"] = incoming["star_id"]
        (target.setdefault("field_sources", {}))["star_id"] = (
            incoming.get("field_sources") or {}
        ).get("star_id", "merge")
    for ref in incoming.get("catalog_refs") or []:
        if isinstance(ref, dict) and ref.get("bibcode") and ref.get("catalog"):
            _add_catalog_ref(target, str(ref["catalog"]), str(ref["bibcode"]))
    # Real catalog rows stay simulated=false unless both sides are simulated.
    target["simulated"] = bool(target.get("simulated")) and bool(incoming.get("simulated"))


def _otype_to_class(otype: str | None) -> str | None:
    if not otype:
        return None
    if otype in SIMBAD_OTYPE_TO_CLASS:
        return SIMBAD_OTYPE_TO_CLASS[otype]
    if otype.startswith("WR"):
        return "WR"
    if otype == "s*r":
        return "RSG"
    if otype == "s*b":
        return "BSG"
    if otype == "s*y":
        return "YSG"
    return None


def _query_simbad_otypes() -> list[dict[str, Any]]:
    """SIMBAD object types for Wolf-Rayet and supergiants (network)."""
    from astroquery.simbad import Simbad

    simbad = Simbad()
    simbad.ROW_LIMIT = 10000
    simbad.add_votable_fields("otype", "sptype")

    out: list[dict[str, Any]] = []
    for otype, star_class in SIMBAD_OTYPE_TO_CLASS.items():
        table = simbad.query_criteria(f"otype={otype}")
        if table is None:
            logger.warning("SIMBAD returned no rows for otype=%s", otype)
            continue
        for row in table:
            ra = _as_float(row["ra"])
            dec = _as_float(row["dec"])
            if ra is None or dec is None:
                continue
            main_id = _as_str(row["main_id"]) or f"SIMBAD-{ra:.5f}{dec:+.5f}"
            sp = _as_str(row["sp_type"]) if "sp_type" in table.colnames else None
            otype_val = _as_str(row["otype"]) if "otype" in table.colnames else otype
            mapped = _otype_to_class(otype_val) or star_class
            record = _normalize_row(
                {
                    "star_id": main_id,
                    "ra_deg": ra,
                    "dec_deg": dec,
                    "class": mapped,
                    "spectral_type": sp,
                    "luminosity_class": _parse_luminosity_class(sp),
                    "simulated": False,
                    "field_sources": {
                        "star_id": "SIMBAD",
                        "ra_deg": "SIMBAD",
                        "dec_deg": "SIMBAD",
                        "class": "SIMBAD",
                        **({"spectral_type": "SIMBAD"} if sp else {}),
                        **(
                            {"luminosity_class": "SIMBAD"}
                            if _parse_luminosity_class(sp)
                            else {}
                        ),
                    },
                    "catalog_refs": [],
                }
            )
            out.append(record)
        logger.info("SIMBAD otype=%s rows=%d", otype, len(table))
    return out


def _enrich_curated_from_simbad(rows: list[dict[str, Any]]) -> None:
    """Fill null curated fields from SIMBAD; never overwrite real curated values."""
    from astroquery.simbad import Simbad

    simbad = Simbad()
    simbad.add_votable_fields("otype", "sptype")

    for row in rows:
        star_id = row.get("star_id")
        if not star_id:
            continue
        try:
            table = simbad.query_object(str(star_id))
        except Exception as exc:  # noqa: BLE001 — offline build must continue
            logger.warning("SIMBAD query_object failed for %s: %s", star_id, exc)
            continue
        if table is None or len(table) == 0:
            continue
        hit = table[0]
        sp = _as_str(hit["sp_type"]) if "sp_type" in table.colnames else None
        otype = _as_str(hit["otype"]) if "otype" in table.colnames else None
        _set_field(row, "spectral_type", sp, "SIMBAD")
        _set_field(row, "luminosity_class", _parse_luminosity_class(sp), "SIMBAD")
        mapped = _otype_to_class(otype)
        if mapped:
            _set_field(row, "class", mapped, "SIMBAD")
        # Coordinates: fill only if curated left them null (should be rare).
        _set_field(row, "ra_deg", hit["ra"], "SIMBAD")
        _set_field(row, "dec_deg", hit["dec"], "SIMBAD")


def _hms_or_deg_to_deg(ra_val: Any, dec_val: Any) -> tuple[float | None, float | None]:
    """Parse VizieR RA/Dec which may be sexagesimal strings or degrees."""
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    if _is_missing(ra_val) or _is_missing(dec_val):
        return None, None
    # Already numeric degrees.
    if isinstance(ra_val, (int, float)) and isinstance(dec_val, (int, float)):
        return _as_float(ra_val), _as_float(dec_val)
    ra_s = str(ra_val).strip()
    dec_s = str(dec_val).strip()
    try:
        # Sexagesimal "HH MM SS.s" / "±DD MM SS.s"
        if ":" in ra_s or " " in ra_s:
            coord = SkyCoord(f"{ra_s} {dec_s}", unit=(u.hourangle, u.deg), frame="icrs")
        else:
            coord = SkyCoord(float(ra_s) * u.deg, float(dec_s) * u.deg, frame="icrs")
        return float(coord.ra.deg), float(coord.dec.deg)
    except Exception:  # noqa: BLE001
        return None, None


def _query_vizier_wr() -> list[dict[str, Any]]:
    """Published Galactic WR catalog via VizieR (van der Hucht 2001)."""
    from astroquery.vizier import Vizier

    vizier = Vizier(columns=["*"], row_limit=-1)
    tables = vizier.get_catalogs(f"{VIZIER_WR_CATALOG}")
    if not tables:
        return []

    by_name = {t.meta.get("name", ""): t for t in tables}
    pos = by_name.get(f"{VIZIER_WR_CATALOG}/table13")
    sp = by_name.get(f"{VIZIER_WR_CATALOG}/table15")
    phys = by_name.get(f"{VIZIER_WR_CATALOG}/table28")
    if pos is None:
        logger.warning("VizieR %s missing table13", VIZIER_WR_CATALOG)
        return []

    sp_by_wr = {}
    if sp is not None:
        for row in sp:
            wr = _as_str(row["WR"])
            if wr:
                sp_by_wr[wr] = row
    phys_by_wr = {}
    if phys is not None:
        for row in phys:
            wr = _as_str(row["WR"])
            if wr:
                phys_by_wr[wr] = row

    source = f"VizieR:{VIZIER_WR_CATALOG}"
    out: list[dict[str, Any]] = []
    for row in pos:
        wr = _as_str(row["WR"])
        if not wr:
            continue
        ra, dec = _hms_or_deg_to_deg(row["RAJ2000"], row["DEJ2000"])
        if ra is None or dec is None:
            continue
        name = _as_str(row["Name"]) or _as_str(row["Aname"])
        star_id = f"WR {wr}" if not wr.upper().startswith("WR") else wr
        if name:
            # Prefer catalog Name when present (e.g. HIP ids stay as notes).
            pass
        sp_row = sp_by_wr.get(wr)
        phys_row = phys_by_wr.get(wr)
        spectral = None
        if sp_row is not None:
            spectral = _as_str(sp_row["SpType"])
        elif phys_row is not None:
            spectral = _as_str(phys_row["SpType"])
        distance = _as_float(phys_row["d"]) if phys_row is not None else None
        av = _as_float(phys_row["Av"]) if phys_row is not None else None

        record = _normalize_row(
            {
                "star_id": star_id,
                "common_name": name,
                "ra_deg": ra,
                "dec_deg": dec,
                "class": "WR",
                "spectral_type": spectral,
                "distance_kpc": distance,
                "extinction_av_mag": av,
                "simulated": False,
                "field_sources": {
                    "star_id": source,
                    "ra_deg": source,
                    "dec_deg": source,
                    "class": source,
                    **({"spectral_type": source} if spectral else {}),
                    **({"distance_kpc": source} if distance is not None else {}),
                    **({"extinction_av_mag": source} if av is not None else {}),
                    **({"common_name": source} if name else {}),
                },
                "catalog_refs": [
                    {"catalog": VIZIER_WR_CATALOG, "bibcode": VIZIER_WR_BIBCODE}
                ],
                "notes": f"van der Hucht 2001 WR={wr}",
            }
        )
        out.append(record)
    logger.info("VizieR WR %s rows=%d", VIZIER_WR_CATALOG, len(out))
    return out


def _distance_modulus_to_kpc(dm: float | None) -> float | None:
    """Convert a published distance modulus to kpc. Returns null if dm missing."""
    if dm is None:
        return None
    # d_pc = 10 ** ((DM + 5) / 5); d_kpc = d_pc / 1000
    d_pc = 10 ** ((dm + 5.0) / 5.0)
    return d_pc / 1000.0


def _query_vizier_rsg() -> list[dict[str, Any]]:
    """Published Galactic RSG-candidate catalog via VizieR (Messineo+ 2019)."""
    from astroquery.vizier import Vizier

    vizier = Vizier(columns=["*"], row_limit=-1)
    tables = vizier.get_catalogs(f"{VIZIER_RSG_CATALOG}/catalog")
    if not tables:
        tables = vizier.get_catalogs(VIZIER_RSG_CATALOG)
    if not tables:
        return []

    table = tables[0]
    source = f"VizieR:{VIZIER_RSG_CATALOG}"
    out: list[dict[str, Any]] = []
    for row in table:
        ra, dec = _hms_or_deg_to_deg(row["RAJ2000"], row["DEJ2000"])
        if ra is None or dec is None:
            continue
        catalog_id = _as_str(row["ID"])
        alias = _as_str(row["Alias"]) if "Alias" in table.colnames else None
        simbad_name = (
            _as_str(row["SimbadName"]) if "SimbadName" in table.colnames else None
        )
        star_id = simbad_name or alias or (f"Messineo2019-{catalog_id}" if catalog_id else None)
        if not star_id:
            star_id = f"Messineo2019-{ra:.5f}{dec:+.5f}"
        spectral = _as_str(row["SpType"]) if "SpType" in table.colnames else None
        lum = _as_str(row["Class"]) if "Class" in table.colnames else None
        if lum in {"?", ""}:
            lum = None
        dm = _as_float(row["DM"]) if "DM" in table.colnames else None
        distance = _distance_modulus_to_kpc(dm)

        record = _normalize_row(
            {
                "star_id": star_id,
                "common_name": alias,
                "ra_deg": ra,
                "dec_deg": dec,
                "class": "RSG",
                "spectral_type": spectral,
                "luminosity_class": lum,
                "distance_kpc": distance,
                "simulated": False,
                "field_sources": {
                    "star_id": source,
                    "ra_deg": source,
                    "dec_deg": source,
                    "class": source,
                    **({"spectral_type": source} if spectral else {}),
                    **({"luminosity_class": source} if lum else {}),
                    **({"distance_kpc": source} if distance is not None else {}),
                    **({"common_name": source} if alias else {}),
                },
                "catalog_refs": [
                    {"catalog": VIZIER_RSG_CATALOG, "bibcode": VIZIER_RSG_BIBCODE}
                ],
                "notes": (
                    f"Messineo+ 2019 ID={catalog_id}; distance from published DM"
                    if distance is not None
                    else f"Messineo+ 2019 ID={catalog_id}"
                ),
            }
        )
        out.append(record)
    logger.info("VizieR RSG %s rows=%d", VIZIER_RSG_CATALOG, len(out))
    return out


def _rows_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    serializable: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["field_sources"] = json.dumps(row.get("field_sources") or {}, sort_keys=True)
        item["catalog_refs"] = json.dumps(row.get("catalog_refs") or [])
        serializable.append(item)
    columns = [
        "star_id",
        "common_name",
        "ra_deg",
        "dec_deg",
        "class",
        "spectral_type",
        "luminosity_class",
        "teff_k",
        "distance_kpc",
        "extinction_av_mag",
        "field_sources",
        "catalog_refs",
        "notes",
        "simulated",
    ]
    if not serializable:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(serializable, columns=columns)


def load_star_table(path: Path | None = None) -> list[dict[str, Any]]:
    """Read star_table.parquet (or JSON) into row dicts. No network."""
    target = Path(path) if path is not None else STAR_TABLE_PATH
    if not target.is_file():
        return []
    if target.suffix == ".json":
        return [_normalize_row(r) for r in load_curated_stars(target)]
    df = pd.read_parquet(target)
    rows: list[dict[str, Any]] = []
    for record in df.to_dict(orient="records"):
        sources = record.get("field_sources")
        if isinstance(sources, str):
            try:
                record["field_sources"] = json.loads(sources)
            except json.JSONDecodeError:
                record["field_sources"] = {}
        refs = record.get("catalog_refs")
        if isinstance(refs, str):
            try:
                record["catalog_refs"] = json.loads(refs)
            except json.JSONDecodeError:
                record["catalog_refs"] = []
        rows.append(_normalize_row(record))
    return rows


def build_star_table(
    *,
    use_network: bool | None = None,
    out_path: Path | None = None,
    curated_path: Path | None = None,
) -> Path:
    """Build star_table.parquet from curated stars (+ optional SIMBAD/VizieR).

    When ``use_network`` is False (default on the trigger path / when
    USE_CACHED_STREAM=True), only local curated data is used — no SIMBAD or
    VizieR calls. Network enrichment is an offline build step only.
    """
    if use_network is None:
        # Cached-stream / trigger path: never hit the network.
        use_network = not bool(settings.use_cached_stream)

    if use_network and settings.use_cached_stream:
        raise RuntimeError(
            "build_star_table(use_network=True) is disabled when "
            "USE_CACHED_STREAM=True; run the offline build with "
            "USE_CACHED_STREAM=False or pass use_network=False to use curated only."
        )

    curated_raw = load_curated_stars(curated_path)
    rows = [
        _normalize_row(r, default_source=_as_str(r.get("source")) or "curated_stars.json")
        for r in curated_raw
    ]
    # Curated is the source of truth. No ADS bibcode for the file itself —
    # literature claims stay out of catalog_refs until Vincent adds bibcodes.
    for row in rows:
        row["simulated"] = bool(row.get("simulated", False))

    if use_network:
        logger.info("Offline catalog build: querying SIMBAD + VizieR")
        _enrich_curated_from_simbad(rows)
        index = _index_rows(rows)
        for incoming in _query_simbad_otypes():
            _merge_row(rows, index, incoming, prefer_incoming=False)
        for incoming in _query_vizier_wr():
            _merge_row(rows, index, incoming, prefer_incoming=False)
        for incoming in _query_vizier_rsg():
            _merge_row(rows, index, incoming, prefer_incoming=False)
    else:
        logger.info(
            "build_star_table: use_network=False — curated only (%d rows), no SIMBAD/VizieR",
            len(rows),
        )

    # Drop rows without coordinates (cannot be filtered on a skymap).
    rows = [r for r in rows if r.get("ra_deg") is not None and r.get("dec_deg") is not None]
    for row in rows:
        if not row.get("star_id"):
            row["star_id"] = f"anon-{row['ra_deg']:.5f}{row['dec_deg']:+.5f}"

    target = Path(out_path) if out_path is not None else STAR_TABLE_PATH
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    df = _rows_to_dataframe(rows)
    df.to_parquet(target, index=False)
    logger.info("Wrote %d stars to %s", len(df), target)
    return target


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.candidates.catalog",
        description=(
            "Offline build of data/stars/star_table.parquet from curated stars "
            "plus optional SIMBAD/VizieR enrichment."
        ),
    )
    parser.add_argument(
        "--network",
        action="store_true",
        help="Query SIMBAD + VizieR (requires USE_CACHED_STREAM=False).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=STAR_TABLE_PATH,
        help="Output parquet path (default data/stars/star_table.parquet).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    path = build_star_table(use_network=bool(args.network), out_path=args.out)
    n = len(load_star_table(path))
    print(f"wrote {n} stars to {path} (use_network={bool(args.network)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
