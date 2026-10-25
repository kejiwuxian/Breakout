"""Scenario A: Betelgeuse PRESN → SN_BURST through the full core loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.candidates.catalog import CURATED_PATH, load_curated_stars
from backend.config import ROOT
from backend.literature.build_index import INDEX_PATH, seed_betelgeuse_index
from backend.pipeline import reset_watchlist


SCENARIO = "scenario_a_galactic_ccsn"
BETELGEUSE_ID = "* alf Ori"


@pytest.fixture(scope="module")
def betelgeuse_row() -> dict[str, Any]:
    rows = load_curated_stars()
    match = [r for r in rows if r.get("star_id") == BETELGEUSE_ID]
    assert match, f"{BETELGEUSE_ID} missing from {CURATED_PATH}"
    row = match[0]
    assert row.get("class") == "RSG"
    assert row.get("distance_kpc") is not None
    assert row.get("ra_deg") is not None and row.get("dec_deg") is not None
    return row


@pytest.fixture(scope="module")
def index_bibcodes() -> set[str]:
    if not INDEX_PATH.is_file():
        seed_betelgeuse_index()
    import pandas as pd

    df = pd.read_parquet(INDEX_PATH)
    row = df.loc[df["star_id"] == BETELGEUSE_ID].iloc[0]
    evidence = json.loads(row["evidence_json"])
    bibs = {str(e["bibcode"]) for e in evidence if e.get("bibcode")}
    assert bibs, "index.parquet must carry ADS bibcodes for Betelgeuse"
    return bibs


def test_scenario_alerts_are_simulated_presn_then_burst(betelgeuse_row: dict[str, Any]) -> None:
    path = ROOT / "data" / "cache" / SCENARIO / "alerts.jsonl"
    assert path.is_file()
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 2
    alerts = [json.loads(ln) for ln in lines]
    assert all(a.get("simulated") is True for a in alerts)
    kinds = [a["kind"] for a in alerts]
    assert kinds[0] == "PRESN"
    assert "SN_BURST" in kinds
    burst = next(a for a in alerts if a["kind"] == "SN_BURST")
    assert burst["raw"]["ra_deg"] == pytest.approx(float(betelgeuse_row["ra_deg"]))
    assert burst["raw"]["dec_deg"] == pytest.approx(float(betelgeuse_row["dec_deg"]))
    assert burst["raw"]["distance_kpc"] == pytest.approx(float(betelgeuse_row["distance_kpc"]))


def test_scenario_betelgeuse_full_loop_top_candidate(
    betelgeuse_row: dict[str, Any],
    index_bibcodes: set[str],
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

    # Ensure literature index is present for evidence assertions.
    if not INDEX_PATH.is_file():
        seed_betelgeuse_index()

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
            assert got_candidates, f"no candidates event in { [m.get('type') for m in seen] }"

    alert_events = [m for m in seen if m.get("type") == "alert"]
    assert len(alert_events) >= 2
    assert alert_events[0]["payload"]["kind"] == "PRESN"
    assert alert_events[0]["simulated"] is True
    assert any(a["payload"]["kind"] == "SN_BURST" for a in alert_events)

    cand_evt = next(m for m in seen if m["type"] == "candidates")
    assert cand_evt["simulated"] is True
    candidates = cand_evt["payload"]["candidates"]
    assert candidates, "expected at least one CandidateScore"
    top = candidates[0]
    assert top["star_id"] == BETELGEUSE_ID
    assert top["presn_watch"] is True
    assert top["class"] == "RSG"
    assert top["breakout"]["class_window"] == "about 1 day"
    assert top.get("simulated") is True

    evidence = top["lit"]["evidence"]
    assert evidence, "Betelgeuse must carry literature evidence from index.parquet"
    bibs = {e["bibcode"] for e in evidence}
    assert bibs <= index_bibcodes
    assert bibs & index_bibcodes
    # Every claim must have a real ADS bibcode from the index (never invented).
    for item in evidence:
        assert item["bibcode"] in index_bibcodes
        assert item["claim"]
