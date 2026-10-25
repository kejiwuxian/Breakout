"""Scenario B: IceCube-170922A HE_NEUTRINO → TXS 0506+056 from catalog match."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.candidates.blazars import load_cached_blazars
from backend.config import ROOT
from backend.pipeline import reset_watchlist


SCENARIO = "scenario_b_icecube_170922a"
TXS_ID = "TXS 0506+056"
CACHE = ROOT / "data" / "cache" / SCENARIO


def test_scenario_b_cache_is_real_not_simulated() -> None:
    alerts_path = CACHE / "alerts.jsonl"
    assert alerts_path.is_file()
    lines = [ln for ln in alerts_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 1
    alerts = [json.loads(ln) for ln in lines]
    assert all(a.get("simulated") is False for a in alerts)
    he = next(a for a in alerts if a["kind"] == "HE_NEUTRINO")
    assert he["alert_id"] == "IceCube-170922A"
    assert he["source"] == "gcn_kafka"
    ice = next(d for d in he["detectors"] if d["name"] == "IceCube")
    assert ice["pointing"]["ra_deg"] == pytest.approx(77.43)
    assert ice["pointing"]["dec_deg"] == pytest.approx(5.72)

    assert (CACHE / "gcn_circular_21916.txt").is_file()
    assert (CACHE / "gcn_amon_notice_50579430_130033.txt").is_file()
    readme = (CACHE / "README.md").read_text(encoding="utf-8")
    assert "https://gcn.nasa.gov/circulars/21916" in readme
    assert "https://gcn.gsfc.nasa.gov/notices_amon/50579430_130033.amon" in readme


def test_blazar_cache_contains_txs_from_catalog_not_hardcoded() -> None:
    rows = load_cached_blazars(SCENARIO)
    assert rows, "blazars.json must be populated from the one-shot SIMBAD pull"
    assert all(r.get("simulated") is False for r in rows)
    assert all(r.get("class") == "BLAZAR" for r in rows)
    ids = {r["star_id"] for r in rows}
    assert TXS_ID in ids
    # Must not be a single-row hardcoded TXS stub.
    assert len(rows) >= 2


def test_scenario_icecube_replay_top_match_txs(
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
    app = app_mod.app
    app_mod._out_root = tmp_path / "run"
    pipeline_mod.reset_watchlist()
    reset_watchlist()

    with TestClient(app) as client:
        with client.websocket_connect("/ws/events") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"

            resp = client.post(f"/scenario/{SCENARIO}/start")
            assert resp.status_code == 200

            seen: list[dict[str, Any]] = []
            got_candidates = False
            for _ in range(40):
                msg = ws.receive_json()
                seen.append(msg)
                if msg.get("type") == "candidates":
                    got_candidates = True
                    break
            assert got_candidates, f"no candidates in {[m.get('type') for m in seen]}"

    alert_events = [m for m in seen if m.get("type") == "alert"]
    assert alert_events, "expected HE_NEUTRINO alert event"
    assert alert_events[0]["payload"]["kind"] == "HE_NEUTRINO"
    assert alert_events[0]["simulated"] is False

    skymap_evt = next(m for m in seen if m["type"] == "skymap")
    assert skymap_evt["simulated"] is False
    assert "icecube_pointing" in skymap_evt["payload"]["components"]

    cand_evt = next(m for m in seen if m["type"] == "candidates")
    assert cand_evt["simulated"] is False
    candidates = cand_evt["payload"]["candidates"]
    assert candidates, "expected at least one blazar CandidateScore"
    top = candidates[0]
    assert top["star_id"] == TXS_ID
    assert top["class"] == "BLAZAR"
    assert top["breakout"]["class_window"] == "n/a"
    assert top.get("simulated") is False
    # TXS must win by sky probability among catalog matches (not hardwired rank).
    assert top["p_sky"] == max(c["p_sky"] for c in candidates)
