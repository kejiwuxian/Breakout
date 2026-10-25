"""Consolidate SN-potential star inventory (position, life, composition, confidence).

Built offline from curated stars + literature index. Never invents bibcodes or
star-specific remaining lifetimes — life expectancy is a class-window estimate
with an optional literature stage note taken from ADS claims only.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from backend.candidates.catalog import (
    CURATED_PATH,
    STAR_TABLE_PATH,
    load_curated_stars,
    load_star_table,
)
from backend.config import CLASS_WINDOWS, ROOT
from backend.literature.rerank import load_index
from backend.physics.breakout_window import class_window
from backend.schemas import Evidence, Literature

logger = logging.getLogger("breakout.progenitors.inventory")

INVENTORY_PATH = ROOT / "data" / "stars" / "progenitor_inventory.parquet"
INVENTORY_META_PATH = ROOT / "data" / "stars" / "progenitor_inventory_meta.json"

# Class-window basis citations (same ADS bibcodes as backend.config.CLASS_WINDOWS).
_CLASS_WINDOW_BASIS: dict[str, str] = {
    "WR": "class optical-breakout window: compact WR envelopes (ADS 2010ApJ...725..904N)",
    "BSG": "class optical-breakout window: BSG/SN 1987A hours-scale (ADS 1987PhRvL..58.1490H)",
    "YSG": "class optical-breakout window: YSG inherits hours-scale BSG-like default (ADS 2010ApJ...725..904N)",
    "RSG": "class optical-breakout window: extended RSG envelopes ~1 day (ADS 2010ApJ...725..904N)",
    "LBV": "class optical-breakout window: LBV inherits hours-scale default (ADS 2010ApJ...725..904N)",
    "AGN": "no CCSN optical breakout; follow-up hours label only",
}


class LifeExpectancy(BaseModel):
    """Comparable timing context — not a star-specific collapse countdown."""

    optical_breakout_window: Literal["minutes", "hours", "about 1 day"]
    stellar_stage_note: str | None = Field(
        default=None,
        description="Optional stage note copied from an ADS claim; never invented.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    basis: str = Field(..., min_length=1)


class ProgenitorProfile(BaseModel):
    """One inventory row for a star with any supernova-progenitor potential."""

    star_id: str
    common_name: str | None = None
    ra_deg: float
    dec_deg: float
    class_: str = Field(..., alias="class")
    spectral_type: str = ""
    distance_kpc: float | None = None
    extinction_av_mag: float | None = None
    composition: str | None = Field(
        default=None,
        description="Spectral/class composition summary from catalog fields only.",
    )
    life_expectancy: LifeExpectancy
    sn_potential: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="0..1 inventory score from literature evolved_stage × confidence.",
    )
    lit: Literature
    last_reviewed_utc: str
    catalog_refs: list[dict[str, str]] = Field(default_factory=list)
    simulated: bool = False

    model_config = {"populate_by_name": True}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        # pandas NA / NaN
        if isinstance(value, float) and value != value:
            return None
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, float) and value != value:
            return None
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _float_or_zero(value: Any) -> float:
    if isinstance(value, dict):
        inner = value.get("value")
        if isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return float(inner)
        return 0.0
    try:
        if value is None:
            return 0.0
        out = float(value)
        if out != out:
            return 0.0
        return max(0.0, min(1.0, out))
    except (TypeError, ValueError):
        return 0.0


def _parse_evidence(src: Any) -> list[Evidence]:
    raw = src
    if isinstance(src, dict):
        raw = src.get("evidence") or []
        if not raw and src.get("evidence_json"):
            ej = src["evidence_json"]
            if isinstance(ej, str) and ej.strip():
                try:
                    raw = json.loads(ej)
                except json.JSONDecodeError:
                    raw = []
    if not isinstance(raw, list):
        return []
    out: list[Evidence] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        bib = str(item.get("bibcode") or "").strip()
        claim = str(item.get("claim") or "").strip()
        if bib and claim and bib.lower() != "null":
            out.append(Evidence(bibcode=bib, claim=claim))
    return out


def _lit_from_sources(
    row: dict[str, Any],
    indexed: dict[str, Any] | None,
) -> Literature:
    """Prefer offline literature index; fall back to curated lit with bibcodes only."""
    if indexed is not None:
        return Literature(
            mass_loss=_float_or_zero(indexed.get("mass_loss")),
            variability=_float_or_zero(indexed.get("variability")),
            evolved_stage=_float_or_zero(indexed.get("evolved_stage")),
            confidence=_float_or_zero(indexed.get("confidence")),
            evidence=_parse_evidence(indexed),
        )
    lit_raw = row.get("lit")
    if lit_raw is None and row.get("lit_json"):
        try:
            lit_raw = json.loads(str(row["lit_json"]))
        except json.JSONDecodeError:
            lit_raw = None
    if isinstance(lit_raw, dict):
        return Literature(
            mass_loss=_float_or_zero(lit_raw.get("mass_loss")),
            variability=_float_or_zero(lit_raw.get("variability")),
            evolved_stage=_float_or_zero(lit_raw.get("evolved_stage")),
            confidence=_float_or_zero(lit_raw.get("confidence")),
            evidence=_parse_evidence(lit_raw),
        )
    return Literature(
        mass_loss=0.0,
        variability=0.0,
        evolved_stage=0.0,
        confidence=0.0,
        evidence=[],
    )


def _composition_summary(row: dict[str, Any]) -> str | None:
    """Catalog-only composition string (spectral type + class). Never invent abundances."""
    parts: list[str] = []
    sp = _optional_str(row.get("spectral_type"))
    cls = _optional_str(row.get("class"))
    if sp:
        parts.append(sp)
    if cls:
        parts.append(f"class {cls}")
    notes = _optional_str(row.get("notes"))
    # Only keep notes that look like catalog provenance, not speculative chemistry.
    if notes and len(notes) < 160 and "invent" not in notes.lower():
        parts.append(notes)
    if not parts:
        return None
    return " · ".join(parts)


def _stellar_stage_note(evidence: list[Evidence]) -> str | None:
    """Pick a short stage-related claim if one already cites an ADS bibcode."""
    keywords = (
        "helium",
        "evolved",
        "supergiant",
        "progenitor",
        "age",
        "core",
        "burning",
        "wolf-rayet",
        "mass",
    )
    for ev in evidence:
        claim_l = ev.claim.lower()
        if any(k in claim_l for k in keywords):
            # Truncate for hover / list density; keep bibcode attribution in basis.
            text = ev.claim.strip()
            if len(text) > 180:
                text = text[:177] + "…"
            return f"{text} (ADS {ev.bibcode})"
    return None


def _life_expectancy(star_class: str, lit: Literature) -> LifeExpectancy:
    window = class_window(star_class)
    basis = _CLASS_WINDOW_BASIS.get(
        str(star_class),
        f"class optical-breakout window default for {star_class}",
    )
    stage = _stellar_stage_note(lit.evidence)
    # Confidence tracks literature support for the stage note; class window alone
    # is a published order-of-magnitude label, not a star-specific lifetime.
    conf = float(lit.confidence) if stage else min(0.35, float(lit.confidence) + 0.1)
    if not lit.evidence:
        conf = 0.15  # class prior only — labeled low confidence
    return LifeExpectancy(
        optical_breakout_window=window,
        stellar_stage_note=stage,
        confidence=max(0.0, min(1.0, conf)),
        basis=basis,
    )


def _sn_potential(lit: Literature, star_class: str) -> float:
    """Inventory SN-potential score from literature features (not an explosion clock)."""
    class_prior = {
        "RSG": 1.0,
        "BSG": 0.9,
        "YSG": 0.85,
        "WR": 0.8,
        "LBV": 0.75,
        "AGN": 0.2,
    }.get(str(star_class), 0.5)
    # Prefer evolved_stage × confidence; keep a small class prior so empty-index
    # stars still appear for AOI filtering without fabricating literature scores.
    lit_term = 0.5 * float(lit.evolved_stage) + 0.5 * float(lit.confidence)
    if lit.evidence:
        score = 0.7 * lit_term + 0.3 * class_prior
    else:
        score = 0.25 * class_prior
    return max(0.0, min(1.0, score))


def _catalog_refs(row: dict[str, Any]) -> list[dict[str, str]]:
    refs = row.get("catalog_refs") or []
    if isinstance(refs, str):
        try:
            refs = json.loads(refs)
        except json.JSONDecodeError:
            refs = []
    out: list[dict[str, str]] = []
    for item in refs or []:
        if not isinstance(item, dict):
            continue
        bib = str(item.get("bibcode") or "").strip()
        cat = str(item.get("catalog") or "").strip()
        if bib and cat:
            out.append({"catalog": cat, "bibcode": bib})
    return out


def profile_from_row(
    row: dict[str, Any],
    *,
    index_rows: dict[str, dict[str, Any]] | None = None,
    reviewed_utc: str | None = None,
) -> ProgenitorProfile | None:
    """Build one ProgenitorProfile from a catalog row (+ optional literature index)."""
    star_id = _optional_str(row.get("star_id")) or ""
    ra = _float_or_none(row.get("ra_deg"))
    dec = _float_or_none(row.get("dec_deg"))
    if not star_id or ra is None or dec is None:
        return None
    star_class = _optional_str(row.get("class")) or "RSG"
    indexed = (index_rows or {}).get(star_id)
    lit = _lit_from_sources(row, indexed)
    life = _life_expectancy(star_class, lit)
    return ProgenitorProfile(
        star_id=star_id,
        common_name=_optional_str(row.get("common_name")),
        ra_deg=ra,
        dec_deg=dec,
        class_=star_class,
        spectral_type=_optional_str(row.get("spectral_type")) or "",
        distance_kpc=_float_or_none(row.get("distance_kpc")),
        extinction_av_mag=_float_or_none(row.get("extinction_av_mag")),
        composition=_composition_summary(row),
        life_expectancy=life,
        sn_potential=_sn_potential(lit, star_class),
        lit=lit,
        last_reviewed_utc=reviewed_utc or _utcnow_iso(),
        catalog_refs=_catalog_refs(row),
        simulated=bool(row.get("simulated", False)),
    )


def _load_source_rows(
    *,
    curated_path: Path | None = None,
    star_table_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Prefer the fuller local catalog.

    ``star_table.parquet`` may be a partial offline build (e.g. single-star
    seed). Fall back to curated when it has more complete SN-potential coverage.
    """
    curated = Path(curated_path) if curated_path else CURATED_PATH
    curated_rows = load_curated_stars(curated)
    table = Path(star_table_path) if star_table_path else STAR_TABLE_PATH
    table_rows: list[dict[str, Any]] = []
    if table.is_file():
        table_rows = load_star_table(table)
    if table_rows and len(table_rows) >= len(curated_rows):
        return table_rows
    if curated_rows:
        return curated_rows
    return table_rows


def build_inventory(
    *,
    out_path: Path | None = None,
    curated_path: Path | None = None,
    star_table_path: Path | None = None,
    index_path: Path | None = None,
    reviewed_utc: str | None = None,
) -> Path:
    """Write progenitor_inventory.parquet from local catalog + literature index."""
    rows = _load_source_rows(
        curated_path=curated_path, star_table_path=star_table_path
    )
    index_rows = load_index(index_path)
    reviewed = reviewed_utc or _utcnow_iso()
    profiles: list[ProgenitorProfile] = []
    for row in rows:
        profile = profile_from_row(row, index_rows=index_rows, reviewed_utc=reviewed)
        if profile is not None:
            profiles.append(profile)

    target = Path(out_path) if out_path is not None else INVENTORY_PATH
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    for p in profiles:
        blob = p.model_dump(mode="json", by_alias=True)
        # Flatten nested JSON columns for parquet.
        records.append(
            {
                "star_id": blob["star_id"],
                "common_name": blob.get("common_name"),
                "ra_deg": blob["ra_deg"],
                "dec_deg": blob["dec_deg"],
                "class": blob["class"],
                "spectral_type": blob.get("spectral_type") or "",
                "distance_kpc": blob.get("distance_kpc"),
                "extinction_av_mag": blob.get("extinction_av_mag"),
                "composition": blob.get("composition"),
                "life_expectancy_json": json.dumps(blob["life_expectancy"], sort_keys=True),
                "sn_potential": blob["sn_potential"],
                "lit_json": json.dumps(blob["lit"], sort_keys=True),
                "last_reviewed_utc": blob["last_reviewed_utc"],
                "catalog_refs_json": json.dumps(blob.get("catalog_refs") or []),
                "simulated": bool(blob.get("simulated")),
            }
        )
    df = pd.DataFrame(records)
    df.to_parquet(target, index=False)

    meta = {
        "path": str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target),
        "n_stars": len(profiles),
        "built_utc": reviewed,
        "sources": {
            "curated": str(CURATED_PATH.relative_to(ROOT)),
            "star_table": str(STAR_TABLE_PATH.relative_to(ROOT)),
            "literature_index": "backend/literature/index.parquet",
        },
        "note": (
            "Inventory consolidates public catalog + offline literature scores. "
            "Life expectancy optical_breakout_window is a class estimate; "
            "stellar_stage_note only appears when an ADS claim exists."
        ),
    }
    meta_path = target.with_name(target.stem + "_meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %d progenitor profiles to %s", len(profiles), target)
    return target


def _row_to_profile(record: dict[str, Any]) -> ProgenitorProfile | None:
    try:
        life_raw = record.get("life_expectancy_json") or record.get("life_expectancy")
        if isinstance(life_raw, str):
            life_raw = json.loads(life_raw)
        lit_raw = record.get("lit_json") or record.get("lit")
        if isinstance(lit_raw, str):
            lit_raw = json.loads(lit_raw) if lit_raw.strip() else {}
        refs_raw = record.get("catalog_refs_json") or record.get("catalog_refs") or []
        if isinstance(refs_raw, str):
            refs_raw = json.loads(refs_raw) if refs_raw.strip() else []
        lit = Literature.model_validate(lit_raw or {
            "mass_loss": 0.0,
            "variability": 0.0,
            "evolved_stage": 0.0,
            "confidence": 0.0,
            "evidence": [],
        })
        life = LifeExpectancy.model_validate(life_raw)
        return ProgenitorProfile(
            star_id=_optional_str(record.get("star_id")) or "",
            common_name=_optional_str(record.get("common_name")),
            ra_deg=float(record["ra_deg"]),
            dec_deg=float(record["dec_deg"]),
            class_=_optional_str(record.get("class")) or "RSG",
            spectral_type=_optional_str(record.get("spectral_type")) or "",
            distance_kpc=_float_or_none(record.get("distance_kpc")),
            extinction_av_mag=_float_or_none(record.get("extinction_av_mag")),
            composition=_optional_str(record.get("composition")),
            life_expectancy=life,
            sn_potential=_float_or_zero(record.get("sn_potential")),
            lit=lit,
            last_reviewed_utc=_optional_str(record.get("last_reviewed_utc")) or "",
            catalog_refs=list(refs_raw or []),
            simulated=bool(record.get("simulated", False)),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("skip bad inventory row star_id=%s: %s", record.get("star_id"), exc)
        return None


def load_inventory_rows(path: Path | None = None) -> list[ProgenitorProfile]:
    """Load inventory profiles (builds from curated if parquet missing)."""
    target = Path(path) if path is not None else INVENTORY_PATH
    if not target.is_file():
        build_inventory(out_path=target)
    if not target.is_file():
        return []
    df = pd.read_parquet(target)
    out: list[ProgenitorProfile] = []
    for record in df.to_dict(orient="records"):
        profile = _row_to_profile(record)
        if profile is not None:
            out.append(profile)
    return out


def load_inventory(path: Path | None = None) -> dict[str, ProgenitorProfile]:
    """Load inventory keyed by star_id."""
    return {p.star_id: p for p in load_inventory_rows(path)}


def inventory_status(path: Path | None = None) -> dict[str, Any]:
    """Status blob for CLI / health."""
    target = Path(path) if path is not None else INVENTORY_PATH
    meta_path = target.with_name(target.stem + "_meta.json")
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    n = 0
    if target.is_file():
        try:
            n = int(len(pd.read_parquet(target)))
        except Exception:  # noqa: BLE001
            n = 0
    return {
        "path": str(target),
        "exists": target.is_file(),
        "n_stars": n,
        "meta": meta,
    }


def upsert_profile(
    profile: ProgenitorProfile,
    *,
    path: Path | None = None,
) -> Path:
    """Insert or replace one profile in the inventory parquet."""
    target = Path(path) if path is not None else INVENTORY_PATH
    by_id = load_inventory(target) if target.is_file() else {}
    by_id[profile.star_id] = profile
    target.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for p in by_id.values():
        blob = p.model_dump(mode="json", by_alias=True)
        records.append(
            {
                "star_id": blob["star_id"],
                "common_name": blob.get("common_name"),
                "ra_deg": blob["ra_deg"],
                "dec_deg": blob["dec_deg"],
                "class": blob["class"],
                "spectral_type": blob.get("spectral_type") or "",
                "distance_kpc": blob.get("distance_kpc"),
                "extinction_av_mag": blob.get("extinction_av_mag"),
                "composition": blob.get("composition"),
                "life_expectancy_json": json.dumps(blob["life_expectancy"], sort_keys=True),
                "sn_potential": blob["sn_potential"],
                "lit_json": json.dumps(blob["lit"], sort_keys=True),
                "last_reviewed_utc": blob["last_reviewed_utc"],
                "catalog_refs_json": json.dumps(blob.get("catalog_refs") or []),
                "simulated": bool(blob.get("simulated")),
            }
        )
    pd.DataFrame(records).to_parquet(target, index=False)
    return target


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.progenitors.inventory",
        description="Build offline progenitor inventory parquet.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=INVENTORY_PATH,
        help="Output parquet path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    path = build_inventory(out_path=args.out)
    status = inventory_status(path)
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
