"""Action layer: LCOGT dry-run, ToO drafts, GCN Circular draft."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.actions.gcn_circular import draft_circular
from backend.actions.lcogt import build_and_maybe_submit
from backend.actions.too_drafts import draft_hst_too, draft_jwst_too
from backend import config as config_mod
from backend.schemas import Alert, CandidateScore, SkyMap

logger = logging.getLogger("breakout.actions")


def build_actions_payload(
    alert: Alert,
    skymap: SkyMap,
    candidates: list[CandidateScore],
    *,
    run_dir: Path,
) -> dict[str, Any]:
    """Run LCOGT / ToO / GCN builders for the ranked candidates.

    Dry-run by default (``LCOGT_DRY_RUN``). Never invents numbers or bibcodes.
    """
    top = candidates[0] if candidates else None
    simulated = bool(alert.simulated) or bool(skymap.simulated)
    if top is not None:
        simulated = simulated or bool(top.simulated)

    payload: dict[str, Any] = {
        "alert_id": alert.alert_id,
        "lcogt_dry_run": bool(config_mod.settings.lcogt_dry_run),
        "top_star_id": top.star_id if top is not None else None,
        "lcogt": None,
        "too_hst_markdown": None,
        "too_jwst_markdown": None,
        "gcn_circular_markdown": None,
        "simulated": simulated,
        "note": "Drafts only — human approval required before any LCO/HST/JWST/GCN submit.",
    }

    if top is None:
        payload["note"] = "No candidates; action drafts skipped."
        return payload

    lcogt = build_and_maybe_submit(
        top,
        alert_id=alert.alert_id,
        run_dir=run_dir,
        dry_run=bool(config_mod.settings.lcogt_dry_run),
    )
    hst = draft_hst_too(top, skymap)
    jwst = draft_jwst_too(top, skymap)
    gcn = draft_circular(alert, skymap, candidates)

    # Persist Markdown drafts next to the LCO JSON for the run directory.
    alert_dir = Path(run_dir) / alert.alert_id
    alert_dir.mkdir(parents=True, exist_ok=True)
    (alert_dir / "too_hst.md").write_text(hst, encoding="utf-8")
    (alert_dir / "too_jwst.md").write_text(jwst, encoding="utf-8")
    (alert_dir / "gcn_circular.md").write_text(gcn, encoding="utf-8")

    payload["lcogt"] = {
        "path": lcogt.get("path"),
        "dry_run": lcogt.get("dry_run"),
        "submitted": lcogt.get("submitted"),
        "request_group": lcogt.get("request_group"),
        "simulated": lcogt.get("simulated"),
    }
    payload["too_hst_markdown"] = hst
    payload["too_jwst_markdown"] = jwst
    payload["gcn_circular_markdown"] = gcn
    logger.info(
        "actions_built alert_id=%s top=%s dry_run=%s",
        alert.alert_id,
        top.star_id,
        config_mod.settings.lcogt_dry_run,
    )
    return payload
