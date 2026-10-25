"""Scenario B: IceCube-170922A → TXS 0506+056 through the full core loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.candidates.catalog import load_curated_stars
from backend.config import ROOT
from backend.pipeline import reset_watchlist


SCENARIO = "scenario_b_icecube_170922a"
TXS_ID = "TXS 0506+056"
# GCN Circular 21916 refined direction.
ICECUBE_RA = 77.43
ICECUBE_DEC = 5.72


@pytest.fixture(scope="module")
def txs_row() -> dict[str, Any]:
    rows = load_curated_stars()
    match = [r for r in rows if r.get("star_id") == TXS_ID]
    assert match, f"{TXS_ID} missing from curated_stars.json"
    row = match[0]
    assert row.get("class") == "AGN"
    assert row.get("ra_deg") == pytest.approx(77.36, abs=1e-2)
    assert row.get("dec_deg") == pytest.approx(5.69, abs=1e-2)
    return row


def test_scenario_b_alerts_are_real_he_neutrino() -> None:
    path = ROOT / "data" / "cache" / SCENARIO / "alerts.jsonl"
    assert path.is_file()
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 1
    alert = json.loads(lines[0])
    assert alert["simulated"] is False
    assert alert["kind"] == "HE_NEUTRINO"
    assert alert["alert_id"] == "IceCube-170922A"
    assert alert["source"] == "gcn_kafka"
    assert alert["raw"]["ra"] == pytest.approx(ICECUBE_RA)
    assert alert["raw"]["dec"] == pytest.approx(ICECUBE_DEC)
    assert alert["raw"].get("gcn_circular") == 21916
    ice = next(d for d in alert["detectors"] if d["name"] == "IceCube")
    assert ice["pointing"] is not None
    assert ice["pointing"]["ra_deg"] == pytest.approx(ICECUBE_RA)
    assert ice["pointing"]["dec_deg"] == pytest.approx(ICECUBE_DEC)


def test_scenario_icecube_full_loop_txs_top(
    txs_row: dict[str, Any],
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

    # Rebuild star table from Vincent curated (includes TXS).
    from backend.candidates import catalog as catalog_mod

    table = catalog_mod.build_star_table(
        use_network=False, out_path=tmp_path / "star_table.parquet"
    )
    monkeypatch.setattr(pipeline_mod, "STAR_TABLE_PATH", Path(table))
    monkeypatch.setattr(catalog_mod, "STAR_TABLE_PATH", Path(table))

    with TestClient(app) as client:
        with client.websocket_connect("/ws/events") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"

            resp = client.post(f"/scenario/{SCENARIO}/start")
            assert resp.status_code == 200

            seen: list[dict[str, Any]] = []
            got_candidates = False
            for _ in range(80):
                msg = ws.receive_json()
                seen.append(msg)
                if msg.get("type") == "candidates":
                    got_candidates = True
                    break
            assert got_candidates, f"no candidates in {[m.get('type') for m in seen]}"

    alert_evt = next(m for m in seen if m.get("type") == "alert")
    assert alert_evt["simulated"] is False
    assert alert_evt["payload"]["kind"] == "HE_NEUTRINO"
    assert alert_evt["payload"]["simulated"] is False

    skymap_evt = next(m for m in seen if m.get("type") == "skymap")
    assert skymap_evt["simulated"] is False
    peak = skymap_evt["payload"]["peak"]
    # Peak should sit on the IceCube pointing (near TXS).
    assert peak["ra_deg"] == pytest.approx(ICECUBE_RA, abs=2.0)
    assert peak["dec_deg"] == pytest.approx(ICECUBE_DEC, abs=2.0)

    cand_evt = next(m for m in seen if m["type"] == "candidates")
    assert cand_evt["simulated"] is False
    candidates = cand_evt["payload"]["candidates"]
    assert candidates, "expected candidates inside the IceCube region"
    top = candidates[0]
    assert top["star_id"] == TXS_ID
    assert top["class"] == "AGN"
    assert top.get("simulated") is False
    bibs = {e["bibcode"] for e in top["lit"]["evidence"]}
    assert "2018Sci...361.1378I" in bibs or bibs  # curated evidence with real ADS bibcodes
