"""Core loop from cache with the network disabled."""

from __future__ import annotations

import socket
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if any outbound TCP connect is attempted."""

    def _blocked(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Network connect attempted while USE_CACHED_STREAM=True")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", lambda *_a, **_k: 1)


def test_e2e_scenario_a_emits_alert_skymap_candidates(
    no_network: None,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    monkeypatch.setenv("SCENARIO", "scenario_a_galactic_ccsn")
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")

    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    assert config_mod.settings.use_cached_stream is True

    # Refresh app module bindings to the reloaded settings.
    import importlib

    import backend.app as app_mod
    import backend.pipeline as pipeline_mod

    importlib.reload(app_mod)
    app = app_mod.app
    app_mod._out_root = tmp_path / "run"
    pipeline_mod.reset_watchlist()

    with TestClient(app) as client:
        with client.websocket_connect("/ws/events") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert hello["use_cached_stream"] is True

            resp = client.post("/scenario/scenario_a_galactic_ccsn/start")
            assert resp.status_code == 200
            assert resp.json()["status"] == "started"

            seen: list[dict[str, Any]] = []
            deadline_types = {"alert", "skymap", "candidates"}
            found: set[str] = set()
            for _ in range(50):
                msg = ws.receive_json()
                seen.append(msg)
                if msg.get("type") in deadline_types:
                    found.add(msg["type"])
                if found >= deadline_types:
                    break

    # Scenario A starts with PRESN then SN_BURST; skymap/candidates follow the burst.
    alert_events = [m for m in seen if m.get("type") == "alert"]
    assert alert_events, "expected at least one alert event"
    assert alert_events[0]["simulated"] is True
    assert alert_events[0]["payload"]["simulated"] is True
    burst_alerts = [m for m in alert_events if m["payload"]["kind"] == "SN_BURST"]
    assert burst_alerts, "expected an SN_BURST alert in the scenario"
    assert burst_alerts[0]["payload"]["simulated"] is True

    skymap_evt = next(m for m in seen if m.get("type") == "skymap")
    cand_evt = next(m for m in seen if m.get("type") == "candidates")

    assert skymap_evt["simulated"] is True
    assert skymap_evt["payload"]["ordering"] == "NESTED"
    assert skymap_evt["payload"]["simulated"] is True

    assert cand_evt["simulated"] is True
    candidates = cand_evt["payload"]["candidates"]
    assert isinstance(candidates, list)
    assert len(candidates) >= 1
    for row in candidates:
        assert row.get("simulated") is True
        assert "star_id" in row
        assert "posterior" in row
        assert "lit" in row
        assert isinstance(row["lit"]["evidence"], list)
