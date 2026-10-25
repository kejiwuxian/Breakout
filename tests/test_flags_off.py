"""P2.0: with every Phase 2 flag False, the MVP behaves as before."""

from __future__ import annotations

import importlib
import socket
from typing import Any

import pytest
from fastapi.testclient import TestClient


PHASE2_FLAGS = (
    "DROID_ENABLED",
    "CONVEX_ENABLED",
    "APIFY_ENABLED",
    "TIGER_ENABLED",
)


@pytest.fixture()
def phase2_flags_off(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PHASE2_FLAGS:
        monkeypatch.setenv(name, "False")


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Network connect attempted while USE_CACHED_STREAM=True")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", lambda *_a, **_k: 1)


def test_settings_phase2_flags_default_false(phase2_flags_off: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DROID_ENABLED", raising=False)
    monkeypatch.delenv("CONVEX_ENABLED", raising=False)
    monkeypatch.delenv("APIFY_ENABLED", raising=False)
    monkeypatch.delenv("TIGER_ENABLED", raising=False)

    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    s = config_mod.settings
    assert s.droid_enabled is False
    assert s.convex_enabled is False
    assert s.apify_enabled is False
    assert s.tiger_enabled is False


def test_apify_noop_when_flag_off(
    phase2_flags_off: None, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("APIFY_ENABLED", "False")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    from backend.integrations import apify_literature

    importlib.reload(apify_literature)
    written = apify_literature.fetch_and_store(
        [{"star_id": "* alf Ori", "aliases": ["Betelgeuse"]}],
        out_dir=tmp_path,
    )
    assert written == {}
    assert list(tmp_path.iterdir()) == []


def test_e2e_scenario_a_with_all_phase2_flags_off(
    phase2_flags_off: None,
    no_network: None,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    monkeypatch.setenv("SCENARIO", "scenario_a_galactic_ccsn")
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")
    for name in PHASE2_FLAGS:
        monkeypatch.setenv(name, "False")

    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    assert config_mod.settings.apify_enabled is False
    assert config_mod.settings.droid_enabled is False
    assert config_mod.settings.convex_enabled is False
    assert config_mod.settings.tiger_enabled is False

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

            resp = client.post("/scenario/scenario_a_galactic_ccsn/start")
            assert resp.status_code == 200
            assert resp.json()["status"] == "started"

            found: set[str] = set()
            for _ in range(50):
                msg = ws.receive_json()
                if msg.get("type") in {"alert", "skymap", "candidates"}:
                    found.add(msg["type"])
                if found >= {"alert", "skymap", "candidates"}:
                    break

    assert found >= {"alert", "skymap", "candidates"}
