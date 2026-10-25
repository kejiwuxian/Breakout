"""Community notify: access + refresh tokens over WebSocket subscribe."""

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
    issue_tokens,
    list_subscribers,
    refresh_access_token,
    verify_access_token,
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


def test_issue_and_refresh_access_refresh_tokens() -> None:
    issued = issue_tokens(email="Obs@Example.EDU", label="campus-0.3m")
    assert issued["status"] == "active"
    assert issued["access_token"]
    assert issued["refresh_token"]
    assert issued["access_token"] != issued["refresh_token"]
    assert issued["subscriber"]["email_masked"].startswith("o***@")

    raw = json.loads(subs_mod.REGISTRY_PATH.read_text(encoding="utf-8"))
    assert raw[0]["status"] == "active"
    assert raw[0]["email"] == "obs@example.edu"
    assert raw[0]["access_token_hash"] != issued["access_token"]
    assert raw[0]["refresh_token_hash"] != issued["refresh_token"]
    assert "webhook_url" not in raw[0]

    assert verify_access_token(issued["access_token"]) is not None
    assert verify_access_token(issued["refresh_token"]) is None

    active = list_subscribers(public=True, active_only=True)
    assert len(active) == 1
    assert "access_token" not in active[0]
    assert "refresh_token" not in active[0]

    refreshed = refresh_access_token(refresh_token=issued["refresh_token"])
    assert refreshed["access_token"] != issued["access_token"]
    assert refreshed["refresh_token"] != issued["refresh_token"]
    # Old access invalidated by rotation of hashes.
    assert verify_access_token(issued["access_token"]) is None
    assert verify_access_token(refreshed["access_token"]) is not None

    # Old refresh cannot be reused.
    with pytest.raises(ValueError, match="invalid"):
        refresh_access_token(refresh_token=issued["refresh_token"])


def test_access_token_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subs_mod, "ACCESS_TTL", timedelta(seconds=1))
    issued = issue_tokens(email="a@example.edu")
    assert verify_access_token(issued["access_token"]) is not None

    # Force expiry on the stored row.
    rows = json.loads(subs_mod.REGISTRY_PATH.read_text(encoding="utf-8"))
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(microsecond=0)
    rows[0]["access_expires_utc"] = past.isoformat().replace("+00:00", "Z")
    subs_mod.REGISTRY_PATH.write_text(json.dumps(rows), encoding="utf-8")
    assert verify_access_token(issued["access_token"]) is None


def test_dispatch_marks_websocket_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import config as config_mod
    from backend.notify.dispatch import dispatch_ranked_alert

    monkeypatch.setattr(config_mod.settings, "notify_dry_run", True)
    issue_tokens(email="active@example.edu", label="scope")

    result = dispatch_ranked_alert(
        _toy_alert(),
        _toy_skymap(),
        [_toy_score()],
        run_dir=tmp_path,
    )
    disp = result["dispatch"]
    assert "websocket" in disp["channels"]
    assert any(d.get("channel") == "websocket" for d in disp["deliveries"])
    assert (tmp_path / "notify-test-1" / "community_alert.json").is_file()


def test_rate_limit_by_ip() -> None:
    clear_rate_limits()
    for i in range(subs_mod.RATE_LIMIT_MAX_PER_KEY):
        issue_tokens(email=f"r{i}@example.edu", client_ip="10.0.0.1")
    with pytest.raises(ValueError, match="rate limit"):
        issue_tokens(email="extra@example.edu", client_ip="10.0.0.1")


def test_subscribe_api_access_refresh_and_ws(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    monkeypatch.setenv("NOTIFY_DRY_RUN", "True")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    import importlib

    import backend.app as app_mod

    importlib.reload(app_mod)

    with TestClient(app_mod.app) as client:
        issued = client.post(
            "/subscribe",
            json={"email": "scope@example.edu", "label": "campus"},
        )
        assert issued.status_code == 200
        body = issued.json()
        assert body["status"] == "active"
        access = body["access_token"]
        refresh = body["refresh_token"]
        sid = body["subscriber"]["id"]
        assert body["ws"] == "/ws/subscribe"

        listed = client.get("/subscribe")
        assert listed.status_code == 200
        assert any(r["id"] == sid for r in listed.json()["subscribers"])
        assert listed.json()["ws"] == "/ws/subscribe"

        bad_refresh = client.post("/subscribe/refresh", json={"refresh_token": "nope"})
        assert bad_refresh.status_code == 401

        refreshed = client.post("/subscribe/refresh", json={"refresh_token": refresh})
        assert refreshed.status_code == 200
        new_access = refreshed.json()["access_token"]
        assert new_access != access

        latest = client.get("/alerts/latest")
        assert latest.status_code == 200
        assert latest.json()["ws"] == "/ws/subscribe"

        latest_auth = client.get(f"/alerts/latest?token={new_access}")
        assert latest_auth.status_code == 200

        bad_tok = client.get("/alerts/latest?token=not-a-real-token")
        assert bad_tok.status_code == 401

        with client.websocket_connect(f"/ws/subscribe?access_token={new_access}") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "subscribe_hello"
            assert hello["subscriber_id"] == sid
            assert "access_expires_utc" in hello
            ws.send_text("ping")
            assert ws.receive_json()["type"] == "pong"

            # Extend with a freshly refreshed access token.
            again = client.post(
                "/subscribe/refresh",
                json={"refresh_token": refreshed.json()["refresh_token"]},
            )
            assert again.status_code == 200
            ext = again.json()["access_token"]
            ws.send_json({"type": "access_token", "access_token": ext})
            extended = ws.receive_json()
            assert extended["type"] == "access_extended"
            assert extended["subscriber_id"] == sid

        gone = client.delete(f"/subscribe/{sid}")
        assert gone.status_code == 200


def test_ws_subscribe_rejects_bad_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BREAKOUT_DISABLE_AUTOSTART", "1")
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    import importlib

    import backend.app as app_mod

    importlib.reload(app_mod)

    with TestClient(app_mod.app) as client:
        with client.websocket_connect("/ws/subscribe?access_token=bad") as ws:
            # Accepted then closed with application code 4003.
            with pytest.raises(Exception):
                ws.receive_json()
