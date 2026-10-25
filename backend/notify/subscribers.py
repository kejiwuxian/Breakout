"""Access + refresh token registry for community WebSocket subscribe.

Stored under ``data/subscribers/registry.json`` (gitignored runtime file).

Two-token auth (OAuth-style):
  - **access_token** — short-lived; required to open/extend ``/ws/subscribe``
  - **refresh_token** — longer-lived; exchanged via ``POST /subscribe/refresh``
    for a new access token (client may push the new access token on a live WS)

Tokens are hashed at rest; plaintext is returned only at issue/refresh time.
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

ACCESS_TTL = timedelta(minutes=5)
REFRESH_TTL = timedelta(days=7)

RATE_LIMIT_WINDOW_SEC = 3600
RATE_LIMIT_MAX_PER_KEY = 10

_rate_hits: dict[str, list[float]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    email = row.get("email")
    return {
        "id": row.get("id"),
        "label": row.get("label"),
        "created_utc": row.get("created_utc"),
        "status": row.get("status"),
        "has_email": bool(email),
        "email_masked": _mask_email(str(email)) if email else None,
        "access_expires_utc": row.get("access_expires_utc"),
        "refresh_expires_utc": row.get("refresh_expires_utc"),
    }


def list_subscribers(*, public: bool = True, active_only: bool = True) -> list[dict[str, Any]]:
    """Return registry rows. Public view masks email and omits token hashes."""
    rows = _load()
    if active_only:
        rows = [r for r in rows if r.get("status") == "active"]
    if not public:
        return rows
    return [_public_row(row) for row in rows]


def _issue_pair(row: dict[str, Any], *, now: datetime | None = None) -> dict[str, str]:
    """Write new access + refresh hashes/expiries onto ``row``; return plaintext."""
    now = now or _utcnow()
    access_token = _new_token()
    refresh_token = _new_token()
    access_exp = now + ACCESS_TTL
    refresh_exp = now + REFRESH_TTL
    row["access_token_hash"] = _hash_token(access_token)
    row["refresh_token_hash"] = _hash_token(refresh_token)
    row["access_expires_utc"] = _iso(access_exp)
    row["refresh_expires_utc"] = _iso(refresh_exp)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_expires_utc": row["access_expires_utc"],
        "refresh_expires_utc": row["refresh_expires_utc"],
    }


def issue_tokens(
    *,
    email: str | None = None,
    label: str | None = None,
    client_ip: str | None = None,
) -> dict[str, Any]:
    """Create an active subscriber and return access + refresh tokens."""
    em = validate_email(email) if email else None
    lab = (label or "").strip() or None
    check_rate_limit(
        f"email:{em}" if em else "",
        f"ip:{client_ip or 'unknown'}",
    )

    now = _utcnow()
    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "email": em,
        "label": lab,
        "status": "active",
        "created_utc": _iso(now),
        "access_token_hash": None,
        "refresh_token_hash": None,
        "access_expires_utc": None,
        "refresh_expires_utc": None,
    }
    tokens = _issue_pair(row, now=now)
    rows = _load()
    rows.append(row)
    _save(rows)

    return {
        "status": "active",
        "subscriber": _public_row(row),
        **tokens,
        "access_ttl_sec": int(ACCESS_TTL.total_seconds()),
        "refresh_ttl_sec": int(REFRESH_TTL.total_seconds()),
        "ws": "/ws/subscribe",
        "note": (
            "Connect WebSocket /ws/subscribe with access_token. "
            "Refresh via POST /subscribe/refresh; send the new access_token "
            "on the live socket to extend before expiry auto-closes the wire."
        ),
    }


def refresh_access_token(*, refresh_token: str) -> dict[str, Any]:
    """Exchange a valid refresh_token for a new access_token (refresh rotated)."""
    text = (refresh_token or "").strip()
    if not text:
        raise ValueError("refresh_token required")

    digest = _hash_token(text)
    rows = _load()
    now = _utcnow()
    matched: dict[str, Any] | None = None
    matched_idx = -1
    for idx, row in enumerate(rows):
        if row.get("status") != "active":
            continue
        if row.get("refresh_token_hash") == digest:
            matched = row
            matched_idx = idx
            break

    if matched is None:
        raise ValueError("invalid refresh token")

    refresh_exp = _parse_iso(matched.get("refresh_expires_utc"))
    if refresh_exp is not None and refresh_exp <= now:
        raise ValueError("refresh token expired")

    tokens = _issue_pair(matched, now=now)
    rows[matched_idx] = matched
    _save(rows)

    return {
        "status": "active",
        "subscriber": _public_row(matched),
        **tokens,
        "access_ttl_sec": int(ACCESS_TTL.total_seconds()),
        "refresh_ttl_sec": int(REFRESH_TTL.total_seconds()),
    }


def verify_access_token(token: str) -> dict[str, Any] | None:
    """Return the active subscriber row if ``token`` is a non-expired access token."""
    text = (token or "").strip()
    if not text:
        return None
    digest = _hash_token(text)
    now = _utcnow()
    for row in _load():
        if row.get("status") != "active":
            continue
        if row.get("access_token_hash") != digest:
            continue
        exp = _parse_iso(row.get("access_expires_utc"))
        if exp is not None and exp <= now:
            return None
        return row
    return None


def access_expires_at(row: dict[str, Any]) -> datetime | None:
    """Parse access_expires_utc from a registry row."""
    return _parse_iso(row.get("access_expires_utc") if isinstance(row, dict) else None)


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
