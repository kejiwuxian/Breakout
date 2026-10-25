"""Runtime AOI ranking with inventory enrichment (+ optional live Grok).

Trigger path stays offline-safe: when ``USE_CACHED_STREAM=True`` or XAI key is
missing, ranking is deterministic (``literature.rerank``) and inventory fields
are attached without calling Grok. Live Grok shortlist ranking runs only when
keys are present and cached-stream mode is off.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from backend.config import settings
from backend.literature.rerank import rerank
from backend.progenitors.inventory import (
    INVENTORY_PATH,
    ProgenitorProfile,
    load_inventory,
)
from backend.schemas import CandidateScore, LifeExpectancyInfo, SkyMap

logger = logging.getLogger("breakout.progenitors.rank_runtime")

XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"
XAI_MODEL_DEFAULT = "grok-2-latest"


def _live_grok_allowed() -> bool:
    if settings.use_cached_stream:
        return False
    return bool((settings.xai_api_key or "").strip())


def _enrich_row(row: dict[str, Any], profile: ProgenitorProfile | None) -> dict[str, Any]:
    """Attach inventory profile fields onto a filter candidate row."""
    hit = dict(row)
    if profile is None:
        return hit
    # Prefer inventory spectral/distance when catalog left them null.
    if not hit.get("spectral_type") and profile.spectral_type:
        hit["spectral_type"] = profile.spectral_type
    if hit.get("distance_kpc") is None and profile.distance_kpc is not None:
        hit["distance_kpc"] = profile.distance_kpc
    if hit.get("extinction_av_mag") is None and profile.extinction_av_mag is not None:
        hit["extinction_av_mag"] = profile.extinction_av_mag
    # Seed lit from inventory when row lacks scored lit (rerank also reads index).
    if not hit.get("lit") and not hit.get("lit_json"):
        hit["lit"] = profile.lit.model_dump(mode="json")
    hit["_inventory"] = profile
    return hit


def _attach_inventory_fields(
    score: CandidateScore,
    profile: ProgenitorProfile | None,
    *,
    rank_confidence: float | None = None,
    rank_reasoning: str | None = None,
) -> CandidateScore:
    updates: dict[str, Any] = {}
    if profile is not None:
        updates["life_expectancy"] = LifeExpectancyInfo.model_validate(
            profile.life_expectancy.model_dump(mode="json")
        )
        updates["composition"] = profile.composition
        if rank_confidence is None:
            # Offline confidence: blend inventory SN-potential with lit confidence.
            updates["rank_confidence"] = float(
                0.5 * profile.sn_potential + 0.5 * profile.lit.confidence
            )
        if rank_reasoning is None:
            stage = profile.life_expectancy.stellar_stage_note
            updates["rank_reasoning"] = (
                "Offline inventory rank: posterior from p_sky × class × literature "
                f"confidence; SN-potential={profile.sn_potential:.2f}; "
                f"life window={profile.life_expectancy.optical_breakout_window} "
                f"({profile.life_expectancy.basis})."
                + (f" Stage note: {stage}" if stage else "")
            )
    if rank_confidence is not None:
        updates["rank_confidence"] = float(max(0.0, min(1.0, rank_confidence)))
    if rank_reasoning is not None:
        updates["rank_reasoning"] = rank_reasoning
    if not updates:
        return score
    return score.model_copy(update=updates)


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1)
    else:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    return json.loads(stripped)


def _build_rank_prompt(
    alert_id: str,
    shortlist: list[CandidateScore],
    profiles: dict[str, ProgenitorProfile],
) -> str:
    rows = []
    for i, s in enumerate(shortlist, start=1):
        prof = profiles.get(s.star_id)
        rows.append(
            {
                "rank_seed": i,
                "star_id": s.star_id,
                "class": s.class_,
                "spectral_type": s.spectral_type,
                "ra_deg": s.ra_deg,
                "dec_deg": s.dec_deg,
                "distance_kpc": s.distance_kpc,
                "p_sky": s.p_sky,
                "posterior_seed": s.posterior,
                "lit_confidence": s.lit.confidence,
                "composition": (prof.composition if prof else None),
                "life_expectancy": (
                    prof.life_expectancy.model_dump(mode="json") if prof else None
                ),
                "sn_potential": (prof.sn_potential if prof else None),
                "evidence_bibcodes": [e.bibcode for e in s.lit.evidence],
            }
        )
    return (
        "You rank galactic supernova progenitor candidates inside a neutrino "
        "localization for BREAKOUT.\n"
        "Use ONLY the shortlist JSON below. Do not invent stars, bibcodes, "
        "coordinates, distances, or lifetimes.\n"
        "Return ONLY JSON:\n"
        "{\n"
        '  "rankings": [\n'
        "    {\n"
        '      "star_id": "<must match shortlist>",\n'
        '      "confidence": float 0..1,\n'
        '      "reasoning": "<brief; cite only provided bibcodes>"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Include every shortlist star_id exactly once, ordered best→worst.\n\n"
        f"ALERT_ID: {alert_id}\n"
        f"SHORTLIST:\n{json.dumps(rows, indent=2)}\n"
    )


def _grok_rank_shortlist(
    alert_id: str,
    shortlist: list[CandidateScore],
    profiles: dict[str, ProgenitorProfile],
    *,
    api_key: str,
    http_post: Any | None = None,
) -> dict[str, dict[str, Any]]:
    """Call Grok; return star_id → {confidence, reasoning}. Drops unknown ids."""
    prompt = _build_rank_prompt(alert_id, shortlist, profiles)
    body = {
        "model": XAI_MODEL_DEFAULT,
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You rank stellar progenitors from provided inventory only. "
                    "Never invent citations or stars."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    poster = http_post or httpx.post
    resp = poster(XAI_CHAT_URL, headers=headers, json=body, timeout=60.0)
    resp.raise_for_status()
    payload = resp.json()
    content = ""
    choices = payload.get("choices") or []
    if choices:
        content = str((choices[0].get("message") or {}).get("content") or "")
    parsed = _parse_json_object(content)
    allowed = {s.star_id for s in shortlist}
    out: dict[str, dict[str, Any]] = {}
    for item in parsed.get("rankings") or []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("star_id") or "").strip()
        if sid not in allowed or sid in out:
            continue
        try:
            conf = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        out[sid] = {
            "confidence": max(0.0, min(1.0, conf)),
            "reasoning": str(item.get("reasoning") or "").strip() or None,
            "order": len(out),
        }
    return out


def _apply_grok_order(
    scores: list[CandidateScore],
    grok: dict[str, dict[str, Any]],
    profiles: dict[str, ProgenitorProfile],
) -> list[CandidateScore]:
    """Reorder by Grok ranking; renormalize posterior by Grok confidence × p_sky."""
    if not grok:
        return [
            _attach_inventory_fields(s, profiles.get(s.star_id)) for s in scores
        ]

    def sort_key(s: CandidateScore) -> tuple[int, float]:
        info = grok.get(s.star_id)
        if info is None:
            return (10_000, -s.posterior)
        return (int(info["order"]), -float(info["confidence"]))

    ordered = sorted(scores, key=sort_key)
    weights: list[float] = []
    for s in ordered:
        info = grok.get(s.star_id) or {}
        conf = float(info.get("confidence", s.lit.confidence))
        weights.append(max(s.p_sky, 0.0) * max(conf, 1e-6))
    total = sum(weights)
    out: list[CandidateScore] = []
    for s, w in zip(ordered, weights, strict=True):
        info = grok.get(s.star_id) or {}
        posterior = (w / total) if total > 0 else 0.0
        enriched = s.model_copy(update={"posterior": float(posterior)})
        out.append(
            _attach_inventory_fields(
                enriched,
                profiles.get(s.star_id),
                rank_confidence=info.get("confidence"),
                rank_reasoning=info.get("reasoning")
                or "Grok ranking applied; reasoning empty.",
            )
        )
    return out


def rank_with_grok(
    candidates: list[dict[str, Any]],
    *,
    skymap: SkyMap,
    t0_utc: str,
    watchlist: set[str] | None = None,
    prob: np.ndarray | None = None,
    inventory_path: Path | None = None,
    index: Path | dict[str, dict[str, Any]] | None = None,
    http_post: Any | None = None,
    force_offline: bool | None = None,
) -> list[CandidateScore]:
    """Filter-AOI candidates → inventory enrich → rank (+ optional live Grok).

    Always returns a sorted ``list[CandidateScore]`` with optional v1.1 fields
    ``rank_confidence``, ``rank_reasoning``, ``life_expectancy``, ``composition``.
    """
    t0 = time.perf_counter()
    inv_path = Path(inventory_path) if inventory_path else INVENTORY_PATH
    try:
        profiles = load_inventory(inv_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("inventory load failed: %s — ranking without profiles", exc)
        profiles = {}

    enriched_rows = [
        _enrich_row(row, profiles.get(str(row.get("star_id")))) for row in candidates
    ]

    scores = rerank(
        enriched_rows,
        index,
        watchlist,
        skymap=skymap,
        t0_utc=t0_utc,
        prob=prob,
    )

    offline = force_offline if force_offline is not None else not _live_grok_allowed()
    if offline or not scores:
        out = [_attach_inventory_fields(s, profiles.get(s.star_id)) for s in scores]
        logger.info(
            "rank_with_grok mode=offline n=%d elapsed_s=%.4f",
            len(out),
            time.perf_counter() - t0,
        )
        return out

    try:
        grok = _grok_rank_shortlist(
            skymap.alert_id,
            scores,
            profiles,
            api_key=settings.xai_api_key,
            http_post=http_post,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("live Grok rank failed; offline fallback: %s", exc)
        out = [_attach_inventory_fields(s, profiles.get(s.star_id)) for s in scores]
        return out

    out = _apply_grok_order(scores, grok, profiles)
    logger.info(
        "rank_with_grok mode=live_grok n=%d elapsed_s=%.4f top=%s",
        len(out),
        time.perf_counter() - t0,
        out[0].star_id if out else None,
    )
    return out
