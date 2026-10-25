"""Scenario D: GCN Circular 25913 IceCube-191001A → real HE_NEUTRINO path."""

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


SCENARIO = "scenario_d_icecube_191001a"
CACHE = ROOT / "data" / "cache" / SCENARIO

# Published refined direction (GCN Circular 25913).
RA_DEG = 314.08
DEC_DEG = 12.94


def test_scenario_d_alert_is_real_he_neutrino() -> None:
    path = CACHE / "alerts.jsonl"
    assert path.is_file()
    alert = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert alert["simulated"] is False
    assert alert["kind"] == "HE_NEUTRINO"
    assert alert["alert_id"] == "IceCube-191001A"
    assert alert["raw"]["ra"] == pytest.approx(RA_DEG)
    assert alert["raw"]["dec"] == pytest.approx(DEC_DEG)
    assert alert["raw"]["gcn_circular"] == 25913


def test_archive_copies_contain_published_coordinates() -> None:
    circ = (CACHE / "gcn_circular_25913.txt").read_text(encoding="utf-8")
    assert "IceCube-191001A" in circ
    assert "314.08" in circ
    assert "12.94" in circ
    amon = (CACHE / "gcn_amon_notice_133119_22683750.txt").read_text(encoding="utf-8")
    assert "133119" in amon
    assert "22683750" in amon
    assert "SRC_ERROR" in amon


def test_notice_normalizes_to_same_alert() -> None:
    notice = json.loads((CACHE / "notice.json").read_text(encoding="utf-8"))
    alert = normalize_gcn_payload(notice, simulated=False)
    assert alert.simulated is False
    assert alert.alert_id == "IceCube-191001A"
    assert alert.detectors[0].pointing is not None
    assert alert.detectors[0].pointing.ra_deg == pytest.approx(RA_DEG)
    assert alert.detectors[0].pointing.dec_deg == pytest.approx(DEC_DEG)
    assert alert.detectors[0].pointing.err_deg == pytest.approx(2.95)


def test_fuse_recovers_published_direction(tmp_path: Path) -> None:
    notice = json.loads((CACHE / "notice.json").read_text(encoding="utf-8"))
    alert = normalize_gcn_payload(notice, simulated=False)
    skymap = fuse(alert, nside=64, out_root=tmp_path)
    assert skymap.simulated is False
    assert "timing:snews_diffpointing" not in skymap.components
    prob = np.asarray(hp.read_map(str(tmp_path / alert.alert_id / "skymap.fits"), nest=True))
    assert position_in_credible_region(prob, RA_DEG, DEC_DEG, level=0.9)


def test_scenario_d_replay_emits_skymap(
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
