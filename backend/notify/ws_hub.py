"""WebSocket hub for community alert subscribe (access-token gated).

Clients connect to ``/ws/subscribe`` with a valid access_token. The wire
auto-closes when that access token expires unless the client sends a newer
access_token on the live connection (after ``POST /subscribe/refresh``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from backend.notify.subscribers import access_expires_at, verify_access_token

logger = logging.getLogger("breakout.notify.ws")

CLOSE_ACCESS_EXPIRED = 4001
CLOSE_ACCESS_INVALID = 4003


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@dataclass
class SubscribeSession:
    ws: WebSocket
    subscriber_id: str
    access_expires_utc: datetime
    close_task: asyncio.Task[None] | None = field(default=None, repr=False)


class SubscribeHub:
    """Fan-out community_alert packages to authenticated WS subscribers."""

    def __init__(self) -> None:
        self._sessions: dict[WebSocket, SubscribeSession] = {}
        self._lock = asyncio.Lock()

    @property
    def n_connected(self) -> int:
        return len(self._sessions)

    async def register(
        self,
        ws: WebSocket,
        *,
        subscriber_id: str,
        access_expires_utc: datetime,
    ) -> SubscribeSession:
        """Track an accepted socket and schedule auto-close at access expiry."""
        session = SubscribeSession(
            ws=ws,
            subscriber_id=str(subscriber_id),
            access_expires_utc=access_expires_utc,
        )
        async with self._lock:
            old = self._sessions.get(ws)
            if old and old.close_task and not old.close_task.done():
                old.close_task.cancel()
            self._sessions[ws] = session
        session.close_task = asyncio.create_task(
            self._expire_watch(ws, access_expires_utc),
            name=f"subscribe-expire-{subscriber_id[:8]}",
        )
        return session

    async def extend_access(
        self,
        ws: WebSocket,
        *,
        access_token: str,
    ) -> dict[str, Any]:
        """Validate a new access_token on a live socket and reschedule close."""
        row = verify_access_token(access_token)
        if row is None:
            raise ValueError("invalid or expired access token")
        exp = access_expires_at(row)
        if exp is None:
            raise ValueError("access token missing expiry")

        async with self._lock:
            session = self._sessions.get(ws)
            if session is None:
                raise ValueError("socket not registered")
            if str(row.get("id")) != str(session.subscriber_id):
                raise ValueError("access token subscriber mismatch")
            if session.close_task and not session.close_task.done():
                session.close_task.cancel()
            session.access_expires_utc = exp
            session.close_task = asyncio.create_task(
                self._expire_watch(ws, exp),
                name=f"subscribe-expire-{session.subscriber_id[:8]}",
            )

        now = _utcnow()
        expires_in = max(0, int((exp - now).total_seconds()))
        return {
            "type": "access_extended",
            "subscriber_id": session.subscriber_id,
            "access_expires_utc": exp.isoformat().replace("+00:00", "Z"),
            "expires_in_sec": expires_in,
        }

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            session = self._sessions.pop(ws, None)
        if session and session.close_task and not session.close_task.done():
            session.close_task.cancel()

    async def broadcast_alert(self, package: dict[str, Any]) -> int:
        """Send a community_alert event to every connected subscriber."""
        event = {
            "type": "community_alert",
            "payload": package,
            "simulated": bool(package.get("simulated")),
        }
        data = json.dumps(event, ensure_ascii=False)
        async with self._lock:
            sessions = list(self._sessions.values())
        sent = 0
        dead: list[WebSocket] = []
        for session in sessions:
            try:
                if session.ws.client_state != WebSocketState.CONNECTED:
                    dead.append(session.ws)
                    continue
                await session.ws.send_text(data)
                sent += 1
            except Exception:
                logger.exception(
                    "subscribe_ws_send_failed subscriber_id=%s",
                    session.subscriber_id,
                )
                dead.append(session.ws)
        for ws in dead:
            await self.disconnect(ws)
        return sent

    async def _expire_watch(self, ws: WebSocket, expires_at: datetime) -> None:
        """Sleep until access expiry, then close the wire."""
        try:
            now = _utcnow()
            delay = (expires_at - now).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            async with self._lock:
                session = self._sessions.get(ws)
                if session is None:
                    return
                if session.access_expires_utc > _utcnow():
                    return
            try:
                await ws.close(code=CLOSE_ACCESS_EXPIRED, reason="access_token_expired")
            except Exception:
                pass
            await self.disconnect(ws)
            logger.info("subscribe_ws_closed_access_expired")
        except asyncio.CancelledError:
            return


subscribe_hub = SubscribeHub()


def schedule_alert_broadcast(package: dict[str, Any]) -> None:
    """Sync-safe: enqueue WS fan-out onto the running event loop if any."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(subscribe_hub.broadcast_alert(package))
