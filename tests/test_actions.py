"""Action builders: LCOGT dry-run, ToO drafts, GCN Circular draft."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from backend.actions.gcn_circular import draft_circular
from backend.actions.lcogt import (
    FILTERS_IR,
    FILTERS_OPTICAL,
    build_and_maybe_submit,
    build_request_group,
)
from backend.actions.too_drafts import draft_hst_too, draft_jwst_too
from backend.candidates.catalog import CURATED_PATH, load_curated_stars
from backend.config import ROOT
from backend.literature.build_index import INDEX_PATH, seed_betelgeuse_index
from backend.pipeline import reset_watchlist
from backend.schemas import (
    Alert,
    Breakout,
    CandidateScore,
    Evidence,
    Literature,
    SkyMap,
    SkyPeak,
)


SCENARIO = "scenario_a_galactic_ccsn"
BETELGEUSE_ID = "* alf Ori"


def _fixture_candidate(*, ir_followup: bool = False, simulated: bool = True) -> CandidateScore:
    return CandidateScore(
        star_id=BETELGEUSE_ID,
        ra_deg=88.792939,
        dec_deg=7.407064,
        class_="RSG",
        spectral_type="M2 I",
        distance_kpc=0.222,
        extinction_av_mag=0.62,
        p_sky=0.01,
        lit=Literature(
            mass_loss=0.0,
            variability=0.0,
            evolved_stage=0.0,
            confidence=0.0,
            evidence=[
                Evidence(
                    bibcode="2017AJ....154...11H",
                    claim="Harper et al. 2017 distance solution for Betelgeuse.",
                )
            ],
        ),
        presn_watch=True,
        posterior=0.5,
        breakout=Breakout(class_window="about 1 day", countdown_from="2026-10-24T21:46:00Z"),
        ir_followup=ir_followup,
        simulated=simulated,
    )


def _fixture_skymap(*, simulated: bool = True) -> SkyMap:
    return SkyMap(
        alert_id="sim-burst-test",
        nside=64,
        prob_path="data/run/sim-burst-test/skymap.fits",
        components=["superk_pointing"],
        credible_90_deg2=12.0,
        peak=SkyPeak(ra_deg=88.792939, dec_deg=7.407064),
        simulated=simulated,
    )


def _fixture_alert(*, simulated: bool = True) -> Alert:
    return Alert(
        alert_id="sim-burst-test",
        kind="SN_BURST",
        source="snewpy_sim",
        simulated=simulated,
        t0_utc="2026-10-24T21:46:00Z",
        detectors=[],
        significance=0.0,
        raw={"ra_deg": 88.792939, "dec_deg": 7.407064, "distance_kpc": 0.222},
    )


def test_lcogt_request_group_targets_candidate_and_filters() -> None:
    cand = _fixture_candidate(ir_followup=False)
    rg = build_request_group(cand, proposal="TESTPROP", dry_run=True, alert_id="sim-burst-test")
    assert rg["observation_type"] == "RAPID_RESPONSE"
    assert rg["operator"] == "SINGLE"
    assert rg["proposal"] == "TESTPROP"
    assert rg["simulated"] is True
    assert rg["breakout"]["dry_run"] is True
    req = rg["requests"][0]
    assert len(req["configurations"]) == len(FILTERS_OPTICAL)
    target = req["configurations"][0]["target"]
    assert target["ra"] == pytest.approx(cand.ra_deg)
    assert target["dec"] == pytest.approx(cand.dec_deg)
    filters = [c["instrument_configs"][0]["optical_elements"]["filter"] for c in req["configurations"]]
    assert tuple(filters) == FILTERS_OPTICAL

    ir = build_request_group(
        _fixture_candidate(ir_followup=True),
        proposal="TESTPROP",
        dry_run=True,
    )
    ir_filters = [
        c["instrument_configs"][0]["optical_elements"]["filter"]
        for c in ir["requests"][0]["configurations"]
    ]
    assert tuple(ir_filters) == FILTERS_IR


def test_lcogt_dry_run_writes_json_and_makes_no_network_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LCOGT_DRY_RUN", "True")
    monkeypatch.setenv("LCOGT_PROPOSAL", "DRYPROP")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    cand = _fixture_candidate()
    with mock.patch("urllib.request.urlopen") as urlopen:
        result = build_and_maybe_submit(
            cand,
            alert_id="sim-burst-test",
            run_dir=tmp_path,
            dry_run=True,
        )
        urlopen.assert_not_called()
    assert result["dry_run"] is True
    assert result["submitted"] is False
    path = Path(result["path"])
    assert path.is_file()
    assert path.name == "lcogt_request.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["observation_type"] == "RAPID_RESPONSE"
    assert written["proposal"] == "DRYPROP"


def test_too_drafts_valid_for_betelgeuse() -> None:
    cand = _fixture_candidate()
    skymap = _fixture_skymap()
    hst = draft_hst_too(cand, skymap)
    jwst = draft_jwst_too(cand, skymap)
    assert "DRAFT for human review" in hst
    assert BETELGEUSE_ID in hst
    assert "2017AJ....154...11H" in hst
    assert "DRAFT for human review" in jwst
    assert "very bright" in jwst.lower()
    assert BETELGEUSE_ID in jwst
    assert "[simulated]" in hst
    assert "[simulated]" in jwst


def test_gcn_circular_carries_draft_header_and_bibcodes() -> None:
    text = draft_circular(_fixture_alert(), _fixture_skymap(), [_fixture_candidate()])
    assert text.lstrip().startswith("# DRAFT for human review")
    assert "DRAFT for human review" in text
    assert "2017AJ....154...11H" in text
    assert "(simulated)" in text
    assert BETELGEUSE_ID in text


def test_betelgeuse_run_emits_actions_with_three_drafts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    monkeypatch.setenv("SCENARIO", SCENARIO)
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")
    monkeypatch.setenv("LCOGT_DRY_RUN", "True")
    monkeypatch.setenv("LCOGT_PROPOSAL", "BREAKOUT-TEST")

    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    assert config_mod.settings.lcogt_dry_run is True

    import importlib

    import backend.app as app_mod
    import backend.pipeline as pipeline_mod

    importlib.reload(app_mod)
    app = app_mod.app
    app_mod._out_root = tmp_path / "run"
    pipeline_mod.reset_watchlist()
    reset_watchlist()

    if not INDEX_PATH.is_file():
        seed_betelgeuse_index()
    assert CURATED_PATH.is_file()
    assert any(r.get("star_id") == BETELGEUSE_ID for r in load_curated_stars())

    with mock.patch("urllib.request.urlopen") as urlopen:
        with TestClient(app) as client:
            with client.websocket_connect("/ws/events") as ws:
                hello = ws.receive_json()
                assert hello["type"] == "hello"

                resp = client.post(f"/scenario/{SCENARIO}/start")
                assert resp.status_code == 200

                seen: list[dict[str, Any]] = []
                actions_evt: dict[str, Any] | None = None
                for _ in range(120):
                    msg = ws.receive_json()
                    seen.append(msg)
                    if msg.get("type") == "actions" and msg.get("payload", {}).get(
                        "gcn_circular_markdown"
                    ):
                        actions_evt = msg
                        break
                assert actions_evt is not None, (
                    f"no actions drafts in {[m.get('type') for m in seen]}"
                )
        urlopen.assert_not_called()

    payload = actions_evt["payload"]
    assert payload["lcogt_dry_run"] is True
    assert payload["top_star_id"] == BETELGEUSE_ID
    assert payload["lcogt"] is not None
    assert payload["lcogt"]["dry_run"] is True
    assert payload["lcogt"]["submitted"] is False
    rg = payload["lcogt"]["request_group"]
    assert rg["observation_type"] == "RAPID_RESPONSE"
    assert rg["operator"] == "SINGLE"
    assert rg["proposal"] == "BREAKOUT-TEST"

    hst = payload["too_hst_markdown"]
    jwst = payload["too_jwst_markdown"]
    gcn = payload["gcn_circular_markdown"]
    assert isinstance(hst, str) and "DRAFT for human review" in hst
    assert isinstance(jwst, str) and "very bright" in jwst.lower()
    assert isinstance(gcn, str) and gcn.lstrip().startswith("# DRAFT for human review")

    # Dry-run artifact on disk for the SN_BURST alert.
    written = list((tmp_path / "run").glob("*/lcogt_request.json"))
    assert written, "expected lcogt_request.json under data/run/<alert_id>/"
    disk = json.loads(written[0].read_text(encoding="utf-8"))
    assert disk["observation_type"] == "RAPID_RESPONSE"
