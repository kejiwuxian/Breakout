"""Community notify: two-token email opt-in for ranked-candidate alerts.

Phase 1 MVP path so scientists and enthusiasts can confirm an email, then
receive ranked progenitors before large facilities are on board.
No webhook delivery. Never invents coordinates or bibcodes; simulated stays labeled.
"""

from backend.notify.dispatch import dispatch_ranked_alert
from backend.notify.payload import build_community_alert
from backend.notify.subscribers import (
    confirm_subscribe,
    list_subscribers,
    remove_subscriber,
    request_subscribe,
    verify_access_token,
)

__all__ = [
    "build_community_alert",
    "confirm_subscribe",
    "dispatch_ranked_alert",
    "list_subscribers",
    "remove_subscriber",
    "request_subscribe",
    "verify_access_token",
]
