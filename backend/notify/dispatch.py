"""Fan-out community alerts to confirmed email subscribers (no webhooks)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend import config as config_mod
from backend.config import ROOT
from backend.notify.payload import build_community_alert
from backend.notify.subscribers import list_subscribers
from backend.schemas import Alert, CandidateScore, SkyMap

logger = logging.getLogger("breakout.notify")

FEED_PATH = ROOT / "data" / "subscribers" / "alert_feed.jsonl"


def _append_feed(package: dict[str, Any]) -> None:
    FEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEED_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(package, ensure_ascii=False) + "\n")


def _email_stub(email: str, package: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    """Email delivery: dry-run unless SMTP env is configured (Phase 1 default dry-run)."""
    smtp_host = (getattr(config_mod.settings, "smtp_host", "") or "").strip()
    if dry_run or not smtp_host:
        logger.info(
            "notify_email_dry_run to=%s alert_id=%s n_cand=%s",
            email,
            package.get("alert_id"),
            len(package.get("candidates") or []),
        )
        return {"ok": True, "dry_run": True, "channel": "email"}
    # Live SMTP intentionally minimal — only when operator sets SMTP_HOST.
    return {
        "ok": False,
        "dry_run": False,
        "channel": "email",
        "error": "SMTP live send not enabled in Phase 1 MVP",
    }


def latest_feed_packages(*, limit: int = 20) -> list[dict[str, Any]]:
    """Read recent packages from the local JSONL feed (newest last → reverse)."""
    if not FEED_PATH.is_file():
        return []
    lines = FEED_PATH.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, limit) :]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return list(reversed(out))


def dispatch_ranked_alert(
    alert: Alert,
    skymap: SkyMap,
    candidates: list[CandidateScore],
    *,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    """Build package, append feed, email only *active* (confirmed) subscribers."""
    package = build_community_alert(alert, skymap, candidates)
    _append_feed(package)

    dry_run = bool(getattr(config_mod.settings, "notify_dry_run", True))
    deliveries: list[dict[str, Any]] = []
    # Only confirmed subscribers receive email; webhook path removed.
    for sub in list_subscribers(public=False, active_only=True):
        sid = str(sub.get("id") or "")
        entry: dict[str, Any] = {"subscriber_id": sid, "label": sub.get("label")}
        em = sub.get("email")
        if isinstance(em, str) and em:
            entry["email"] = _email_stub(em, package, dry_run=dry_run)
        deliveries.append(entry)

    summary = {
        "alert_id": alert.alert_id,
        "simulated": bool(package.get("simulated")),
        "n_candidates": len(package.get("candidates") or []),
        "n_subscribers": len(deliveries),
        "dry_run": dry_run,
        "deliveries": deliveries,
        "schema": package.get("schema"),
        "channels": ["email"],
    }

    if run_dir is not None:
        alert_dir = Path(run_dir) / alert.alert_id
        alert_dir.mkdir(parents=True, exist_ok=True)
        (alert_dir / "community_alert.json").write_text(
            json.dumps(package, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (alert_dir / "notify_dispatch.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    logger.info(
        "notify_dispatch alert_id=%s subscribers=%s dry_run=%s simulated=%s",
        alert.alert_id,
        len(deliveries),
        dry_run,
        package.get("simulated"),
    )
    return {"package": package, "dispatch": summary}
