"""Core alert → localization → candidates pipeline with stage latency logs."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import healpy as hp
import numpy as np

from backend.candidates.catalog import CURATED_PATH, build_star_table, load_curated_stars
from backend.candidates.filter import filter_candidates
from backend.config import ROOT, settings
from backend.literature.rerank import rerank
from backend.localize.fuse import fuse
from backend.schemas import Alert, CandidateScore, SkyMap

logger = logging.getLogger("breakout.pipeline")

# In-memory Stage 0 watchlist (star_id).
_watchlist: set[str] = set()


def get_watchlist() -> set[str]:
    return set(_watchlist)


def reset_watchlist() -> None:
    _watchlist.clear()


def _stage(name: str, t0: float) -> float:
    dt_ms = (time.perf_counter() - t0) * 1000.0
    logger.info("stage=%s latency_ms=%.2f", name, dt_ms)
    return dt_ms


def apply_presn_watchlist(alert: Alert) -> set[str]:
    """Mark curated stars for Stage 0 watch (presn_watch) and return the set."""
    global _watchlist
    t0 = time.perf_counter()
    stars = load_curated_stars()
    # Combined KamLAND+Super-K pre-SN has no direction; raise all curated stars.
    added = {str(s["star_id"]) for s in stars if s.get("star_id")}
    _watchlist |= added
    _stage("presn_watchlist", t0)
    return set(_watchlist)


def process_sn_burst(
    alert: Alert,
    *,
    out_root: Path | None = None,
) -> tuple[SkyMap, list[CandidateScore], dict[str, Any]]:
    """SN_BURST / HE_NEUTRINO path: fuse → filter → rerank (+ clocks / dust)."""
    latencies: dict[str, float] = {}

    t0 = time.perf_counter()
    skymap = fuse(alert, out_root=out_root)
    latencies["fuse_ms"] = _stage("fuse", t0)

    fits = Path(skymap.prob_path)
    if not fits.is_file():
        fits = ROOT / skymap.prob_path
    prob = np.asarray(hp.read_map(str(fits), nest=True))

    t0 = time.perf_counter()
    table = build_star_table(use_network=False)
    if not Path(table).is_file():
        table = CURATED_PATH
    rows = filter_candidates(skymap, Path(table), prob=prob)
    latencies["filter_ms"] = _stage("filter", t0)

    t0 = time.perf_counter()
    scores = rerank(
        rows,
        skymap,
        watchlist=_watchlist,
        t0_utc=alert.t0_utc,
        prob=prob,
    )
    latencies["rerank_ms"] = _stage("rerank", t0)

    actions_payload: dict[str, Any] = {
        "lcogt_dry_run": bool(settings.lcogt_dry_run),
        "alert_id": alert.alert_id,
        "top_star_id": scores[0].star_id if scores else None,
        "note": "Action drafts (LCOGT/ToO/GCN) filled by actions/ modules.",
    }
    return skymap, scores, {"latencies_ms": latencies, "actions": actions_payload}


def process_alert(
    alert: Alert,
    *,
    out_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Run the per-alert pipeline and return ordered WS event dicts.

    Each event: ``{ type, payload, simulated }``.
    """
    events: list[dict[str, Any]] = []
    simulated = bool(alert.simulated)
    events.append(
        {
            "type": "alert",
            "payload": alert.model_dump(mode="json"),
            "simulated": simulated,
        }
    )

    if alert.kind == "PRESN":
        watch = apply_presn_watchlist(alert)
        events.append(
            {
                "type": "actions",
                "payload": {
                    "presn_watchlist": sorted(watch),
                    "note": "Stage 0 watchlist updated; awaiting SN_BURST.",
                },
                "simulated": simulated,
            }
        )
        return events

    if alert.kind in {"SN_BURST", "HE_NEUTRINO"}:
        skymap, scores, meta = process_sn_burst(alert, out_root=out_root)
        events.append(
            {
                "type": "skymap",
                "payload": skymap.model_dump(mode="json"),
                "simulated": bool(skymap.simulated),
            }
        )
        events.append(
            {
                "type": "candidates",
                "payload": {
                    "alert_id": alert.alert_id,
                    "candidates": [s.model_dump(mode="json", by_alias=True) for s in scores],
                },
                "simulated": simulated or any(s.simulated for s in scores),
            }
        )
        events.append(
            {
                "type": "actions",
                "payload": meta["actions"],
                "simulated": simulated,
            }
        )
        return events

    return events
