"""Event → scripted line → Grok TTS audio, pushed to the UI.

Spoken lines come from ``data/voice/announcer_lines.json`` filled only with real
payload fields; say \"simulated\" when the payload is simulated.

``VOICE_MODE=live`` calls POST https://api.x.ai/v1/tts (docs.x.ai); cached plays
pre-rendered clips; off is captions only. Runs after the pipeline and never
blocks it. On live TTS errors, log and fall back to cached.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Callable, Awaitable

import httpx

from backend import config as config_mod
from backend.config import ROOT

logger = logging.getLogger("breakout.voice.announcer")

LINES_PATH = ROOT / "data" / "voice" / "announcer_lines.json"
TTS_URL = "https://api.x.ai/v1/tts"

# Template keys in announcer_lines.json keyed by pipeline event type.
EVENT_LINE_KEYS: dict[str, list[str]] = {
    "alert": ["alert"],
    "skymap": ["localization"],
    "candidates": ["top_candidate", "countdown"],
}

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")

# Per-scenario spoken sequence (thread-safe for background tasks).
_seq_lock = threading.Lock()
_seq_by_scenario: dict[str, int] = {}
_last_alert_id: str | None = None

# Optional push callback set by app.py (broadcast voice events).
_push_voice: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None


def set_voice_pusher(
    pusher: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
) -> None:
    """Register an async/sync callback that receives voice WS events."""
    global _push_voice
    _push_voice = pusher


def reset_sequence(scenario: str | None = None) -> None:
    """Reset spoken seq counters (call when a scenario starts)."""
    with _seq_lock:
        if scenario is None:
            _seq_by_scenario.clear()
        else:
            _seq_by_scenario[scenario] = 0


def _next_seq(scenario: str) -> int:
    with _seq_lock:
        seq = _seq_by_scenario.get(scenario, 0)
        _seq_by_scenario[scenario] = seq + 1
        return seq


def load_announcer_lines(path: Path = LINES_PATH) -> dict[str, str]:
    """Load Barron's announcer script templates."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("announcer_lines.json must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def _detector_names(payload: dict[str, Any]) -> str:
    detectors = payload.get("detectors") or []
    names: list[str] = []
    for hit in detectors:
        if isinstance(hit, dict) and hit.get("name"):
            names.append(str(hit["name"]))
    return ", ".join(names) if names else "unknown detectors"


def _fmt_deg(value: Any) -> str:
    try:
        return f"{float(value):.3f} degrees"
    except (TypeError, ValueError):
        return "unknown"


def _fmt_area(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "unknown"


def _fmt_posterior(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "unknown"


def _evidence_fields(top: dict[str, Any]) -> tuple[str, str]:
    """Build evidence summary + spoken bibcodes from real CandidateScore evidence only."""
    lit = top.get("lit") if isinstance(top.get("lit"), dict) else {}
    evidence = lit.get("evidence") or []
    claims: list[str] = []
    bibs: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        bib = str(item.get("bibcode") or "").strip()
        claim = str(item.get("claim") or "").strip()
        if not bib or not claim:
            continue  # no bibcode → no claim
        bibs.append(bib)
        # Keep claims short for speech.
        short = claim if len(claim) <= 140 else claim[:137].rstrip() + "..."
        claims.append(f"{short} ({bib})")
    if not claims:
        return (
            "No ADS-bibcoded evidence on this row.",
            "none",
        )
    summary = " ".join(claims[:3])
    spoken = ", ".join(bibs[:5])
    return summary, spoken


def build_fill_fields(
    event_type: str,
    payload: dict[str, Any],
    *,
    simulated: bool,
) -> dict[str, str]:
    """Extract template fill fields from a real event payload only."""
    fields: dict[str, str] = {
        "simulated_note": "simulated." if simulated else "",
    }

    if event_type == "alert":
        fields["kind"] = str(payload.get("kind") or "unknown")
        fields["detectors"] = _detector_names(payload)
        return fields

    if event_type == "skymap":
        peak = payload.get("peak") if isinstance(payload.get("peak"), dict) else {}
        fields["credible_90_deg2"] = _fmt_area(payload.get("credible_90_deg2"))
        fields["peak_ra"] = _fmt_deg(peak.get("ra_deg"))
        fields["peak_dec"] = _fmt_deg(peak.get("dec_deg"))
        return fields

    if event_type == "candidates":
        cands = payload.get("candidates") or []
        top = cands[0] if cands and isinstance(cands[0], dict) else {}
        evidence_summary, bibcodes_spoken = _evidence_fields(top)
        star_class = top.get("class") or top.get("class_") or "unknown"
        breakout = top.get("breakout") if isinstance(top.get("breakout"), dict) else {}
        fields.update(
            {
                "star_id": str(top.get("star_id") or "unknown"),
                "class": str(star_class),
                "posterior": _fmt_posterior(top.get("posterior")),
                "evidence_summary": evidence_summary,
                "bibcodes_spoken": bibcodes_spoken,
                "class_window": str(breakout.get("class_window") or "unknown"),
                "countdown_from": str(breakout.get("countdown_from") or "unknown"),
            }
        )
        return fields

    return fields


def render_line(template: str, fields: dict[str, str]) -> str:
    """Fill a template only with provided fields; never invent numbers.

    Unknown placeholders become empty strings (still no invented values).
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(fields.get(key, ""))

    text = _PLACEHOLDER_RE.sub(_replace, template)
    text = re.sub(r"\s{2,}", " ", text).strip()
    # Ensure simulated payloads end with the word when the note was empty-spaced.
    if fields.get("simulated_note") and "simulated" not in text.lower():
        text = f"{text} simulated."
    return text


def _alert_id_from_event(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "alert":
        return str(payload.get("alert_id") or "unknown")
    if event_type == "skymap":
        return str(payload.get("alert_id") or "unknown")
    if event_type == "candidates":
        return str(payload.get("alert_id") or "unknown")
    return "unknown"


def _run_voice_dir(alert_id: str, run_root: Path) -> Path:
    path = Path(run_root) / alert_id / "voice"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_voice_path(scenario: str, seq: int) -> Path:
    return ROOT / "data" / "cache" / scenario / "voice" / f"{seq}.mp3"


def call_tts(text: str, *, voice_id: str, api_key: str) -> bytes:
    """POST https://api.x.ai/v1/tts — returns raw MP3 bytes (docs.x.ai)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {"text": text, "voice_id": voice_id, "language": "en"}
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(TTS_URL, headers=headers, json=body)
        resp.raise_for_status()
        return resp.content


def _try_cached_audio(scenario: str, seq: int) -> Path | None:
    path = _cache_voice_path(scenario, seq)
    return path if path.is_file() else None


def speak(
    event_type: str,
    payload: dict[str, Any],
    *,
    voice_mode: str | None = None,
    voice_id: str | None = None,
    simulated: bool | None = None,
    scenario: str | None = None,
    run_root: Path | None = None,
    lines: dict[str, str] | None = None,
    seq: int | None = None,
    line_key: str | None = None,
) -> dict[str, Any]:
    """Produce announcer audio/caption for an event.

    Returns a voice event dict for ``/ws/events``:
    ``{ type: voice, payload: { text, audio_url, simulated }, simulated }``.
    """
    settings = config_mod.settings
    mode = (voice_mode or settings.voice_mode or "off").lower()
    vid = voice_id or settings.xai_tts_voice or "eve"
    scen = scenario or settings.scenario
    out_root = Path(run_root) if run_root is not None else ROOT / "data" / "run"
    templates = lines if lines is not None else load_announcer_lines()

    is_sim = bool(payload.get("simulated")) if simulated is None else bool(simulated)
    # Event-level simulated flag may live beside payload.
    fields = build_fill_fields(event_type, payload, simulated=is_sim)

    key = line_key
    if key is None:
        keys = EVENT_LINE_KEYS.get(event_type) or []
        key = keys[0] if keys else event_type
    template = templates.get(key) or ""
    text = render_line(template, fields) if template else ""

    alert_id = _alert_id_from_event(event_type, payload)
    global _last_alert_id
    _last_alert_id = alert_id
    spoken_seq = seq if seq is not None else _next_seq(scen)

    audio_url: str | None = None
    audio_path: Path | None = None

    if mode == "off":
        return {
            "type": "voice",
            "payload": {
                "text": text,
                "audio_url": None,
                "simulated": is_sim,
                "seq": spoken_seq,
                "line_key": key,
                "alert_id": alert_id,
            },
            "simulated": is_sim,
        }

    if mode == "cached":
        cached = _try_cached_audio(scen, spoken_seq)
        if cached is not None:
            # Copy into run dir for a stable /api URL when possible.
            dest = _run_voice_dir(alert_id, out_root) / f"{spoken_seq}.mp3"
            if not dest.is_file():
                dest.write_bytes(cached.read_bytes())
            audio_path = dest
            audio_url = f"/api/voice/{alert_id}/{spoken_seq}.mp3"
        else:
            logger.warning(
                "voice cached clip missing scenario=%s seq=%s", scen, spoken_seq
            )
        return {
            "type": "voice",
            "payload": {
                "text": text,
                "audio_url": audio_url,
                "simulated": is_sim,
                "seq": spoken_seq,
                "line_key": key,
                "alert_id": alert_id,
                "path": str(audio_path) if audio_path else None,
            },
            "simulated": is_sim,
        }

    # live
    api_key = (settings.xai_api_key or "").strip()
    used_mode = "live"
    try:
        if not api_key:
            raise RuntimeError("XAI_API_KEY missing for VOICE_MODE=live")
        mp3 = call_tts(text, voice_id=vid, api_key=api_key)
        dest = _run_voice_dir(alert_id, out_root) / f"{spoken_seq}.mp3"
        dest.write_bytes(mp3)
        audio_path = dest
        audio_url = f"/api/voice/{alert_id}/{spoken_seq}.mp3"
    except Exception:
        logger.exception(
            "voice live TTS failed; falling back to cached alert_id=%s seq=%s",
            alert_id,
            spoken_seq,
        )
        used_mode = "cached_fallback"
        cached = _try_cached_audio(scen, spoken_seq)
        if cached is not None:
            dest = _run_voice_dir(alert_id, out_root) / f"{spoken_seq}.mp3"
            dest.write_bytes(cached.read_bytes())
            audio_path = dest
            audio_url = f"/api/voice/{alert_id}/{spoken_seq}.mp3"

    return {
        "type": "voice",
        "payload": {
            "text": text,
            "audio_url": audio_url,
            "simulated": is_sim,
            "seq": spoken_seq,
            "line_key": key,
            "alert_id": alert_id,
            "voice_mode_used": used_mode,
            "path": str(audio_path) if audio_path else None,
        },
        "simulated": is_sim,
    }


def speak_event_lines(
    event: dict[str, Any],
    *,
    voice_mode: str | None = None,
    run_root: Path | None = None,
    scenario: str | None = None,
) -> list[dict[str, Any]]:
    """Render all announcer lines for a pipeline event (alert/skymap/candidates)."""
    event_type = str(event.get("type") or "")
    if event_type not in EVENT_LINE_KEYS:
        return []
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    simulated = bool(event.get("simulated", payload.get("simulated", False)))
    # Prefer event-level simulated; also stamp payload for field builder.
    payload = dict(payload)
    payload.setdefault("simulated", simulated)

    out: list[dict[str, Any]] = []
    for line_key in EVENT_LINE_KEYS[event_type]:
        out.append(
            speak(
                event_type,
                payload,
                voice_mode=voice_mode,
                simulated=simulated,
                scenario=scenario,
                run_root=run_root,
                line_key=line_key,
            )
        )
    return out


async def handle_pipeline_event(event: dict[str, Any]) -> None:
    """Background handler: never blocks the pipeline; pushes voice events."""
    event_type = str(event.get("type") or "")
    if event_type not in EVENT_LINE_KEYS:
        return
    settings = config_mod.settings
    try:
        voice_events = await asyncio.to_thread(
            speak_event_lines,
            event,
            voice_mode=settings.voice_mode,
            run_root=ROOT / "data" / "run",
            scenario=settings.scenario,
        )
    except Exception:
        logger.exception("voice handle_pipeline_event failed type=%s", event_type)
        return

    pusher = _push_voice
    for ve in voice_events:
        if pusher is None:
            continue
        try:
            result = pusher(ve)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                await result  # type: ignore[misc]
        except Exception:
            logger.exception("voice push failed")


def attach_to_hub(hub: Any) -> None:
    """Subscribe to an EventHub-like object with ``subscribe(listener)``."""
    if hasattr(hub, "subscribe"):
        hub.subscribe(_on_hub_event)
        return
    raise TypeError("hub must support subscribe(listener)")


def _on_hub_event(event: dict[str, Any]) -> Any:
    """Hub listener: return a coroutine the hub can await or background-task."""
    event_type = str(event.get("type") or "")
    if event_type not in EVENT_LINE_KEYS:
        return None
    return handle_pipeline_event(event)


def prerender_scenario(scenario: str, *, force: bool = False) -> list[Path]:
    """Render cached MP3 clips for a scenario via live TTS (network once).

    Writes ``data/cache/<scenario>/voice/<seq>.mp3``. Requires XAI_API_KEY.
    """
    from backend.pipeline import process_alert, reset_watchlist
    from backend.schemas import Alert

    settings = config_mod.settings
    api_key = (settings.xai_api_key or "").strip()
    if not api_key:
        raise RuntimeError("XAI_API_KEY required for --prerender")

    templates = load_announcer_lines()
    out_dir = ROOT / "data" / "cache" / scenario / "voice"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    seq = 0
    reset_watchlist()

    cache_dir = ROOT / "data" / "cache" / scenario
    alerts_path = cache_dir / "alerts.jsonl"
    if not alerts_path.is_file():
        raise FileNotFoundError(alerts_path)

    alerts: list[Alert] = []
    for line in alerts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        alerts.append(Alert.model_validate_json(line))

    tmp_run = ROOT / "data" / "run" / "_prerender"
    tmp_run.mkdir(parents=True, exist_ok=True)

    for alert in alerts:
        events = process_alert(alert, out_root=tmp_run)
        for event in events:
            et = str(event.get("type") or "")
            if et not in EVENT_LINE_KEYS:
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            simulated = bool(event.get("simulated", payload.get("simulated", False)))
            payload = dict(payload)
            payload["simulated"] = simulated
            for line_key in EVENT_LINE_KEYS[et]:
                dest = out_dir / f"{seq}.mp3"
                if dest.is_file() and not force:
                    logger.info("prerender skip existing %s", dest)
                    written.append(dest)
                    seq += 1
                    continue
                fields = build_fill_fields(et, payload, simulated=simulated)
                text = render_line(templates.get(line_key, ""), fields)
                logger.info("prerender seq=%s key=%s text=%r", seq, line_key, text[:80])
                mp3 = call_tts(text, voice_id=settings.xai_tts_voice or "eve", api_key=api_key)
                dest.write_bytes(mp3)
                written.append(dest)
                seq += 1

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BREAKOUT Grok Voice announcer")
    parser.add_argument(
        "--prerender",
        metavar="SCENARIO",
        help="Render data/cache/<scenario>/voice/*.mp3 via xAI TTS (network once)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing cached clips when prerendering",
    )
    args = parser.parse_args(argv)
    if args.prerender:
        paths = prerender_scenario(args.prerender, force=args.force)
        for p in paths:
            print(p)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
