"""POST /voice/session: ephemeral token for the browser.

XAI_API_KEY never reaches the browser; the backend mints a short-lived
client secret via POST https://api.x.ai/v1/realtime/client_secrets
(docs.x.ai ephemeral tokens) with ``expires_after.seconds = 300``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend import config as config_mod

logger = logging.getLogger("breakout.voice.realtime_session")

CLIENT_SECRETS_URL = "https://api.x.ai/v1/realtime/client_secrets"


def mint_client_secret(*, expires_after_seconds: int = 300) -> dict[str, Any]:
    """Mint an ephemeral realtime client secret for judge Q&A.

    Requires ``XAI_API_KEY``. Returns ``token`` (xAI ``value``) and
    ``model`` (``XAI_VOICE_MODEL``) for the browser. Never includes the API key.
    """
    settings = config_mod.settings
    api_key = (settings.xai_api_key or "").strip()
    if not api_key:
        raise RuntimeError("XAI_API_KEY is required to mint a realtime client secret")

    # Body matches docs.x.ai ephemeral-tokens Page: expires_after.seconds only
    # (no session / anchor fields).
    body = {"expires_after": {"seconds": int(expires_after_seconds)}}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(CLIENT_SECRETS_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, dict):
        raise RuntimeError("Unexpected client_secrets response (not a JSON object)")

    token = data.get("value")
    if not isinstance(token, str) or not token.strip():
        # Stop if the endpoint shape differs from docs.x.ai / the Page.
        raise RuntimeError(
            "client_secrets response missing string 'value' field; "
            f"keys={sorted(data.keys())}. Re-check docs.x.ai ephemeral tokens."
        )

    expires_at = data.get("expires_at")
    model = settings.xai_voice_model or "grok-voice-latest"
    # Browser session.update voice — from XAI_TTS_VOICE (.env), never the API key.
    voice = settings.xai_tts_voice or "eve"

    # Return only what the browser needs — never the API key or raw env secrets.
    out: dict[str, Any] = {
        "token": token,
        "model": model,
        "voice": voice,
        "expires_at": expires_at,
        "expires_after_seconds": int(expires_after_seconds),
    }
    # Belt-and-suspenders: ensure key material never leaks into the body.
    serialized = str(out)
    if api_key and api_key in serialized:
        raise RuntimeError("Refusing to return a body that contains XAI_API_KEY")
    logger.info("realtime client_secret minted model=%s expires_at=%s", model, expires_at)
    return out
