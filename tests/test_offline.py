"""No network with USE_CACHED_STREAM=True and VOICE_MODE=cached.

Monkeypatches ``socket.socket.connect`` to raise so any attempt by
astroquery, ADS, Grok, xAI voice, gcn-kafka, or similar fails loudly.
Both cached scenarios must complete end to end.
"""

from __future__ import annotations

import importlib
import socket
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.config import ROOT

SCENARIOS = (
    "scenario_a_galactic_ccsn",
    "scenario_b_icecube_170922a",
)


@pytest.fixture
def block_network(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Raise on any real socket connect (offline demo / venue Wi-Fi off)."""
    attempts: list[tuple[Any, ...]] = []

    def _blocked(self: socket.socket, address: Any) -> None:  # noqa: ANN401
        attempts.append(address if isinstance(address, tuple) else (address,))
        raise OSError(
            f"OFFLINE TEST: network connect blocked to {address!r}. "
            "USE_CACHED_STREAM=True / VOICE_MODE=cached must not dial out."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    return attempts


@pytest.fixture
def offline_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    monkeypatch.setenv("VOICE_MODE", "cached")
    monkeypatch.setenv("LCOGT_DRY_RUN", "True")
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")
    monkeypatch.setenv("SCENARIO", "scenario_a_galactic_ccsn")
    # Empty keys — offline path must not need them.
    monkeypatch.setenv("XAI_API_KEY", "")
    monkeypatch.setenv("ADS_API_TOKEN", "")
    monkeypatch.setenv("GCN_CLIENT_ID", "")
    monkeypatch.setenv("GCN_CLIENT_SECRET", "")
    monkeypatch.setenv("LCOGT_API_TOKEN", "")

    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    assert config_mod.settings.use_cached_stream is True
    assert config_mod.settings.voice_mode == "cached"
    assert config_mod.settings.lcogt_dry_run is True

    import backend.app as app_mod
    import backend.pipeline as pipeline_mod
    from backend.pipeline import reset_watchlist
    from backend.voice.announcer import reset_sequence
    from backend.voice.tools import reset_run_state

    importlib.reload(app_mod)
    app_mod._out_root = tmp_path / "run"
    pipeline_mod.reset_watchlist()
    reset_watchlist()
    reset_run_state()
    reset_sequence()
    return app_mod


def _assert_voice_cache(scenario: str) -> None:
    voice_dir = ROOT / "data" / "cache" / scenario / "voice"
    assert voice_dir.is_dir(), f"missing voice cache dir {voice_dir}"
    clips = sorted(voice_dir.glob("*.mp3"))
    assert clips, f"no cached MP3 clips under {voice_dir}"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_completes_with_network_blocked(
    scenario: str,
    offline_app: Any,
    block_network: list[tuple[Any, ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each cached scenario finishes with zero socket.connect attempts."""
    _assert_voice_cache(scenario)
    monkeypatch.setenv("SCENARIO", scenario)
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    from backend.voice.announcer import reset_sequence
    from backend.voice.tools import reset_run_state
    from backend.pipeline import reset_watchlist
    import backend.pipeline as pipeline_mod

    index_path = ROOT / "backend" / "literature" / "index.parquet"
    if not index_path.is_file():
        pytest.fail(f"missing offline literature index at {index_path}")

    pipeline_mod.reset_watchlist()
    reset_watchlist()
    reset_run_state()
    reset_sequence(scenario)

    app = offline_app.app
    with TestClient(app) as client:
        with client.websocket_connect("/ws/events") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"

            resp = client.post(f"/scenario/{scenario}/start")
            assert resp.status_code == 200

            types: list[str] = []
            got_done = False
            for _ in range(200):
                msg = ws.receive_json()
                types.append(str(msg.get("type")))
                if msg.get("type") == "scenario_done":
                    got_done = True
                    assert msg["payload"]["scenario"] == scenario
                    break

    assert got_done, f"scenario_done missing; saw {types}"
    assert "alert" in types
    # SN_BURST / HE_NEUTRINO paths emit skymap + candidates; PRESN-only would not.
    if scenario == "scenario_a_galactic_ccsn":
        assert "skymap" in types and "candidates" in types
        assert "voice" in types
    if scenario == "scenario_b_icecube_170922a":
        assert "skymap" in types and "candidates" in types
        assert "voice" in types

    assert block_network == [], (
        f"offline test made network connect attempts: {block_network[:5]}"
    )


def test_both_scenarios_offline_back_to_back(
    offline_app: Any,
    block_network: list[tuple[Any, ...]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run A then B under one blocked-network session (demo preflight path)."""
    from backend import config as config_mod
    from backend.pipeline import reset_watchlist
    import backend.pipeline as pipeline_mod
    from backend.voice.announcer import reset_sequence
    from backend.voice.tools import reset_run_state

    app = offline_app.app
    with TestClient(app) as client:
        with client.websocket_connect("/ws/events") as ws:
            assert ws.receive_json()["type"] == "hello"
            for scenario in SCENARIOS:
                _assert_voice_cache(scenario)
                monkeypatch.setenv("SCENARIO", scenario)
                config_mod.settings = config_mod.load_settings()
                pipeline_mod.reset_watchlist()
                reset_watchlist()
                reset_run_state()
                reset_sequence(scenario)

                assert client.post(f"/scenario/{scenario}/start").status_code == 200
                done = False
                for _ in range(200):
                    msg = ws.receive_json()
                    if msg.get("type") == "scenario_done":
                        assert msg["payload"]["scenario"] == scenario
                        done = True
                        break
                assert done, f"{scenario} did not finish offline"

    assert block_network == [], f"network attempts: {block_network[:5]}"
