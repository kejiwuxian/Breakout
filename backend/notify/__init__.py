"""Community notify: webhook (and optional email) fan-out of ranked candidates.

Phase 1 MVP path so scientists and enthusiasts can point instruments at
BREAKOUT-ranked progenitors before large facilities are on board.
Never invents coordinates or bibcodes; every simulated field stays labeled.
"""

from backend.notify.dispatch import dispatch_ranked_alert
from backend.notify.payload import build_community_alert
from backend.notify.subscribers import add_subscriber, list_subscribers, remove_subscriber

__all__ = [
    "add_subscriber",
    "build_community_alert",
    "dispatch_ranked_alert",
    "list_subscribers",
    "remove_subscriber",
]
