"""LIVE: lookup + rerank candidates; no LLM or network call.

``rerank(candidates, index, watchlist)`` → ``list[CandidateScore]`` sorted by
posterior, with P ∝ p_sky × w_class × w_lit × w_watch and normalized over the
candidate set. Weights live in ``backend.config``. ``w_lit`` comes from
``backend/literature/index.parquet`` confidence. Run time is logged and must
stay seconds or less on the trigger path.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import healpy as hp
import numpy as np

from backend.config import (
    RANKING_CLASS_WEIGHT,
    RANKING_WATCH_BOOST,
    RANKING_W_LIT_FLOOR,
    RANKING_W_LIT_SCALE,
    ROOT,
    settings,
)
from backend.literature.build_index import INDEX_PATH
from backend.physics.breakout_window import breakout_countdown
from backend.physics.extinction import apply_extinction_flag, extinction_decision
from backend.schemas import CandidateScore, Evidence, Literature, SkyMap

logger = logging.getLogger("breakout.literature.rerank")

# Re-export config weights for tests / callers.
CLASS_WEIGHT: dict[str, float] = dict(RANKING_CLASS_WEIGHT)
# Keep AGN in the live weight map even if settings.ranking_weights was frozen earlier.
if "AGN" not in CLASS_WEIGHT:
    CLASS_WEIGHT["AGN"] = float(RANKING_CLASS_WEIGHT.get("AGN", 0.7))


def _class_weights() -> dict[str, float]:
    weights = dict(RANKING_CLASS_WEIGHT)
    rw = settings.ranking_weights or {}
    for key, value in rw.items():
        if key.startswith("class_"):
            weights[key.removeprefix("class_")] = float(value)
    return weights


def _watch_boost() -> float:
    rw = settings.ranking_weights or {}
    if "watch_boost" in rw:
        return float(rw["watch_boost"])
    return float(RANKING_WATCH_BOOST)


def _w_lit_params() -> tuple[float, float]:
    rw = settings.ranking_weights or {}
    floor = float(rw.get("w_lit_floor", RANKING_W_LIT_FLOOR))
    scale = float(rw.get("w_lit_scale", RANKING_W_LIT_SCALE))
    return floor, scale


def _p_sky_at(
    skymap: SkyMap,
    ra_deg: float,
    dec_deg: float,
    prob: np.ndarray | None = None,
) -> float:
    if prob is None:
        fits = Path(skymap.prob_path)
        if not fits.is_file():
            fits = ROOT / skymap.prob_path
        prob = np.asarray(hp.read_map(str(fits), nest=True))
    ipix = int(hp.ang2pix(skymap.nside, ra_deg, dec_deg, nest=True, lonlat=True))
    return float(prob[ipix])


def _parse_evidence(src: dict[str, Any]) -> list[Evidence]:
    """Parse evidence list or evidence_json string; skip empty bibcodes."""
    evidence_raw = src.get("evidence") or []
    if not evidence_raw and src.get("evidence_json"):
        raw = src["evidence_json"]
        if isinstance(raw, str) and raw.strip():
            evidence_raw = json.loads(raw)
        elif isinstance(raw, list):
            evidence_raw = raw
    evidence: list[Evidence] = []
    for item in evidence_raw or []:
        if not isinstance(item, dict):
            continue
        bib = str(item.get("bibcode", "")).strip()
        claim = str(item.get("claim", "")).strip()
        if bib and claim:
            evidence.append(Evidence(bibcode=bib, claim=claim))
    return evidence


def _float_or_zero(value: Any) -> float:
    if value is None:
        return 0.0
    # Vincent curated lit scores may be ``{value, reason}`` with qualitative text.
    if isinstance(value, dict):
        inner = value.get("value")
        if isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return float(inner)
        return 0.0
    try:
        if isinstance(value, float) and np.isnan(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _lit_from_row(row: dict[str, Any], index_rows: dict[str, dict[str, Any]]) -> Literature:
    """Build Literature from offline index (preferred) or row; never invent bibcodes."""
    star_id = str(row.get("star_id", ""))
    indexed = index_rows.get(star_id)
    src = indexed if indexed is not None else row.get("lit")
    if src is None and row.get("lit_json"):
        raw = row["lit_json"]
        if isinstance(raw, str) and raw.strip():
            try:
                src = json.loads(raw)
            except json.JSONDecodeError:
                src = None
    if isinstance(src, Literature):
        return src
    if isinstance(src, dict):
        return Literature(
            mass_loss=_float_or_zero(src.get("mass_loss", 0.0)),
            variability=_float_or_zero(src.get("variability", 0.0)),
            evolved_stage=_float_or_zero(src.get("evolved_stage", 0.0)),
            confidence=_float_or_zero(src.get("confidence", 0.0)),
            evidence=_parse_evidence(src),
        )
    return Literature(
        mass_loss=0.0,
        variability=0.0,
        evolved_stage=0.0,
        confidence=0.0,
        evidence=[],
    )


def load_index(index: Path | dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Load literature index rows keyed by star_id. No network."""
    if isinstance(index, dict):
        return {str(k): v for k, v in index.items()}
    path = Path(index) if index is not None else INDEX_PATH
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


def _resolve_p_sky(
    row: dict[str, Any],
    *,
    skymap: SkyMap | None,
    prob: np.ndarray | None,
) -> float:
    if row.get("p_sky") is not None:
        return max(_float_or_zero(row.get("p_sky")), 0.0)
    if skymap is None:
        return 0.0
    return max(
        _p_sky_at(skymap, float(row["ra_deg"]), float(row["dec_deg"]), prob=prob),
        0.0,
    )


def rerank(
    candidates: list[dict[str, Any]],
    index: Path | dict[str, dict[str, Any]] | SkyMap | None = None,
    watchlist: set[str] | None = None,
    *,
    skymap: SkyMap | None = None,
    t0_utc: str | None = None,
    prob: np.ndarray | None = None,
    index_path: Path | None = None,
) -> list[CandidateScore]:
    """Rerank candidates by normalized posterior; no LLM / network.

    Parameters
    ----------
    candidates:
        Filtered star rows (optionally already carrying ``p_sky``).
    index:
        Path to ``index.parquet``, an in-memory star_id→row map, or (legacy)
        a ``SkyMap`` as the second positional argument.
    watchlist:
        Star ids boosted by ``w_watch`` (presn Stage 0).
    """
    t_start = time.perf_counter()

    # Legacy: rerank(candidates, skymap, watchlist=...)
    if isinstance(index, SkyMap):
        skymap = index
        index = index_path if index_path is not None else INDEX_PATH
    elif index is None:
        index = index_path if index_path is not None else INDEX_PATH

    watch = watchlist or set()
    index_rows = load_index(index)
    class_w = _class_weights()
    watch_boost = _watch_boost()
    w_lit_floor, w_lit_scale = _w_lit_params()

    countdown_from = t0_utc or "1970-01-01T00:00:00Z"

    weighted: list[tuple[float, CandidateScore, dict[str, Any]]] = []

    for row in candidates:
        star_id = str(row["star_id"])
        ra = float(row["ra_deg"])
        dec = float(row["dec_deg"])
        star_class = str(row.get("class") or "UNK")
        if star_class not in class_w:
            # Unknown / field catalog star — do not silently promote to RSG.
            star_class = "UNK" if "UNK" in class_w else "RSG"

        lit = _lit_from_row(row, index_rows)
        p_sky = _resolve_p_sky(row, skymap=skymap, prob=prob)
        w_class = float(class_w[star_class])
        w_lit = w_lit_floor + w_lit_scale * float(lit.confidence)
        on_watch = star_id in watch or bool(row.get("presn_watch"))
        w_watch = watch_boost if on_watch else 1.0
        weight = p_sky * w_class * w_lit * w_watch

        av = row.get("extinction_av_mag")
        if av is not None:
            try:
                av = float(av)
            except (TypeError, ValueError):
                av = None

        vmag = row.get("vmag")
        try:
            vmag_f = float(vmag) if vmag is not None else None
        except (TypeError, ValueError):
            vmag_f = None

        score = CandidateScore(
            star_id=star_id,
            ra_deg=ra,
            dec_deg=dec,
            class_=star_class,  # type: ignore[arg-type]
            spectral_type=str(row.get("spectral_type") or ""),
            distance_kpc=row.get("distance_kpc"),
            extinction_av_mag=av,
            p_sky=p_sky,
            lit=lit,
            presn_watch=on_watch,
            posterior=0.0,
            breakout=breakout_countdown(star_class, t0_utc=str(countdown_from)),
            ir_followup=False,
            simulated=bool(
                (skymap.simulated if skymap is not None else False)
                or row.get("simulated", False)
            ),
            vmag=vmag_f,
        )
        decision = extinction_decision(
            ra_deg=ra, dec_deg=dec, extinction_av_mag=score.extinction_av_mag
        )
        score = apply_extinction_flag(score)
        meta = {
            "weight": weight,
            "w_class": w_class,
            "w_lit": w_lit,
            "w_watch": w_watch,
            "extinction_reason": decision.reason,
        }
        weighted.append((weight, score, meta))

    total = sum(w for w, _, _ in weighted)
    out: list[CandidateScore] = []
    for weight, score, meta in sorted(weighted, key=lambda t: t[0], reverse=True):
        posterior = (weight / total) if total > 0 else 0.0
        out.append(score.model_copy(update={"posterior": float(posterior)}))
        logger.debug(
            "rerank star_id=%s posterior=%.6f p_sky=%.6e w_class=%.3f w_lit=%.3f "
            "w_watch=%.3f ir=%s reason=%s",
            score.star_id,
            posterior,
            score.p_sky,
            meta["w_class"],
            meta["w_lit"],
            meta["w_watch"],
            score.ir_followup,
            meta["extinction_reason"],
        )

    elapsed_s = time.perf_counter() - t_start
    logger.info(
        "rerank n=%d elapsed_s=%.4f top=%s",
        len(out),
        elapsed_s,
        out[0].star_id if out else None,
    )
    return out
