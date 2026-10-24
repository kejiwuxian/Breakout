"""LIVE: lookup + rerank candidates; no LLM call.

Reads the offline index when present and returns CandidateScore rows (v1).
Ranking: P ∝ p_sky × w_class × w_lit × w_watch. No network / LLM.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import healpy as hp
import numpy as np

from backend.config import ROOT
from backend.literature.build_index import INDEX_PATH
from backend.physics.breakout_window import breakout_countdown
from backend.physics.extinction import apply_extinction_flag
from backend.schemas import (
    CandidateScore,
    Evidence,
    Literature,
    SkyMap,
    StarClass,
)

# Relative class weights (dimensionless ranking priors; not observational rates).
CLASS_WEIGHT: dict[str, float] = {
    "RSG": 1.0,
    "BSG": 0.9,
    "YSG": 0.85,
    "WR": 0.8,
    "LBV": 0.75,
}


def _p_sky_at(skymap: SkyMap, ra_deg: float, dec_deg: float, prob: np.ndarray | None = None) -> float:
    if prob is None:
        fits = Path(skymap.prob_path)
        if not fits.is_file():
            fits = ROOT / skymap.prob_path
        prob = np.asarray(hp.read_map(str(fits), nest=True))
    ipix = int(hp.ang2pix(skymap.nside, ra_deg, dec_deg, nest=True, lonlat=True))
    return float(prob[ipix])


def _lit_from_row(row: dict[str, Any], index_rows: dict[str, dict[str, Any]]) -> Literature:
    """Build Literature from curated row or offline index; never invent bibcodes."""
    star_id = str(row.get("star_id", ""))
    indexed = index_rows.get(star_id)
    src = indexed if indexed is not None else row.get("lit")
    if isinstance(src, Literature):
        return src
    if isinstance(src, dict):
        evidence_raw = src.get("evidence") or []
        evidence: list[Evidence] = []
        for item in evidence_raw:
            bib = str(item.get("bibcode", "")).strip()
            claim = str(item.get("claim", "")).strip()
            if bib and claim:
                evidence.append(Evidence(bibcode=bib, claim=claim))
        return Literature(
            mass_loss=float(src.get("mass_loss", 0.0) or 0.0),
            variability=float(src.get("variability", 0.0) or 0.0),
            evolved_stage=float(src.get("evolved_stage", 0.0) or 0.0),
            confidence=float(src.get("confidence", 0.0) or 0.0),
            evidence=evidence,
        )
    return Literature(
        mass_loss=0.0,
        variability=0.0,
        evolved_stage=0.0,
        confidence=0.0,
        evidence=[],
    )


def _load_index(index_path: Path) -> dict[str, dict[str, Any]]:
    path = Path(index_path)
    if not path.is_file():
        return {}
    try:
        import pandas as pd

        df = pd.read_parquet(path)
        if "star_id" not in df.columns:
            return {}
        return {str(r["star_id"]): r for r in df.to_dict(orient="records")}
    except Exception:
        return {}


def rerank(
    candidates: list[dict[str, Any]],
    skymap: SkyMap,
    *,
    index_path: Path = INDEX_PATH,
    watchlist: set[str] | None = None,
    t0_utc: str | None = None,
    prob: np.ndarray | None = None,
) -> list[CandidateScore]:
    """Lookup literature scores and compute posteriors for candidates.

    No network / LLM. Missing index → lit scores of 0 with empty evidence.
    Applies breakout countdown and extinction IR flag.
    """
    watch = watchlist or set()
    index_rows = _load_index(index_path)
    if prob is None:
        fits = Path(skymap.prob_path)
        if not fits.is_file():
            fits = ROOT / skymap.prob_path
        prob = np.asarray(hp.read_map(str(fits), nest=True))

    countdown_from = t0_utc or "1970-01-01T00:00:00Z"
    weighted: list[tuple[float, CandidateScore]] = []

    for row in candidates:
        star_id = str(row["star_id"])
        ra = float(row["ra_deg"])
        dec = float(row["dec_deg"])
        star_class = str(row.get("class", "RSG"))
        if star_class not in CLASS_WEIGHT:
            star_class = "RSG"
        lit = _lit_from_row(row, index_rows)
        p_sky = _p_sky_at(skymap, ra, dec, prob=prob)
        w_class = CLASS_WEIGHT[star_class]
        w_lit = 0.25 + 0.75 * float(lit.confidence)  # keep zero-confidence stars alive
        w_watch = 2.0 if star_id in watch or bool(row.get("presn_watch")) else 1.0
        weight = max(p_sky, 0.0) * w_class * w_lit * w_watch

        score = CandidateScore(
            star_id=star_id,
            ra_deg=ra,
            dec_deg=dec,
            class_=star_class,  # type: ignore[arg-type]
            spectral_type=str(row.get("spectral_type") or ""),
            distance_kpc=row.get("distance_kpc"),
            extinction_av_mag=row.get("extinction_av_mag"),
            p_sky=p_sky,
            lit=lit,
            presn_watch=star_id in watch or bool(row.get("presn_watch")),
            posterior=0.0,
            breakout=breakout_countdown(star_class, t0_utc=countdown_from),  # type: ignore[arg-type]
            ir_followup=False,
            simulated=bool(skymap.simulated or row.get("simulated", False)),
        )
        score = apply_extinction_flag(score)
        weighted.append((weight, score))

    total = sum(w for w, _ in weighted)
    out: list[CandidateScore] = []
    for weight, score in sorted(weighted, key=lambda t: t[0], reverse=True):
        posterior = (weight / total) if total > 0 else 0.0
        out.append(score.model_copy(update={"posterior": float(posterior)}))
    return out
