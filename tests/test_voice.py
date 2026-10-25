"""Grok Voice announcer + realtime tools (xAI API mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from backend.voice.announcer import (
    build_fill_fields,
    load_announcer_lines,
    render_line,
    reset_sequence,
    speak,
    speak_event_lines,
)
from backend.voice.realtime_session import mint_client_secret
from backend.voice.tools import (
    get_breakout_countdown,
    get_skymap_summary,
    get_top_candidates,
    reset_run_state,
    update_run_state,
)


SECRET = "test-xai-api-key-do-not-leak"


@pytest.fixture(autouse=True)
def _voice_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOICE_MODE", "off")
    monkeypatch.setenv("XAI_API_KEY", SECRET)
    monkeypatch.setenv("XAI_TTS_VOICE", "eve")
    monkeypatch.setenv("XAI_VOICE_MODEL", "grok-voice-latest")
    monkeypatch.setenv("SCENARIO", "scenario_a_galactic_ccsn")
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    reset_sequence()
    reset_run_state()


def test_lines_contain_only_payload_values() -> None:
    lines = load_announcer_lines()
    payload = {
        "kind": "SN_BURST",
        "detectors": [{"name": "Super-K"}, {"name": "IceCube"}],
        "alert_id": "sim-burst-test",
        "simulated": True,
    }
    fields = build_fill_fields("alert", payload, simulated=True)
    text = render_line(lines["alert"], fields)
    assert "SN_BURST" in text
    assert "Super-K" in text and "IceCube" in text
    assert "simulated" in text.lower()
    # No invented detector names.
    assert "KamLAND" not in text


def test_simulated_payloads_say_simulated() -> None:
    event = {
        "type": "skymap",
        "simulated": True,
        "payload": {
            "alert_id": "a1",
            "credible_90_deg2": 12.5,
            "peak": {"ra_deg": 88.79, "dec_deg": 7.41},
            "simulated": True,
        },
    }
    voice_events = speak_event_lines(event, voice_mode="off")
    assert len(voice_events) == 1
    text = voice_events[0]["payload"]["text"]
    assert "simulated" in text.lower()
    assert "12.5" in text
    assert voice_events[0]["simulated"] is True


def test_cached_and_off_modes_make_no_network_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOICE_MODE", "off")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    payload = {
        "kind": "PRESN",
        "detectors": [{"name": "KamLAND"}],
        "alert_id": "sim-presn",
        "simulated": True,
    }
    with mock.patch("httpx.Client") as client_cls:
        speak("alert", payload, voice_mode="off", run_root=tmp_path)
        client_cls.assert_not_called()

    # Cached with missing clip still must not call network.
    monkeypatch.setenv("VOICE_MODE", "cached")
    config_mod.settings = config_mod.load_settings()
    with mock.patch("httpx.Client") as client_cls:
        speak("alert", payload, voice_mode="cached", run_root=tmp_path, seq=99)
        client_cls.assert_not_called()


def test_live_tts_posts_documented_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_MODE", "live")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    class _Resp:
        content = b"ID3fake-mp3"

        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> _Resp:
            assert url == "https://api.x.ai/v1/tts"
            assert headers["Authorization"] == f"Bearer {SECRET}"
            assert json["voice_id"] == "eve"
            assert json["language"] == "en"
            assert "text" in json
            return _Resp()

    payload = {
        "kind": "SN_BURST",
        "detectors": [{"name": "Super-K"}],
        "alert_id": "sim-burst-live",
        "simulated": True,
    }
    with mock.patch("httpx.Client", _Client):
        evt = speak("alert", payload, voice_mode="live", run_root=tmp_path, seq=0)
    assert evt["payload"]["audio_url"] == "/api/voice/sim-burst-live/0.mp3"
    assert (tmp_path / "sim-burst-live" / "voice" / "0.mp3").is_file()
    assert "simulated" in evt["payload"]["text"].lower()


def test_candidates_line_includes_evidence_bibcodes() -> None:
    payload = {
        "alert_id": "sim-burst",
        "candidates": [
            {
                "star_id": "* alf Ori",
                "class": "RSG",
                "posterior": 0.91,
                "breakout": {
                    "class_window": "about 1 day",
                    "countdown_from": "2026-10-24T21:46:00Z",
                },
                "lit": {
                    "evidence": [
                        {
                            "bibcode": "2017AJ....154...11H",
                            "claim": "Harper et al. 2017 distance for Betelgeuse.",
                        }
                    ]
                },
                "simulated": True,
            }
        ],
        "simulated": True,
    }
    events = speak_event_lines(
        {"type": "candidates", "payload": payload, "simulated": True},
        voice_mode="off",
    )
    assert len(events) == 2
    top_text = events[0]["payload"]["text"]
    countdown = events[1]["payload"]["text"]
    assert "* alf Ori" in top_text
    assert "RSG" in top_text
    assert "2017AJ....154...11H" in top_text
    assert "about 1 day" in countdown
    assert "2026-10-24T21:46:00Z" in countdown
    assert "simulated" in top_text.lower()


def test_session_endpoint_never_leaks_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"value": "xai-realtime-client-secret-abc", "expires_at": 1_700_000_000}

    class _Client:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> _Resp:
            assert url == "https://api.x.ai/v1/realtime/client_secrets"
            assert headers["Authorization"] == f"Bearer {SECRET}"
            assert json == {"expires_after": {"seconds": 300}}
            return _Resp()

    with mock.patch("httpx.Client", _Client):
        body = mint_client_secret(expires_after_seconds=300)
    assert body["token"] == "xai-realtime-client-secret-abc"
    assert body["model"] == "grok-voice-latest"
    assert SECRET not in json.dumps(body)

    import importlib

    import backend.app as app_mod

    importlib.reload(app_mod)
    with mock.patch("httpx.Client", _Client):
        with TestClient(app_mod.app) as client:
            resp = client.post("/voice/session")
            assert resp.status_code == 200
            data = resp.json()
            assert data["token"].startswith("xai-realtime-client-secret-")
            assert data["model"] == "grok-voice-latest"
            assert SECRET not in resp.text
            assert "XAI_API_KEY" not in resp.text


def test_voice_tools_return_current_run_only() -> None:
    reset_run_state()
    update_run_state(
        alert_id="sim-burst",
        skymap={
            "alert_id": "sim-burst",
            "credible_90_deg2": 10.0,
            "peak": {"ra_deg": 88.8, "dec_deg": 7.4},
            "components": ["superk_pointing"],
            "nside": 64,
            "ordering": "NESTED",
            "frame": "ICRS",
            "simulated": True,
        },
        candidates=[
            {
                "star_id": "* alf Ori",
                "class": "RSG",
                "posterior": 1.0,
                "breakout": {
                    "class_window": "about 1 day",
                    "countdown_from": "2026-10-24T21:46:00Z",
                },
                "lit": {
                    "evidence": [
                        {"bibcode": "2017AJ....154...11H", "claim": "distance 222 pc"}
                    ]
                },
                "simulated": True,
            }
        ],
        simulated=True,
    )
    tops = get_top_candidates(limit=3)
    assert tops["candidates"][0]["star_id"] == "* alf Ori"
    assert tops["candidates"][0]["evidence"][0]["bibcode"] == "2017AJ....154...11H"
    assert tops["simulated"] is True

    sky = get_skymap_summary()
    assert sky["available"] is True
    assert sky["credible_90_deg2"] == 10.0
    assert sky["simulated"] is True

    cd = get_breakout_countdown()
    assert cd["class_window"] == "about 1 day"
    assert cd["countdown_from"] == "2026-10-24T21:46:00Z"
    assert cd["evidence"][0]["bibcode"] == "2017AJ....154...11H"


def test_betelgeuse_run_emits_voice_lines_off_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOICE_MODE", "off")
    monkeypatch.setenv("SCENARIO", "scenario_a_galactic_ccsn")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    import importlib

    import backend.app as app_mod
    import backend.pipeline as pipeline_mod
    from backend.literature.build_index import INDEX_PATH, seed_betelgeuse_index
    from backend.pipeline import reset_watchlist

    importlib.reload(app_mod)
    app = app_mod.app
    app_mod._out_root = tmp_path / "run"
    pipeline_mod.reset_watchlist()
    reset_watchlist()
    reset_sequence("scenario_a_galactic_ccsn")
    if not INDEX_PATH.is_file():
        seed_betelgeuse_index()

    with mock.patch("httpx.Client") as client_cls:
        with TestClient(app) as client:
            with client.websocket_connect("/ws/events") as ws:
                assert ws.receive_json()["type"] == "hello"
                assert client.post("/scenario/scenario_a_galactic_ccsn/start").status_code == 200
                voice_msgs: list[dict[str, Any]] = []
                for _ in range(150):
                    msg = ws.receive_json()
                    if msg.get("type") == "voice":
                        voice_msgs.append(msg)
                    if msg.get("type") == "scenario_done":
                        break
                # Allow late voice tasks scheduled after scenario_done.
                import time

                deadline = time.time() + 2.0
                while time.time() < deadline and len(voice_msgs) < 4:
                    try:
                        ws.send_text("ping")
                        msg = ws.receive_json()
                        if msg.get("type") == "voice":
                            voice_msgs.append(msg)
                    except Exception:
                        break
        client_cls.assert_not_called()

    texts = [m["payload"]["text"] for m in voice_msgs if m.get("payload", {}).get("text")]
    blob = " ".join(texts).lower()
    assert any("alert" in t.lower() or "mission control" in t.lower() for t in texts)
    assert any("sky map" in t.lower() or "ninety" in t.lower() for t in texts)
    assert any("alf ori" in t.lower() or "candidate" in t.lower() for t in texts)
    assert any("breakout" in t.lower() or "countdown" in t.lower() or "about 1 day" in t.lower() for t in texts)
    assert "simulated" in blob
    for m in voice_msgs:
        assert SECRET not in json.dumps(m)
