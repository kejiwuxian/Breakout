"""Community notify: subscribe + ranked-candidate dispatch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.notify import dispatch as dispatch_mod
from backend.notify import subscribers as subs_mod
from backend.notify.payload import build_community_alert
from backend.notify.subscribers import add_subscriber, clear_subscribers
from backend.schemas import Alert, CandidateScore, DetectorHit, SkyMap, SkyPeak


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg = tmp_path / "registry.json"
    feed = tmp_path / "alert_feed.jsonl"
    monkeypatch.setattr(subs_mod, "REGISTRY_DIR", tmp_path)
    monkeypatch.setattr(subs_mod, "REGISTRY_PATH", reg)
    monkeypatch.setattr(dispatch_mod, "FEED_PATH", feed)
    clear_subscribers()


def _toy_alert() -> Alert:
    return Alert(
        alert_id="notify-test-1",
        kind="SN_BURST",
        source="cache",
        simulated=True,
        t0_utc="2020-01-01T00:00:00",
        detectors=[
            DetectorHit(
                name="Super-K",
                lat_deg=36.4,
                lon_deg=137.3,
                height_m=370.0,
                t_arrival_utc="2020-01-01T00:00:00",
                t_err_ms=1.0,
                n_events=10,
                pointing=None,
            )
        ],
        significance=3.0,
        raw={},
    )


def _toy_skymap() -> SkyMap:
    return SkyMap(
        alert_id="notify-test-1",
        nside=64,
        prob_path="unused.fits",
        components=["timing:test"],
        credible_90_deg2=100.0,
        peak=SkyPeak(ra_deg=88.79, dec_deg=7.41),
        simulated=True,
    )


def _toy_score() -> CandidateScore:
    return CandidateScore.model_validate(
        {
            "star_id": "* alf Ori",
            "ra_deg": 88.7929,
            "dec_deg": 7.4071,
            "class": "RSG",
            "spectral_type": "M2 I",
            "distance_kpc": 0.168,
            "extinction_av_mag": 0.62,
            "p_sky": 0.05,
            "lit": {
                "mass_loss": 0.8,
                "variability": 0.8,
                "evolved_stage": 0.9,
                "confidence": 0.7,
                "evidence": [
                    {
                        "bibcode": "2020ApJ...902...63J",
                        "claim": "Joyce et al. distance for Betelgeuse.",
                    }
                ],
            },
            "presn_watch": False,
            "posterior": 0.4,
            "breakout": {
                "class_window": "about 1 day",
                "countdown_from": "2020-01-01T00:00:00",
            },
            "ir_followup": False,
            "simulated": True,
        }
    )


def test_build_community_alert_labels_simulated() -> None:
    pkg = build_community_alert(_toy_alert(), _toy_skymap(), [_toy_score()])
    assert pkg["schema"].startswith("breakout.community_alert")
    assert pkg["simulated"] is True
    assert pkg["candidates"][0]["ra_deg"] == pytest.approx(88.7929)
    assert pkg["candidates"][0]["evidence"][0]["bibcode"] == "2020ApJ...902...63J"
    assert pkg["candidates"][0]["simulated"] is True


def test_subscribe_and_dispatch_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import config as config_mod
    from backend.notify.dispatch import dispatch_ranked_alert

    monkeypatch.setattr(config_mod.settings, "notify_dry_run", True)
    sub = add_subscriber(
        webhook_url="https://hooks.example.edu/breakout",
        email="obs@example.edu",
        label="campus-0.3m",
    )
    assert sub["has_webhook"] is True

    result = dispatch_ranked_alert(
        _toy_alert(),
        _toy_skymap(),
        [_toy_score()],
        run_dir=tmp_path,
    )
    disp = result["dispatch"]
    assert disp["n_subscribers"] == 1
    assert disp["dry_run"] is True
    assert disp["deliveries"][0]["webhook"]["dry_run"] is True
    assert (tmp_path / "notify-test-1" / "community_alert.json").is_file()
    feed = json.loads(dispatch_mod.FEED_PATH.read_text(encoding="utf-8").splitlines()[0])
    assert feed["alert_id"] == "notify-test-1"


def test_subscribe_api_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    import importlib

    import backend.app as app_mod

    importlib.reload(app_mod)

    with TestClient(app_mod.app) as client:
        bad = client.post("/subscribe", json={})
        assert bad.status_code == 400
        ok = client.post(
            "/subscribe",
            json={
                "webhook_url": "https://hooks.example.edu/a",
                "label": "test",
            },
        )
        assert ok.status_code == 200
        sid = ok.json()["subscriber"]["id"]
        listed = client.get("/subscribe")
        assert listed.status_code == 200
        assert any(r["id"] == sid for r in listed.json()["subscribers"])
        latest = client.get("/alerts/latest")
        assert latest.status_code == 200
        assert "packages" in latest.json()
        gone = client.delete(f"/subscribe/{sid}")
        assert gone.status_code == 200
