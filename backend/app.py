"""BREAKOUT FastAPI entrypoint: REST + WebSocket event stream to the UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from backend.config import ROOT, settings
from backend.ingest.cache import replay_scenario
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


async def run_scenario(name: str, *, speed: float = 0.0) -> None:
    """Replay a cached scenario through the core loop (no live network)."""
    logger.info("scenario_start name=%s speed=%s", name, speed)
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
        logger.info("startup USE_CACHED_STREAM=True scenario=%s", settings.scenario)

        async def _autostart() -> None:
            # Tests set BREAKOUT_DISABLE_AUTOSTART=1 and use POST /scenario/.../start.
            if os.environ.get("BREAKOUT_DISABLE_AUTOSTART") == "1":
                return
            await asyncio.sleep(0.05)
            await _start_scenario_task(settings.scenario, speed=0.0)

        asyncio.create_task(_autostart())
    else:
        logger.info("startup live listeners")
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
        "scenario": settings.scenario,
        "voice_mode": settings.voice_mode,
        "lcogt_dry_run": settings.lcogt_dry_run,
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
    return FileResponse(png, media_type="image/png")


def _star_id_slug(star_id: str) -> str:
    import re

    cleaned = re.sub(r"[^\w.\-]+", "_", star_id.strip(), flags=re.UNICODE)
    return cleaned.strip("._") or "unknown"


@app.get("/api/literature/raw/{star_id:path}")
def literature_raw(star_id: str) -> dict[str, Any]:
    """Return offline Grok raw JSON for a star (reasoning + evidence).

    Never invents claims: serves ``data/index/raw/<slug>.json`` when present;
    otherwise returns evidence from ``index.parquet`` only (no synthetic reasoning).
    """
    from backend.literature.build_index import INDEX_PATH, RAW_DIR

    slug = _star_id_slug(star_id)
    raw_path = RAW_DIR / f"{slug}.json"
    if raw_path.is_file():
        return json.loads(raw_path.read_text(encoding="utf-8"))

    # Fallback: evidence from the offline index only — no invented reasoning text.
    evidence: list[dict[str, Any]] = []
    lit: dict[str, Any] = {
        "mass_loss": 0.0,
        "variability": 0.0,
        "evolved_stage": 0.0,
        "confidence": 0.0,
        "evidence": [],
    }
    if INDEX_PATH.is_file():
        import pandas as pd

        df = pd.read_parquet(INDEX_PATH)
        hit = df.loc[df["star_id"].astype(str) == str(star_id)]
        if len(hit) == 0:
            # Try common_name-less match on stripped ids.
            hit = df.loc[df["star_id"].astype(str).str.contains(star_id.replace("*", ""), regex=False)]
        if len(hit) > 0:
            row = hit.iloc[0].to_dict()
            raw_ev = row.get("evidence_json") or "[]"
            evidence = json.loads(raw_ev) if isinstance(raw_ev, str) else list(raw_ev or [])
            lit = {
                "mass_loss": float(row.get("mass_loss", 0.0) or 0.0),
                "variability": float(row.get("variability", 0.0) or 0.0),
                "evolved_stage": float(row.get("evolved_stage", 0.0) or 0.0),
                "confidence": float(row.get("confidence", 0.0) or 0.0),
                "evidence": evidence,
            }
    return {
        "star_id": star_id,
        "reasoning": None,
        "literature": lit,
        "raw_missing": True,
        "note": "No data/index/raw file for this star; evidence from index.parquet only.",
        "simulated": False,
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


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    """Stream pipeline events: alert | skymap | candidates | actions | voice."""
    await hub.connect(websocket)
    hello = WsHelloEvent(
        use_cached_stream=settings.use_cached_stream,
        scenario=settings.scenario,
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
