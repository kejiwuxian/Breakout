"""Community notify: two-token subscribe + ranked-candidate email dispatch."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.notify import dispatch as dispatch_mod
from backend.notify import subscribers as subs_mod
from backend.notify.payload import build_community_alert
from backend.notify.subscribers import (
    clear_rate_limits,
    clear_subscribers,
    confirm_subscribe,
    list_subscribers,
    request_subscribe,
)
from backend.schemas import Alert, CandidateScore, DetectorHit, SkyMap, SkyPeak


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg = tmp_path / "registry.json"
    feed = tmp_path / "alert_feed.jsonl"
    monkeypatch.setattr(subs_mod, "REGISTRY_DIR", tmp_path)
    monkeypatch.setattr(subs_mod, "REGISTRY_PATH", reg)
    monkeypatch.setattr(dispatch_mod, "FEED_PATH", feed)
    clear_subscribers()
    clear_rate_limits()


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


def test_request_confirm_activates_and_hashes_tokens() -> None:
    pending = request_subscribe(
        email="Obs@Example.EDU",
        label="campus-0.3m",
        dry_run=True,
        smtp_configured=False,
    )
    assert pending["pending"] is True
    assert "request_id" in pending
    assert "dry_run" in pending
    rt = pending["dry_run"]["request_token"]
    ct = pending["dry_run"]["confirm_token"]

    raw = json.loads(subs_mod.REGISTRY_PATH.read_text(encoding="utf-8"))
    assert raw[0]["status"] == "pending"
    assert raw[0]["email"] == "obs@example.edu"
    assert raw[0]["request_token_hash"] != rt
    assert raw[0]["confirm_token_hash"] != ct
    assert "webhook_url" not in raw[0]

    # Pending must not appear in the public active list.
    assert list_subscribers(public=True, active_only=True) == []

    confirmed = confirm_subscribe(request_token=rt, confirm_token=ct)
    assert confirmed["status"] == "active"
    assert confirmed["access_token"]
    assert confirmed["subscriber"]["email_masked"].startswith("o***@")

    active = list_subscribers(public=True, active_only=True)
    assert len(active) == 1
    assert active[0]["email_masked"] == "o***@example.edu"
    assert "access_token" not in active[0]

    # Tokens are one-time.
    with pytest.raises(ValueError, match="invalid|already-used"):
        confirm_subscribe(request_token=rt, confirm_token=ct)


def test_confirm_rejects_bad_and_expired_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    pending = request_subscribe(email="a@example.edu", dry_run=True)
    rt = pending["dry_run"]["request_token"]
    ct = pending["dry_run"]["confirm_token"]

    with pytest.raises(ValueError, match="invalid"):
        confirm_subscribe(request_token=rt, confirm_token="wrong-token")

    # Expire the pending row
    rows = json.loads(subs_mod.REGISTRY_PATH.read_text(encoding="utf-8"))
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0)
    rows[0]["expires_utc"] = past.isoformat().replace("+00:00", "Z")
    subs_mod.REGISTRY_PATH.write_text(json.dumps(rows), encoding="utf-8")

    with pytest.raises(ValueError, match="expired|invalid"):
        confirm_subscribe(request_token=rt, confirm_token=ct)


def test_pending_not_dispatched_webhook_gone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import config as config_mod
    from backend.notify.dispatch import dispatch_ranked_alert

    monkeypatch.setattr(config_mod.settings, "notify_dry_run", True)

    pending = request_subscribe(email="pending@example.edu", dry_run=True)
    assert pending["pending"] is True

    # Confirm a different subscriber so dispatch has someone to email.
    ok = request_subscribe(email="active@example.edu", label="scope", dry_run=True)
    confirm_subscribe(
        request_token=ok["dry_run"]["request_token"],
        confirm_token=ok["dry_run"]["confirm_token"],
    )

    result = dispatch_ranked_alert(
        _toy_alert(),
        _toy_skymap(),
        [_toy_score()],
        run_dir=tmp_path,
    )
    disp = result["dispatch"]
    assert disp["n_subscribers"] == 1
    assert disp["channels"] == ["email"]
    assert "webhook" not in disp["deliveries"][0]
    assert disp["deliveries"][0]["email"]["dry_run"] is True
    assert (tmp_path / "notify-test-1" / "community_alert.json").is_file()


def test_rate_limit_by_email() -> None:
    clear_rate_limits()
    for i in range(subs_mod.RATE_LIMIT_MAX_PER_KEY):
        request_subscribe(email=f"r{i}@example.edu", client_ip="10.0.0.1", dry_run=True)
    with pytest.raises(ValueError, match="rate limit"):
        request_subscribe(email="extra@example.edu", client_ip="10.0.0.1", dry_run=True)


def test_subscribe_api_two_token_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    monkeypatch.setenv("NOTIFY_DRY_RUN", "True")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    import importlib

    import backend.app as app_mod

    importlib.reload(app_mod)

    with TestClient(app_mod.app) as client:
        bad = client.post("/subscribe/request", json={})
        assert bad.status_code == 422

        # Legacy webhook field must not create a webhook subscriber.
        legacy_webhook = client.post(
            "/subscribe",
            json={"webhook_url": "https://hooks.example.edu/a", "label": "x"},
        )
        assert legacy_webhook.status_code == 422

        req = client.post(
            "/subscribe/request",
            json={"email": "scope@example.edu", "label": "campus"},
        )
        assert req.status_code == 200
        body = req.json()
        assert body["pending"] is True
        assert "dry_run" in body
        assert body["dry_run"]["request_token"]
        assert body["dry_run"]["confirm_token"]
        # Secrets must not be echoed at top level outside dry_run.
        assert "request_token" not in body
        assert "confirm_token" not in body

        listed_pending = client.get("/subscribe")
        assert listed_pending.status_code == 200
        assert listed_pending.json()["subscribers"] == []

        conf = client.post(
            "/subscribe/confirm",
            json={
                "request_token": body["dry_run"]["request_token"],
                "confirm_token": body["dry_run"]["confirm_token"],
            },
        )
        assert conf.status_code == 200
        conf_body = conf.json()
        assert conf_body["status"] == "active"
        access = conf_body["access_token"]
        sid = conf_body["subscriber"]["id"]

        listed = client.get("/subscribe")
        assert any(r["id"] == sid for r in listed.json()["subscribers"])
        assert listed.json()["subscribers"][0]["email_masked"].endswith("@example.edu")

        reuse = client.post(
            "/subscribe/confirm",
            json={
                "request_token": body["dry_run"]["request_token"],
                "confirm_token": body["dry_run"]["confirm_token"],
            },
        )
        assert reuse.status_code == 400

        latest = client.get("/alerts/latest")
        assert latest.status_code == 200
        assert "packages" in latest.json()

        latest_auth = client.get(f"/alerts/latest?token={access}")
        assert latest_auth.status_code == 200

        bad_tok = client.get("/alerts/latest?token=not-a-real-token")
        assert bad_tok.status_code == 401

        gone = client.delete(f"/subscribe/{sid}")
        assert gone.status_code == 200
