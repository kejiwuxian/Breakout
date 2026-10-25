"""BREAKOUT FastAPI entrypoint: REST + WebSocket event stream to the UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from backend.config import ROOT, settings
from backend.ingest.cache import replay_scenario
from backend.pipeline import process_alert, reset_watchlist
from backend.schemas import WsHelloEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("breakout.app")


class EventHub:
    """Fan-out hub for /ws/events subscribers."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

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
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


hub = EventHub()
_run_lock = asyncio.Lock()
_run_task: asyncio.Task[None] | None = None
_out_root = ROOT / "data" / "run"


async def _emit_pipeline_events(alert: Any) -> None:
    events = await asyncio.to_thread(process_alert, alert, out_root=_out_root)
    for event in events:
        await hub.broadcast(event)


async def run_scenario(name: str, *, speed: float = 0.0) -> None:
    """Replay a cached scenario through the core loop (no live network)."""
    logger.info("scenario_start name=%s speed=%s", name, speed)
    reset_watchlist()
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

    Each listener runs in a worker thread and schedules pipeline work on the
    asyncio loop. Credentials come only from .env; modules no-op if cached.
    """
    from backend.ingest import gcn_kafka, presn, snews

    loop = asyncio.get_running_loop()

    def _pump(name: str, factory: Any) -> None:
        logger.info("live_listener_start %s", name)
        try:
            for alert in factory():
                fut = asyncio.run_coroutine_threadsafe(_emit_pipeline_events(alert), loop)
                fut.result()
        except Exception:
            logger.exception("live_listener_failed %s", name)

    asyncio.create_task(asyncio.to_thread(_pump, "presn", lambda: presn.listen_presn_alerts()))
    asyncio.create_task(asyncio.to_thread(_pump, "snews", lambda: snews.listen_snews_alerts()))
    asyncio.create_task(
        asyncio.to_thread(_pump, "gcn_kafka", lambda: gcn_kafka.listen_gcn_alerts())
    )

@asynccontextmanager
async def lifespan(_app: FastAPI):
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
    """Resolve data/run/<alert_id> without path traversal."""
    import re

    if not re.fullmatch(r"[A-Za-z0-9._\-+:]+", alert_id):
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


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    """Stream pipeline events: alert | skymap | candidates | actions."""
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
