"""Cold start stays idle: no auto scenario replay until POST /scenario/.../start."""

from __future__ import annotations

import socket
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Network connect attempted while USE_CACHED_STREAM=True")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", lambda *_a, **_k: 1)


def test_cold_start_idle_no_autostart_alerts(
    no_network: None,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without BREAKOUT_AUTOSTART, startup must not emit alert/candidates."""
    monkeypatch.delenv("BREAKOUT_AUTOSTART", raising=False)
    monkeypatch.delenv("BREAKOUT_DISABLE_AUTOSTART", raising=False)
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    monkeypatch.setenv("SCENARIO", "scenario_a_galactic_ccsn")
    monkeypatch.setenv("VOICE_MODE", "off")

    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    import importlib

    import backend.app as app_mod
    import backend.pipeline as pipeline_mod

    importlib.reload(app_mod)
    app = app_mod.app
    app_mod._out_root = tmp_path / "run"
    app_mod._active_scenario = None
    pipeline_mod.reset_watchlist()

    with TestClient(app) as client:
        # Former default would auto-start Scenario A within ~50ms.
        time.sleep(0.25)
        assert app_mod._active_scenario is None
        task = app_mod._run_task
        assert task is None or task.done()

        health = client.get("/health")
        assert health.status_code == 200
        body = health.json()
        assert body["scenario"] == "live_waiting"
        assert body["configured_scenario"] == "scenario_a_galactic_ccsn"

        with client.websocket_connect("/ws/events") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert hello["scenario"] == "live_waiting"
            assert hello["use_cached_stream"] is True

            resp = client.post("/scenario/scenario_a_galactic_ccsn/start")
            assert resp.status_code == 200
            assert resp.json()["status"] == "started"

            found: set[str] = set()
            for _ in range(50):
                msg = ws.receive_json()
                t = msg.get("type")
                if t in {"alert", "skymap", "candidates", "scenario_done"}:
                    found.add(str(t))
                if {"alert", "skymap", "candidates"} <= found:
                    break

            assert "alert" in found
            assert client.get("/health").json()["scenario"] == "scenario_a_galactic_ccsn"

    # Leave process idle for other tests sharing the app module.
    app_mod._active_scenario = None


def test_should_autostart_opt_in_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app as app_mod

    monkeypatch.delenv("BREAKOUT_AUTOSTART", raising=False)
    monkeypatch.delenv("BREAKOUT_DISABLE_AUTOSTART", raising=False)
    assert app_mod._should_autostart_scenario() is False

    monkeypatch.setenv("BREAKOUT_AUTOSTART", "1")
    assert app_mod._should_autostart_scenario() is True

    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")
    assert app_mod._should_autostart_scenario() is False
