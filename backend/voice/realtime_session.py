"""POST /voice/session: ephemeral token for the browser.

XAI_API_KEY never reaches the browser; the backend mints a short-lived
client secret via the xAI realtime client_secrets API.
"""

from __future__ import annotations

from typing import Any


def mint_client_secret(*, expires_after_seconds: int = 300) -> dict[str, Any]:
    """Mint an ephemeral realtime client secret for judge Q&A.

    Requires XAI_API_KEY. Used only when VOICE_MODE=live.
    """
    raise NotImplementedError("mint_client_secret is filled in a later prompt.")
