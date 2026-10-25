"""Local subscriber registry (webhooks + optional contact email).

Stored under ``data/subscribers/registry.json`` (gitignored runtime file).
No cloud account required — anyone can POST ``/subscribe`` with a webhook URL
and receive ranked-candidate JSON when BREAKOUT fires.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.config import ROOT

REGISTRY_DIR = ROOT / "data" / "subscribers"
REGISTRY_PATH = REGISTRY_DIR / "registry.json"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load() -> list[dict[str, Any]]:
    if not REGISTRY_PATH.is_file():
        return []
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("subscriber registry must be a JSON list")
    return [r for r in raw if isinstance(r, dict)]


def _save(rows: list[dict[str, Any]]) -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def validate_webhook_url(url: str) -> str:
    """Accept http(s) webhooks only; block obvious SSRF localhost in production later."""
    text = (url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("webhook_url must be http or https")
    if not parsed.netloc:
        raise ValueError("webhook_url missing host")
    return text


def validate_email(email: str) -> str:
    text = (email or "").strip()
    if not _EMAIL_RE.match(text):
        raise ValueError("invalid email")
    return text


def list_subscribers(*, public: bool = True) -> list[dict[str, Any]]:
    """Return registry rows. When ``public``, redact full webhook paths slightly."""
    rows = _load()
    if not public:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "id": row.get("id"),
            "label": row.get("label"),
            "created_utc": row.get("created_utc"),
            "has_webhook": bool(row.get("webhook_url")),
            "has_email": bool(row.get("email")),
        }
        wh = row.get("webhook_url")
        if isinstance(wh, str) and wh:
            host = urlparse(wh).netloc
            item["webhook_host"] = host
        out.append(item)
    return out


def add_subscriber(
    *,
    webhook_url: str | None = None,
    email: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Register a community subscriber. Requires webhook and/or email."""
    wh = validate_webhook_url(webhook_url) if webhook_url else None
    em = validate_email(email) if email else None
    if not wh and not em:
        raise ValueError("provide webhook_url and/or email")
    row = {
        "id": str(uuid.uuid4()),
        "webhook_url": wh,
        "email": em,
        "label": (label or "").strip() or None,
        "created_utc": _utcnow(),
    }
    rows = _load()
    rows.append(row)
    _save(rows)
    return {
        "id": row["id"],
        "label": row["label"],
        "created_utc": row["created_utc"],
        "has_webhook": bool(wh),
        "has_email": bool(em),
        "webhook_host": urlparse(wh).netloc if wh else None,
    }


def remove_subscriber(subscriber_id: str) -> bool:
    """Delete by id. Returns True if a row was removed."""
    rows = _load()
    kept = [r for r in rows if str(r.get("id")) != str(subscriber_id)]
    if len(kept) == len(rows):
        return False
    _save(kept)
    return True


def clear_subscribers() -> None:
    """Test helper: empty the registry."""
    _save([])
