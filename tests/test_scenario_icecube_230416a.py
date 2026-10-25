"""Scenario C: GCN public IceCube-230416A notice → real HE_NEUTRINO path."""

from __future__ import annotations

import json
from pathlib import Path

import healpy as hp
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.config import ROOT
from backend.ingest.gcn_kafka import normalize_gcn_payload
from backend.localize.fuse import fuse, position_in_credible_region
from backend.pipeline import reset_watchlist


SCENARIO = "scenario_c_icecube_230416a"
CACHE = ROOT / "data" / "cache" / SCENARIO


def test_scenario_c_alert_is_real_he_neutrino() -> None:
    path = CACHE / "alerts.jsonl"
    assert path.is_file()
    alert = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert alert["simulated"] is False
    assert alert["kind"] == "HE_NEUTRINO"
    assert alert["alert_id"] == "IceCube-230416A"
    assert alert["raw"]["ra"] == pytest.approx(345.82)
    assert alert["raw"]["dec"] == pytest.approx(9.01)


def test_notice_normalizes_to_same_alert() -> None:
    notice = json.loads((CACHE / "notice.json").read_text(encoding="utf-8"))
    alert = normalize_gcn_payload(notice, simulated=False)
    assert alert.simulated is False
    assert alert.alert_id == "IceCube-230416A"
    assert alert.detectors[0].pointing is not None
    assert alert.detectors[0].pointing.ra_deg == pytest.approx(345.82)
    assert alert.detectors[0].pointing.dec_deg == pytest.approx(9.01)


def test_fuse_recovers_published_direction(tmp_path: Path) -> None:
    notice = json.loads((CACHE / "notice.json").read_text(encoding="utf-8"))
    alert = normalize_gcn_payload(notice, simulated=False)
    skymap = fuse(alert, nside=64, out_root=tmp_path)
    assert skymap.simulated is False
    prob = np.asarray(hp.read_map(str(tmp_path / alert.alert_id / "skymap.fits"), nest=True))
    assert position_in_credible_region(prob, 345.82, 9.01, level=0.9)


def test_scenario_c_replay_emits_skymap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    monkeypatch.setenv("SCENARIO", SCENARIO)
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")

    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    import importlib

    import backend.app as app_mod
    import backend.pipeline as pipeline_mod

    importlib.reload(app_mod)
    app_mod._out_root = tmp_path / "run"
    pipeline_mod.reset_watchlist()
    reset_watchlist()

    with TestClient(app_mod.app) as client:
        with client.websocket_connect("/ws/events") as ws:
            assert ws.receive_json()["type"] == "hello"
            assert client.post(f"/scenario/{SCENARIO}/start").status_code == 200
            types: list[str] = []
            for _ in range(50):
                msg = ws.receive_json()
                types.append(str(msg.get("type")))
                if msg.get("type") == "scenario_done":
                    break
    assert "alert" in types
    assert "skymap" in types
    assert "scenario_done" in types
