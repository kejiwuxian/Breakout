"""Judge Q&A function tools, read-only over the current run.

Tools: get_top_candidates, get_skymap_summary, get_breakout_countdown.
Answers must name the bibcode for every claim and say simulated when needed.
"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_state: dict[str, Any] = {
    "alert_id": None,
    "alert": None,
    "skymap": None,
    "candidates": [],
    "simulated": False,
}


def update_run_state(
    *,
    alert_id: str | None = None,
    alert: dict[str, Any] | None = None,
    skymap: dict[str, Any] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    simulated: bool | None = None,
) -> None:
    """Update the in-memory snapshot used by judge Q&A tools (current run only)."""
    with _lock:
        if alert_id is not None:
            _state["alert_id"] = alert_id
        if alert is not None:
            _state["alert"] = alert
            _state["alert_id"] = alert.get("alert_id", _state["alert_id"])
        if skymap is not None:
            _state["skymap"] = skymap
            _state["alert_id"] = skymap.get("alert_id", _state["alert_id"])
        if candidates is not None:
            _state["candidates"] = list(candidates)
        if simulated is not None:
            _state["simulated"] = bool(simulated)


def reset_run_state() -> None:
    """Clear the current-run snapshot (scenario start / tests)."""
    with _lock:
        _state["alert_id"] = None
        _state["alert"] = None
        _state["skymap"] = None
        _state["candidates"] = []
        _state["simulated"] = False


def _snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "alert_id": _state["alert_id"],
            "alert": _state["alert"],
            "skymap": _state["skymap"],
            "candidates": list(_state["candidates"]),
            "simulated": bool(_state["simulated"]),
        }


def _evidence_rows(cand: dict[str, Any]) -> list[dict[str, str]]:
    lit = cand.get("lit") if isinstance(cand.get("lit"), dict) else {}
    out: list[dict[str, str]] = []
    for item in lit.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        bib = str(item.get("bibcode") or "").strip()
        claim = str(item.get("claim") or "").strip()
        if not bib or not claim:
            continue
        out.append({"bibcode": bib, "claim": claim})
    return out


def get_top_candidates(*, limit: int = 5) -> dict[str, Any]:
    """Return top CandidateScore rows for the active alert (read-only)."""
    snap = _snapshot()
    rows = []
    for cand in snap["candidates"][: max(0, int(limit))]:
        if not isinstance(cand, dict):
            continue
        rows.append(
            {
                "star_id": cand.get("star_id"),
                "class": cand.get("class") or cand.get("class_"),
                "ra_deg": cand.get("ra_deg"),
                "dec_deg": cand.get("dec_deg"),
                "posterior": cand.get("posterior"),
                "p_sky": cand.get("p_sky"),
                "distance_kpc": cand.get("distance_kpc"),
                "ir_followup": cand.get("ir_followup"),
                "presn_watch": cand.get("presn_watch"),
                "breakout": cand.get("breakout"),
                "evidence": _evidence_rows(cand),
                "simulated": bool(cand.get("simulated", snap["simulated"])),
                "rank_confidence": cand.get("rank_confidence"),
                "rank_reasoning": cand.get("rank_reasoning"),
                "composition": cand.get("composition"),
                "life_expectancy": cand.get("life_expectancy"),
            }
        )
    return {
        "alert_id": snap["alert_id"],
        "candidates": rows,
        "simulated": bool(snap["simulated"]),
        "note": "Read-only current-run candidates; every claim carries an ADS bibcode.",
    }


def get_skymap_summary() -> dict[str, Any]:
    """Return a summary of the active SkyMap (read-only)."""
    snap = _snapshot()
    skymap = snap["skymap"] if isinstance(snap["skymap"], dict) else None
    if skymap is None:
        return {
            "alert_id": snap["alert_id"],
            "available": False,
            "simulated": bool(snap["simulated"]),
            "note": "No skymap in the current run yet.",
        }
    peak = skymap.get("peak") if isinstance(skymap.get("peak"), dict) else {}
    return {
        "alert_id": skymap.get("alert_id") or snap["alert_id"],
        "available": True,
        "nside": skymap.get("nside"),
        "ordering": skymap.get("ordering"),
        "frame": skymap.get("frame"),
        "credible_90_deg2": skymap.get("credible_90_deg2"),
        "peak": {
            "ra_deg": peak.get("ra_deg"),
            "dec_deg": peak.get("dec_deg"),
        },
        "components": list(skymap.get("components") or []),
        "simulated": bool(skymap.get("simulated", snap["simulated"])),
        "note": "Fused HEALPix NESTED map; coordinates are ICRS degrees.",
    }


def get_breakout_countdown(*, star_id: str | None = None) -> dict[str, Any]:
    """Return breakout countdown for the top or named candidate (read-only)."""
    snap = _snapshot()
    chosen: dict[str, Any] | None = None
    for cand in snap["candidates"]:
        if not isinstance(cand, dict):
            continue
        if star_id is None:
            chosen = cand
            break
        if str(cand.get("star_id")) == str(star_id):
            chosen = cand
            break
    if chosen is None:
        return {
            "alert_id": snap["alert_id"],
            "available": False,
            "star_id": star_id,
            "simulated": bool(snap["simulated"]),
            "note": "No matching candidate in the current run.",
        }
    breakout = chosen.get("breakout") if isinstance(chosen.get("breakout"), dict) else {}
    return {
        "alert_id": snap["alert_id"],
        "available": True,
        "star_id": chosen.get("star_id"),
        "class": chosen.get("class") or chosen.get("class_"),
        "class_window": breakout.get("class_window"),
        "countdown_from": breakout.get("countdown_from"),
        "evidence": _evidence_rows(chosen),
        "simulated": bool(chosen.get("simulated", snap["simulated"])),
        "note": "Breakout window is an estimate from progenitor class; label as estimate in UI.",
    }


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_top_candidates",
        "description": "Return top ranked candidates with bibcodes and simulated flags.",
    },
    {
        "type": "function",
        "name": "get_skymap_summary",
        "description": "Return fused sky map peak and credible region summary.",
    },
    {
        "type": "function",
        "name": "get_breakout_countdown",
        "description": "Return breakout class window and countdown for a candidate.",
    },
]
