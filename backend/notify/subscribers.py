"""Local subscriber registry with two-token email confirmation (no webhooks).

Stored under ``data/subscribers/registry.json`` (gitignored runtime file).
Flow: request (email) → pending + short-lived tokens → confirm → active + access_token.
Tokens are hashed at rest; plaintext is returned only in dry-run / no-SMTP responses.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.config import ROOT

REGISTRY_DIR = ROOT / "data" / "subscribers"
REGISTRY_PATH = REGISTRY_DIR / "registry.json"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PENDING_TTL = timedelta(hours=1)
RATE_LIMIT_WINDOW_SEC = 3600
RATE_LIMIT_MAX_PER_KEY = 5

# In-memory rate windows: key → list of unix timestamps.
_rate_hits: dict[str, list[float]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utcnow_iso() -> str:
    return _utcnow().isoformat().replace("+00:00", "Z")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _mask_email(email: str) -> str:
    text = (email or "").strip()
    if "@" not in text:
        return "***"
    local, _, domain = text.partition("@")
    if not local:
        return f"***@{domain}"
    if len(local) == 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "***"
    return f"{masked_local}@{domain}"


def validate_email(email: str) -> str:
    text = (email or "").strip().lower()
    if not _EMAIL_RE.match(text):
        raise ValueError("invalid email")
    return text


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


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def purge_expired_pending(*, now: datetime | None = None) -> int:
    """Drop pending rows past expires_utc. Returns count removed."""
    now = now or _utcnow()
    rows = _load()
    kept: list[dict[str, Any]] = []
    removed = 0
    for row in rows:
        if row.get("status") == "pending":
            exp = _parse_iso(row.get("expires_utc"))
            if exp is not None and exp <= now:
                removed += 1
                continue
        kept.append(row)
    if removed:
        _save(kept)
    return removed


def check_rate_limit(*keys: str) -> None:
    """Raise ValueError if any key exceeds the Phase-1 window budget."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SEC
    for key in keys:
        if not key:
            continue
        hits = [t for t in _rate_hits.get(key, []) if t >= cutoff]
        if len(hits) >= RATE_LIMIT_MAX_PER_KEY:
            raise ValueError("rate limit exceeded — try again later")
        hits.append(now)
        _rate_hits[key] = hits


def clear_rate_limits() -> None:
    """Test helper: reset in-memory rate windows."""
    _rate_hits.clear()


def list_subscribers(*, public: bool = True, active_only: bool = True) -> list[dict[str, Any]]:
    """Return registry rows. Public view masks email and omits token hashes."""
    purge_expired_pending()
    rows = _load()
    if active_only:
        rows = [r for r in rows if r.get("status") == "active"]
    if not public:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        email = row.get("email")
        item = {
            "id": row.get("id"),
            "label": row.get("label"),
            "created_utc": row.get("created_utc"),
            "confirmed_utc": row.get("confirmed_utc"),
            "status": row.get("status"),
            "has_email": bool(email),
            "email_masked": _mask_email(str(email)) if email else None,
        }
        out.append(item)
    return out


def request_subscribe(
    *,
    email: str,
    label: str | None = None,
    client_ip: str | None = None,
    dry_run: bool = True,
    smtp_configured: bool = False,
) -> dict[str, Any]:
    """Create a pending subscriber and issue request + confirm tokens.

    Does not activate push delivery. Plaintext tokens appear in the response
    only when ``dry_run`` or SMTP is not configured (demo / local path).
    """
    em = validate_email(email)
    check_rate_limit(f"email:{em}", f"ip:{client_ip or 'unknown'}")
    purge_expired_pending()

    request_token = _new_token()
    confirm_token = _new_token()
    now = _utcnow()
    expires = now + PENDING_TTL
    request_id = str(uuid.uuid4())

    row = {
        "id": request_id,
        "email": em,
        "label": (label or "").strip() or None,
        "status": "pending",
        "created_utc": now.isoformat().replace("+00:00", "Z"),
        "expires_utc": expires.isoformat().replace("+00:00", "Z"),
        "request_token_hash": _hash_token(request_token),
        "confirm_token_hash": _hash_token(confirm_token),
        "access_token_hash": None,
        "confirmed_utc": None,
    }
    rows = _load()
    # Replace any existing pending row for the same email.
    rows = [
        r
        for r in rows
        if not (r.get("status") == "pending" and str(r.get("email") or "").lower() == em)
    ]
    rows.append(row)
    _save(rows)

    out: dict[str, Any] = {
        "pending": True,
        "request_id": request_id,
        "expires_utc": row["expires_utc"],
        "email_masked": _mask_email(em),
        "label": row["label"],
    }
    # Never invent production email delivery — expose tokens only for dry-run / no SMTP.
    if dry_run or not smtp_configured:
        out["dry_run"] = {
            "label": "Simulated/dry-run — tokens returned in API (no email sent)",
            "request_token": request_token,
            "confirm_token": confirm_token,
            "confirm_hint": (
                "POST /subscribe/confirm with both tokens to activate. "
                "With SMTP configured and NOTIFY_DRY_RUN=False these would be emailed."
            ),
        }
    return out


def confirm_subscribe(
    *,
    request_token: str,
    confirm_token: str,
) -> dict[str, Any]:
    """Activate a pending subscriber when both tokens match and are unexpired."""
    rt = (request_token or "").strip()
    ct = (confirm_token or "").strip()
    if not rt or not ct:
        raise ValueError("request_token and confirm_token required")

    purge_expired_pending()
    rt_hash = _hash_token(rt)
    ct_hash = _hash_token(ct)
    rows = _load()
    now = _utcnow()
    matched: dict[str, Any] | None = None
    matched_idx = -1
    for idx, row in enumerate(rows):
        if row.get("status") != "pending":
            continue
        if row.get("request_token_hash") == rt_hash and row.get("confirm_token_hash") == ct_hash:
            matched = row
            matched_idx = idx
            break

    if matched is None:
        raise ValueError("invalid or already-used tokens")

    exp = _parse_iso(matched.get("expires_utc"))
    if exp is not None and exp <= now:
        # Drop expired row
        del rows[matched_idx]
        _save(rows)
        raise ValueError("pending request expired")

    access_token = _new_token()
    matched["status"] = "active"
    matched["confirmed_utc"] = now.isoformat().replace("+00:00", "Z")
    matched["access_token_hash"] = _hash_token(access_token)
    # One-time use: clear confirmation hashes so tokens cannot be reused.
    matched["request_token_hash"] = None
    matched["confirm_token_hash"] = None
    matched["expires_utc"] = None
    rows[matched_idx] = matched
    _save(rows)

    return {
        "status": "active",
        "subscriber": {
            "id": matched["id"],
            "label": matched.get("label"),
            "email_masked": _mask_email(str(matched.get("email") or "")),
            "confirmed_utc": matched["confirmed_utc"],
            "status": "active",
        },
        "access_token": access_token,
    }


def verify_access_token(token: str) -> dict[str, Any] | None:
    """Return the active subscriber row if ``token`` matches an access_token_hash."""
    text = (token or "").strip()
    if not text:
        return None
    digest = _hash_token(text)
    for row in _load():
        if row.get("status") == "active" and row.get("access_token_hash") == digest:
            return row
    return None


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
