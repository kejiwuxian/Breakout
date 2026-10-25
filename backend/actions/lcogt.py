"""LCOGT RequestGroup builder (dry-run by default).

LCOGT_DRY_RUN stays True by default; nothing is submitted without a person.
When dry-run, write ``data/run/<alert_id>/lcogt_request.json`` and never call
the LCO API. ``LCOGT_API_TOKEN`` is read only when ``LCOGT_DRY_RUN=False``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend import config as config_mod
from backend.schemas import CandidateScore

logger = logging.getLogger("breakout.actions.lcogt")

LCO_API_URL = "https://observe.lco.global/api/requestgroups/"

# Optical (low extinction) vs redder/near-IR when ir_followup is recommended.
# Filter codes are LCO Sinistro optical_elements names (not invented fluxes).
FILTERS_OPTICAL = ("gp", "rp", "ip")
FILTERS_IR = ("ip", "zs", "Y")

INSTRUMENT_TYPE = "1M0-SCICAM-SINISTRO"
TELESCOPE_CLASS = "1m0"
EXPOSURE_TIME_S = 60.0
EXPOSURE_COUNT = 1
IPP_VALUE = 1.05


def _filters_for(candidate: CandidateScore) -> tuple[str, ...]:
    """Choose filter set from ``ir_followup`` (catalog A_V threshold), not invented A_V."""
    if candidate.ir_followup:
        return FILTERS_IR
    return FILTERS_OPTICAL


def _lookup_pm(star_id: str) -> tuple[float, float, float]:
    """Return (pmra_mas_yr, pmdec_mas_yr, epoch_year) from catalog when published.

    Never invents PM: missing fields → (0, 0, 2000) for LCO schema defaults.
    """
    try:
        from backend.candidates.catalog import load_curated_stars

        for row in load_curated_stars():
            if str(row.get("star_id")) != star_id:
                continue
            pmra = row.get("pmra_mas_yr", row.get("pmra"))
            pmdec = row.get("pmdec_mas_yr", row.get("pmdec"))
            epoch = row.get("epoch_year", row.get("ref_epoch", 2000.0))
            return (
                float(pmra) if pmra is not None else 0.0,
                float(pmdec) if pmdec is not None else 0.0,
                float(epoch) if epoch is not None else 2000.0,
            )
    except Exception:
        logger.debug("lcogt_pm_lookup_failed star_id=%s", star_id, exc_info=True)
    return 0.0, 0.0, 2000.0


def _target_from_candidate(candidate: CandidateScore) -> dict[str, Any]:
    """ICRS target; attach published PM when the curated catalog has it."""
    pmra, pmdec, epoch = _lookup_pm(candidate.star_id)
    return {
        "name": candidate.star_id,
        "type": "ICRS",
        "ra": float(candidate.ra_deg),
        "dec": float(candidate.dec_deg),
        "proper_motion_ra": pmra,
        "proper_motion_dec": pmdec,
        "epoch": epoch,
        "parallax": 0.0,
    }


def _window_utc(hours: float = 24.0) -> list[dict[str, str]]:
    """Observation window starting now (UTC). Duration is a scheduling draft, not data."""
    start = datetime.now(timezone.utc).replace(microsecond=0)
    end = start + timedelta(hours=hours)
    return [
        {
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    ]


def build_request_group(
    candidate: CandidateScore,
    *,
    proposal: str | None = None,
    dry_run: bool | None = None,
    alert_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Build an LCO observe API RequestGroup JSON for the top candidate.

    Targets the candidate RA/Dec (ICRS degrees). Filters follow ``ir_followup``.
    When dry_run is True, do not call the LCO API.
    """
    if dry_run is None:
        dry_run = bool(config_mod.settings.lcogt_dry_run)
    proposal_id = (
        proposal if proposal is not None else config_mod.settings.lcogt_proposal
    ) or ""
    filters = _filters_for(candidate)
    group_name = name or (
        f"BREAKOUT-{alert_id or 'alert'}-{candidate.star_id}".replace(" ", "_")[:50]
    )

    configurations: list[dict[str, Any]] = []
    for filt in filters:
        configurations.append(
            {
                "type": "EXPOSE",
                "instrument_type": INSTRUMENT_TYPE,
                "instrument_configs": [
                    {
                        "exposure_time": EXPOSURE_TIME_S,
                        "exposure_count": EXPOSURE_COUNT,
                        "mode": "full_frame",
                        "optical_elements": {"filter": filt},
                        "extra_params": {},
                    }
                ],
                "acquisition_config": {"mode": "OFF", "extra_params": {}},
                "guiding_config": {"mode": "ON", "optional": True, "extra_params": {}},
                "constraints": {
                    "max_airmass": 2.0,
                    "min_lunar_distance": 30.0,
                    "max_lunar_phase": 1.0,
                },
                "target": _target_from_candidate(candidate),
            }
        )

    request_group: dict[str, Any] = {
        "name": group_name,
        "proposal": proposal_id,
        "ipp_value": IPP_VALUE,
        "operator": "SINGLE",
        "observation_type": "RAPID_RESPONSE",
        "requests": [
            {
                "acceptability_threshold": 90,
                "configuration_repeats": 1,
                "configurations": configurations,
                "location": {"telescope_class": TELESCOPE_CLASS},
                "windows": _window_utc(),
            }
        ],
        # BREAKOUT provenance (not part of LCO submit schema; stripped on submit).
        "breakout": {
            "star_id": candidate.star_id,
            "ir_followup": bool(candidate.ir_followup),
            "filters": list(filters),
            "simulated": bool(candidate.simulated),
            "dry_run": bool(dry_run),
            "alert_id": alert_id,
        },
        "simulated": bool(candidate.simulated),
    }
    return request_group


def write_request_group(
    request: dict[str, Any],
    *,
    alert_id: str,
    run_dir: Path,
) -> Path:
    """Write RequestGroup JSON to data/run/<alert_id>/lcogt_request.json."""
    out_dir = Path(run_dir) / alert_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "lcogt_request.json"
    path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("lcogt_request_written path=%s dry_run=%s", path, request.get("breakout", {}).get("dry_run"))
    return path


def submit_request_group(request: dict[str, Any]) -> dict[str, Any]:
    """POST RequestGroup to LCO. Only called when LCOGT_DRY_RUN=False.

    Reads ``LCOGT_API_TOKEN`` from settings at call time (never during dry-run).
    """
    token = (config_mod.settings.lcogt_api_token or "").strip()
    if not token:
        raise RuntimeError("LCOGT_API_TOKEN is required when LCOGT_DRY_RUN=False")
    try:
        import urllib.error
        import urllib.request
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("urllib unavailable for LCO submit") from exc

    body = {k: v for k, v in request.items() if k not in {"breakout", "simulated"}}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        LCO_API_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"status": resp.status}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LCO submit failed HTTP {exc.code}: {detail}") from exc


def build_and_maybe_submit(
    candidate: CandidateScore,
    *,
    alert_id: str,
    run_dir: Path,
    proposal: str | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Build RequestGroup, write dry-run JSON, submit only when dry_run is False."""
    if dry_run is None:
        dry_run = bool(config_mod.settings.lcogt_dry_run)
    request = build_request_group(
        candidate,
        proposal=proposal,
        dry_run=dry_run,
        alert_id=alert_id,
    )
    path = write_request_group(request, alert_id=alert_id, run_dir=run_dir)
    result: dict[str, Any] = {
        "request_group": request,
        "path": str(path),
        "dry_run": bool(dry_run),
        "submitted": False,
        "simulated": bool(candidate.simulated),
    }
    if dry_run:
        logger.info("lcogt dry_run=True; not submitting alert_id=%s", alert_id)
        return result

    # Token is read only on the live submit path.
    submitted = submit_request_group(request)
    result["submitted"] = True
    result["submit_response"] = submitted
    return result
