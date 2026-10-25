"""BREAKOUT FastAPI entrypoint: REST + WebSocket event stream to the UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.config import ROOT, settings
from backend.ingest.cache import replay_scenario
from backend.notify.dispatch import latest_feed_packages
from backend.notify.subscribers import (
    access_expires_at,
    issue_tokens,
    list_subscribers,
    refresh_access_token,
    remove_subscriber,
    verify_access_token,
)
from backend.notify.ws_hub import CLOSE_ACCESS_INVALID, subscribe_hub
from backend.pipeline import process_alert, reset_watchlist
from backend.schemas import WsHelloEvent
from backend.voice import announcer as voice_announcer
from backend.voice.tools import reset_run_state, update_run_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("breakout.app")


class EventHub:
    """Fan-out hub for /ws/events subscribers + internal listeners."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._listeners: list[Callable[[dict[str, Any]], Any]] = []
        self._lock = asyncio.Lock()

    def subscribe(self, listener: Callable[[dict[str, Any]], Any]) -> None:
        """Register an internal listener (e.g. Grok Voice announcer)."""
        self._listeners.append(listener)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        data = json.dumps(event)
        async with self._lock:
            clients = list(self._clients)
            listeners = list(self._listeners)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
        # Internal subscribers (voice). Live TTS is background; cached/off are awaited
        # so captions stay ordered with the pipeline event that triggered them.
        et = str(event.get("type") or "")
        mode = (settings.voice_mode or "off").lower()
        for listener in listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                    if (
                        et in voice_announcer.EVENT_LINE_KEYS
                        and mode == "live"
                    ):
                        asyncio.create_task(result)  # type: ignore[arg-type]
                    else:
                        await result  # type: ignore[misc]
            except Exception:
                logger.exception("event hub listener failed type=%s", event.get("type"))


hub = EventHub()
_run_lock = asyncio.Lock()
_run_task: asyncio.Task[None] | None = None
_out_root = ROOT / "data" / "run"


def _note_run_state(event: dict[str, Any]) -> None:
    """Keep judge Q&A tools pointed at the current run only."""
    et = event.get("type")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    simulated = bool(event.get("simulated", False))
    if et == "alert":
        update_run_state(alert=payload, simulated=simulated)
    elif et == "skymap":
        update_run_state(skymap=payload, simulated=simulated)
    elif et == "candidates":
        cands = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        update_run_state(
            alert_id=str(payload.get("alert_id") or "") or None,
            candidates=[c for c in cands if isinstance(c, dict)],
            simulated=simulated,
        )


def _build_actions_event(alert: Any, context: dict[str, Any]) -> dict[str, Any]:
    """Run LCOGT / ToO / GCN builders after candidates (drafts only)."""
    from backend.actions import build_actions_payload

    payload = build_actions_payload(
        context["alert"],
        context["skymap"],
        context["scores"],
        run_dir=_out_root,
    )
    simulated = bool(payload.get("simulated", alert.simulated))
    return {"type": "actions", "payload": payload, "simulated": simulated}


async def _emit_pipeline_events(alert: Any) -> None:
    """Process alert and push WS events; builders run after candidates."""
    events = await asyncio.to_thread(process_alert, alert, out_root=_out_root)
    for event in events:
        if event.get("type") == "_actions_context":
            # After candidates: build LCOGT / ToO / GCN drafts and push actions.
            actions_event = await asyncio.to_thread(
                _build_actions_event, alert, event["payload"]
            )
            await hub.broadcast(actions_event)
            continue
        _note_run_state(event)
        await hub.broadcast(event)


# Idle WS/hello posture until POST /scenario/{name}/start (or a live alert).
IDLE_SCENARIO = "live_waiting"
_active_scenario: str | None = None


def _hello_scenario() -> str:
    """Active scenario name, or live_waiting when idle / listening."""
    return _active_scenario or IDLE_SCENARIO


async def run_scenario(name: str, *, speed: float = 0.0) -> None:
    """Replay a cached scenario through the core loop (no live network)."""
    global _active_scenario
    logger.info("scenario_start name=%s speed=%s", name, speed)
    _active_scenario = name
    reset_watchlist()
    reset_run_state()
    voice_announcer.reset_sequence(name)
    async for alert in replay_scenario(name, speed=speed):
        logger.info(
            "alert_received id=%s kind=%s simulated=%s",
            alert.alert_id,
            alert.kind,
            alert.simulated,
        )
        await _emit_pipeline_events(alert)
    logger.info("scenario_done name=%s", name)
    await hub.broadcast(
        {
            "type": "scenario_done",
            "payload": {"scenario": name},
            "simulated": False,
        }
    )


async def _start_scenario_task(name: str, *, speed: float = 0.0) -> None:
    global _run_task
    async with _run_lock:
        if _run_task is not None and not _run_task.done():
            _run_task.cancel()
            try:
                await _run_task
            except (asyncio.CancelledError, Exception):
                pass
        _run_task = asyncio.create_task(run_scenario(name, speed=speed))


async def _start_live_listeners() -> None:
    """Spawn live ingest iterators when USE_CACHED_STREAM=False.

    Multiplexes every public realtime channel we can subscribe to:
    GCN Kafka (SNEWS2 coincidence, IceCube gold/bronze, pre-SN, classic
    SNEWS text) plus optional SCiMMA Hopskotch ``snews2.alert``. Each
    listener runs in a worker thread; localization uses DiffPointing /
    pointing inside the pipeline. Credentials come only from .env.
    """
    from backend.ingest import live_channels

    loop = asyncio.get_running_loop()

    def _pump(name: str, factory: Any) -> None:
        logger.info("live_listener_start %s", name)
        try:
            for alert in factory():
                fut = asyncio.run_coroutine_threadsafe(_emit_pipeline_events(alert), loop)
                fut.result()
        except Exception:
            logger.exception("live_listener_failed %s", name)

    asyncio.create_task(
        asyncio.to_thread(
            _pump, "gcn_all", lambda: live_channels.listen_gcn_live_alerts()
        )
    )
    asyncio.create_task(
        asyncio.to_thread(
            _pump, "hop_snews", lambda: live_channels.listen_hop_snews_alerts()
        )
    )


def _should_autostart_scenario() -> bool:
    """Opt-in only: default cold start never replays scenarios.

    Set ``BREAKOUT_AUTOSTART=1`` to auto-replay ``SCENARIO`` on startup.
    ``BREAKOUT_DISABLE_AUTOSTART=1`` always wins (tests / explicit off).
    """
    if os.environ.get("BREAKOUT_DISABLE_AUTOSTART") == "1":
        return False
    return os.environ.get("BREAKOUT_AUTOSTART") == "1"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Grok Voice: live TTS pushes via this callback (background); never blocks pipeline.
    async def _push_voice(event: dict[str, Any]) -> None:
        await hub.broadcast(event)

    voice_announcer.set_voice_pusher(_push_voice)
    # Also subscribe so any future hub.broadcast of pipeline events is covered.
    voice_announcer.attach_to_hub(hub)
    logger.info("voice announcer attached mode=%s", settings.voice_mode)

    if settings.use_cached_stream:
        logger.info(
            "startup USE_CACHED_STREAM=True idle=%s configured_scenario=%s",
            IDLE_SCENARIO,
            settings.scenario,
        )
        if _should_autostart_scenario():
            async def _autostart() -> None:
                await asyncio.sleep(0.05)
                await _start_scenario_task(settings.scenario, speed=0.0)

            logger.info("BREAKOUT_AUTOSTART=1 — replaying %s", settings.scenario)
            asyncio.create_task(_autostart())
        else:
            logger.info(
                "cached stream ready — waiting for POST /scenario/{name}/start "
                "(no auto-replay)"
            )
    else:
        logger.info("startup live listeners (subscribed / waiting for alerts)")
        await _start_live_listeners()
    yield
    global _run_task
    if _run_task is not None and not _run_task.done():
        _run_task.cancel()
    voice_announcer.set_voice_pusher(None)


app = FastAPI(
    title="BREAKOUT",
    description="Neutrino-first supernova interceptor (Phase 1 SpaceXAI MVP).",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe for CI and mvp_gate.sh."""
    return {
        "status": "ok",
        "service": "breakout",
        "use_cached_stream": settings.use_cached_stream,
        "scenario": _hello_scenario(),
        "configured_scenario": settings.scenario,
        "voice_mode": settings.voice_mode,
        "lcogt_dry_run": settings.lcogt_dry_run,
        "notify_dry_run": settings.notify_dry_run,
        "n_subscribers": len(list_subscribers(public=True, active_only=True)),
    }


class SubscribeIssueBody(BaseModel):
    """Issue access + refresh tokens for WebSocket community alerts."""

    email: str | None = Field(default=None, description="Optional contact email")
    label: str | None = Field(default=None, description="Optional human label")


class SubscribeRefreshBody(BaseModel):
    """Exchange refresh_token for a new access_token (and rotated refresh)."""

    refresh_token: str = Field(..., description="Refresh token from /subscribe")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@app.post("/subscribe")
def subscribe_issue(body: SubscribeIssueBody, request: Request) -> dict[str, Any]:
    """Issue access_token + refresh_token for /ws/subscribe."""
    try:
        result = issue_tokens(
            email=body.email,
            label=body.label,
            client_ip=_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        **result,
        "notify_dry_run": settings.notify_dry_run,
    }


@app.post("/subscribe/refresh")
def subscribe_refresh(body: SubscribeRefreshBody) -> dict[str, Any]:
    """Mint a new access_token from refresh_token; push it on live WS to extend."""
    try:
        result = refresh_access_token(refresh_token=body.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {
        **result,
        "notify_dry_run": settings.notify_dry_run,
        "next": "Send {type:access_token, access_token} on /ws/subscribe to extend",
    }


@app.get("/subscribe")
def subscribe_list() -> dict[str, Any]:
    """List active subscriber metadata (masked email; no secrets)."""
    return {
        "subscribers": list_subscribers(public=True, active_only=True),
        "notify_dry_run": settings.notify_dry_run,
        "feed": "/alerts/latest",
        "ws": "/ws/subscribe",
        "n_ws_connected": subscribe_hub.n_connected,
        "auth": "access_token + refresh_token over WebSocket",
    }


@app.delete("/subscribe/{subscriber_id}")
def subscribe_delete(subscriber_id: str) -> dict[str, Any]:
    """Remove a subscriber by id."""
    if not remove_subscriber(subscriber_id):
        raise HTTPException(status_code=404, detail="subscriber not found")
    return {"status": "removed", "id": subscriber_id}


@app.get("/alerts/latest")
def alerts_latest(
    limit: int = 10,
    token: str | None = Query(default=None, description="Optional access_token"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Recent community alert packages (ranked candidates + coords).

    Feed remains readable without a token for local demos. When ``token`` or
    ``Authorization: Bearer`` is supplied, it must match a non-expired access token.
    Live push uses ``/ws/subscribe``.
    """
    bearer: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    access = (token or bearer or "").strip()
    if access:
        if verify_access_token(access) is None:
            raise HTTPException(status_code=401, detail="invalid or expired access token")

    lim = max(1, min(int(limit), 50))
    packages = latest_feed_packages(limit=lim)
    return {
        "count": len(packages),
        "packages": packages,
        "ws": "/ws/subscribe",
        "note": (
            "BREAKOUT community feed for local/instrument follow-up. "
            "simulated=true fields are not real observations. "
            "Prefer /ws/subscribe with access_token for live push."
        ),
    }


@app.post("/scenario/{name}/start")
async def start_scenario(name: str, speed: float = 0.0) -> dict[str, Any]:
    """Demo button: replay ``data/cache/<name>`` through the core loop."""
    cache_dir = ROOT / "data" / "cache" / name
    if not cache_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown scenario {name!r}")
    alerts = cache_dir / "alerts.jsonl"
    if not alerts.is_file():
        raise HTTPException(status_code=404, detail=f"Missing {alerts}")
    await _start_scenario_task(name, speed=speed)
    return {"status": "started", "scenario": name, "speed": speed}


def _safe_alert_dir(alert_id: str) -> Path:
    """Resolve data/run/<alert_id> without path traversal.

    Alert ids may include ``*`` (e.g. sim-presn-*_alf_Ori from Scenario A).
    """
    import re

    if not re.fullmatch(r"[A-Za-z0-9._\-+:*]+", alert_id):
        raise HTTPException(status_code=400, detail="Invalid alert_id")
    path = (_out_root / alert_id).resolve()
    root = _out_root.resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=400, detail="Invalid alert_id")
    return path


@app.get("/api/skymap/{alert_id}/png")
def skymap_png(alert_id: str) -> FileResponse:
    """Serve the Mollweide PNG written by localize/fuse for the dashboard."""
    png = _safe_alert_dir(alert_id) / "skymap.png"
    if not png.is_file():
        raise HTTPException(status_code=404, detail=f"No skymap.png for {alert_id}")
    return FileResponse(
        png,
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/api/sky/base")
def sky_base_layers() -> dict[str, Any]:
    """Public SVG sky layers (curated SIMBAD stars + galactic plane) with no alert."""
    from backend.localize.region import public_sky_base

    return public_sky_base()


@app.get("/api/skymap/{alert_id}/region")
def skymap_region(alert_id: str) -> dict[str, Any]:
    """SVG sky layers: ellipse, HEALPix cells, public field stars, galactic plane.

    Regenerates ``region.json`` / ``skymap_focus.png`` when the fused FITS is
    newer so the UI always sees the latest localization.
    """
    from backend.localize.region import ensure_region_artifacts

    alert_dir = _safe_alert_dir(alert_id)
    if not (alert_dir / "skymap.fits").is_file():
        raise HTTPException(status_code=404, detail=f"No skymap.fits for {alert_id}")
    try:
        payload = ensure_region_artifacts(alert_dir, alert_id=alert_id)
    except Exception as exc:
        logger.exception("skymap_region_failed alert_id=%s", alert_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return payload


@app.get("/api/skymap/{alert_id}/focus.png")
def skymap_focus_png(alert_id: str) -> FileResponse:
    """Zoomed gnomonic PNG with red 90% outline (offline Aladin fallback)."""
    from backend.localize.region import ensure_region_artifacts

    alert_dir = _safe_alert_dir(alert_id)
    if not (alert_dir / "skymap.fits").is_file():
        raise HTTPException(status_code=404, detail=f"No skymap.fits for {alert_id}")
    try:
        ensure_region_artifacts(alert_dir, alert_id=alert_id)
    except Exception as exc:
        logger.exception("skymap_focus_failed alert_id=%s", alert_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    focus = alert_dir / "skymap_focus.png"
    if not focus.is_file():
        raise HTTPException(status_code=404, detail=f"No skymap_focus.png for {alert_id}")
    return FileResponse(
        focus,
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/api/literature/raw/{star_id:path}")
def literature_raw(star_id: str) -> dict[str, Any]:
    """Return offline Grok raw JSON for a star (reasoning + evidence).

    Never invents claims: serves ``data/index/raw/<slug>.json`` when present,
    otherwise materializes it from recorded ADS/arXiv fixtures or index.parquet.
    """
    from backend.literature.build_index import ensure_raw_for_star

    artifact = ensure_raw_for_star(star_id)
    if artifact is not None:
        return artifact

    return {
        "star_id": star_id,
        "reasoning": None,
        "literature": {
            "mass_loss": 0.0,
            "variability": 0.0,
            "evolved_stage": 0.0,
            "confidence": 0.0,
            "evidence": [],
        },
        "raw_missing": True,
        "note": "No offline literature artifact for this star yet.",
        "simulated": False,
    }


@app.get("/api/progenitors/inventory")
def progenitors_inventory(limit: int = 100) -> dict[str, Any]:
    """Offline SN-potential inventory summary (no secrets; no live Grok)."""
    from backend.progenitors.inventory import inventory_status, load_inventory_rows

    rows = load_inventory_rows()
    lim = max(1, min(int(limit), 500))
    preview = [
        {
            "star_id": p.star_id,
            "common_name": p.common_name,
            "class": p.class_,
            "ra_deg": p.ra_deg,
            "dec_deg": p.dec_deg,
            "distance_kpc": p.distance_kpc,
            "composition": p.composition,
            "sn_potential": p.sn_potential,
            "life_expectancy": p.life_expectancy.model_dump(mode="json"),
            "lit_confidence": p.lit.confidence,
            "last_reviewed_utc": p.last_reviewed_utc,
            "simulated": p.simulated,
        }
        for p in sorted(rows, key=lambda x: x.sn_potential, reverse=True)[:lim]
    ]
    return {
        "status": inventory_status(),
        "candidates": preview,
        "note": (
            "Inventory consolidates curated catalog + offline literature. "
            "Life expectancy optical_breakout_window is a class estimate."
        ),
    }


@app.get("/api/voice/{alert_id}/{seq}.mp3")
def voice_clip(alert_id: str, seq: int) -> FileResponse:
    """Serve announcer MP3 written under data/run/<alert_id>/voice/."""
    path = _safe_alert_dir(alert_id) / "voice" / f"{seq}.mp3"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"No voice clip {alert_id}/{seq}.mp3")
    return FileResponse(path, media_type="audio/mpeg")


@app.post("/voice/session")
def voice_session() -> dict[str, Any]:
    """Mint an ephemeral realtime token for the browser (key stays server-side)."""
    from backend.voice.realtime_session import mint_client_secret

    try:
        body = mint_client_secret(expires_after_seconds=300)
    except Exception as exc:
        logger.exception("voice session mint failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # Never echo XAI_API_KEY.
    key = (settings.xai_api_key or "").strip()
    if key and key in json.dumps(body):
        raise HTTPException(status_code=500, detail="Refusing to leak API key")
    return body


@app.get("/voice/tools/top_candidates")
@app.get("/voice/tools/get_top_candidates")
def voice_tool_top_candidates(limit: int = 5) -> dict[str, Any]:
    """Read-only judge tool: top candidates from the current run."""
    from backend.voice.tools import get_top_candidates

    return get_top_candidates(limit=limit)


@app.get("/voice/tools/skymap_summary")
@app.get("/voice/tools/get_skymap_summary")
def voice_tool_skymap_summary() -> dict[str, Any]:
    """Read-only judge tool: active skymap summary."""
    from backend.voice.tools import get_skymap_summary

    return get_skymap_summary()


@app.get("/voice/tools/breakout_countdown")
@app.get("/voice/tools/get_breakout_countdown")
def voice_tool_breakout_countdown(star_id: str | None = None) -> dict[str, Any]:
    """Read-only judge tool: breakout countdown for top or named star."""
    from backend.voice.tools import get_breakout_countdown

    return get_breakout_countdown(star_id=star_id)


@app.websocket("/ws/subscribe")
async def ws_subscribe(
    websocket: WebSocket,
    access_token: str | None = Query(default=None),
) -> None:
    """Community alert push: access_token required; auto-closes on expiry.

    Client may send ``{"type":"access_token","access_token":"…"}`` after
    ``POST /subscribe/refresh`` to extend the live wire. Otherwise the socket
    closes with code 4001 when the last access token expires.
    """
    token = (access_token or "").strip()
    if not token:
        await websocket.accept()
        try:
            first = await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
        except (TimeoutError, WebSocketDisconnect):
            await websocket.close(code=CLOSE_ACCESS_INVALID, reason="access_token_required")
            return
        try:
            payload = json.loads(first)
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            token = str(
                payload.get("access_token")
                or (payload.get("payload") or {}).get("access_token")
                or ""
            ).strip()
        if not token:
            await websocket.close(code=CLOSE_ACCESS_INVALID, reason="access_token_required")
            return
        row = verify_access_token(token)
        if row is None:
            await websocket.close(code=CLOSE_ACCESS_INVALID, reason="invalid_access_token")
            return
    else:
        row = verify_access_token(token)
        await websocket.accept()
        if row is None:
            await websocket.close(code=CLOSE_ACCESS_INVALID, reason="invalid_access_token")
            return

    exp = access_expires_at(row)
    if exp is None:
        await websocket.close(code=CLOSE_ACCESS_INVALID, reason="invalid_access_token")
        return

    await subscribe_hub.register(
        websocket,
        subscriber_id=str(row.get("id")),
        access_expires_utc=exp,
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires_in = max(0, int((exp - now).total_seconds()))
    await websocket.send_text(
        json.dumps(
            {
                "type": "subscribe_hello",
                "subscriber_id": row.get("id"),
                "access_expires_utc": exp.isoformat().replace("+00:00", "Z"),
                "expires_in_sec": expires_in,
                "note": (
                    "Push ranked community_alert packages here. "
                    "Refresh access_token via POST /subscribe/refresh and send it "
                    "on this socket before expiry, or the wire closes."
                ),
            }
        )
    )
    try:
        while True:
            message = await websocket.receive_text()
            stripped = message.strip()
            low = stripped.lower()
            if low in {"ping", '{"type":"ping"}'}:
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue
            try:
                msg = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            mtype = str(msg.get("type") or "").lower()
            if mtype in {"access_token", "auth", "extend"}:
                new_tok = str(msg.get("access_token") or "").strip()
                try:
                    extended = await subscribe_hub.extend_access(
                        websocket, access_token=new_tok
                    )
                except ValueError as exc:
                    await websocket.send_text(
                        json.dumps({"type": "error", "detail": str(exc)})
                    )
                    await websocket.close(
                        code=CLOSE_ACCESS_INVALID, reason="invalid_access_token"
                    )
                    break
                await websocket.send_text(json.dumps(extended))
    except WebSocketDisconnect:
        pass
    finally:
        await subscribe_hub.disconnect(websocket)


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    """Stream pipeline events: alert | skymap | candidates | actions | voice."""
    await hub.connect(websocket)
    hello = WsHelloEvent(
        use_cached_stream=settings.use_cached_stream,
        scenario=_hello_scenario(),
        simulated=False,
    )
    await websocket.send_text(hello.model_dump_json())
    try:
        while True:
            message = await websocket.receive_text()
            stripped = message.strip().lower()
            if stripped in {"ping", '{"type":"ping"}'}:
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    except Exception:
        await hub.disconnect(websocket)
        raise
