"""Fan-out community alerts to registered webhooks (email is dry-run unless SMTP set)."""

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


def _post_webhook(url: str, package: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        logger.info("notify_webhook_dry_run url=%s alert_id=%s", url, package.get("alert_id"))
        return {"ok": True, "dry_run": True, "status_code": None}
    try:
        import httpx
    except ImportError:
        return {"ok": False, "dry_run": False, "error": "httpx missing"}
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.post(
                url,
                json=package,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "BREAKOUT-community-alert/1.0",
                    "X-Breakout-Schema": str(package.get("schema") or ""),
                },
            )
        return {
            "ok": 200 <= resp.status_code < 300,
            "dry_run": False,
            "status_code": resp.status_code,
        }
    except Exception as exc:  # noqa: BLE001 — record delivery failure, do not crash pipeline
        logger.exception("notify_webhook_failed url=%s", url)
        return {"ok": False, "dry_run": False, "error": str(exc)}


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
        "error": "SMTP live send not enabled in Phase 1 MVP (set dry-run webhook instead)",
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
    """Build package, append feed, POST webhooks / stub emails for every subscriber."""
    package = build_community_alert(alert, skymap, candidates)
    _append_feed(package)

    dry_run = bool(getattr(config_mod.settings, "notify_dry_run", True))
    deliveries: list[dict[str, Any]] = []
    for sub in list_subscribers(public=False):
        sid = str(sub.get("id") or "")
        entry: dict[str, Any] = {"subscriber_id": sid, "label": sub.get("label")}
        wh = sub.get("webhook_url")
        if isinstance(wh, str) and wh:
            entry["webhook"] = _post_webhook(wh, package, dry_run=dry_run)
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
