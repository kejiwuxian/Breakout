"""Community notify: access + refresh tokens over WebSocket subscribe.

Phase 1 path so scientists and enthusiasts receive ranked progenitors on a
live ``/ws/subscribe`` connection. Access tokens expire; clients refresh and
push a new access token on the wire to extend, otherwise the socket closes.
Never invents coordinates or bibcodes; simulated stays labeled.
"""

from backend.notify.dispatch import dispatch_ranked_alert
from backend.notify.payload import build_community_alert
from backend.notify.subscribers import (
    issue_tokens,
    list_subscribers,
    refresh_access_token,
    remove_subscriber,
    verify_access_token,
)

__all__ = [
    "build_community_alert",
    "dispatch_ranked_alert",
    "issue_tokens",
    "list_subscribers",
    "refresh_access_token",
    "remove_subscriber",
    "verify_access_token",
]
