"""BREAKOUT FastAPI entrypoint: REST + WebSocket event stream to the UI."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.config import settings
from backend.schemas import WsHelloEvent

app = FastAPI(
    title="BREAKOUT",
    description="Neutrino-first supernova interceptor (Phase 1 SpaceXAI MVP).",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe for CI and mvp_gate.sh."""
    return {
        "status": "ok",
        "service": "breakout",
        "use_cached_stream": settings.use_cached_stream,
        "scenario": settings.scenario,
        "voice_mode": settings.voice_mode,
        "lcogt_dry_run": settings.lcogt_dry_run,
    }


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    """Stream pipeline and voice events to the dashboard.

    Scaffold sends a hello event only; later prompts push alert / skymap /
    candidates / voice audio events.
    """
    await websocket.accept()
    hello = WsHelloEvent(
        use_cached_stream=settings.use_cached_stream,
        scenario=settings.scenario,
        simulated=False,
    )
    await websocket.send_text(hello.model_dump_json())
    try:
        while True:
            # Keep the socket open; clients may send pings or control messages.
            message = await websocket.receive_text()
            if message.strip().lower() in {"ping", '{"type":"ping"}'}:
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        return
