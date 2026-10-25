"""Health endpoint smoke test for scaffold / CI."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import app


def test_health_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "breakout"
    assert "use_cached_stream" in body
    assert "scenario" in body


def test_ws_events_hello() -> None:
    import backend.app as app_mod

    app_mod._active_scenario = None
    client = TestClient(app)
    with client.websocket_connect("/ws/events") as ws:
        hello = ws.receive_json()
    assert hello["type"] == "hello"
    assert hello["service"] == "breakout"
    assert "use_cached_stream" in hello
    assert hello["scenario"] == "live_waiting"
