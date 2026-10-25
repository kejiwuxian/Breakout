"""Tests for progenitor inventory, monitor, and offline runtime ranking."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.progenitors.inventory import (
    build_inventory,
    load_inventory,
    profile_from_row,
)
from backend.progenitors.monitor import monitor_publications
from backend.progenitors.rank_runtime import rank_with_grok
from backend.schemas import CONTRACT_VERSION, CandidateScore, SkyMap, SkyPeak

T0 = "2026-10-25T10:00:00Z"
FIXTURES_LIT = Path(__file__).resolve().parent / "fixtures" / "literature"


def _skymap() -> SkyMap:
    return SkyMap(
        alert_id="prog-test",
        nside=64,
        ordering="NESTED",
        frame="ICRS",
        prob_path="data/run/prog-test/skymap.fits",
        components=["test"],
        credible_90_deg2=12.0,
        peak=SkyPeak(ra_deg=88.79, dec_deg=7.41),
        simulated=True,
    )


def test_contract_version_mentions_v1_1() -> None:
    assert CONTRACT_VERSION == "v1.1"


def test_build_inventory_from_curated(tmp_path: Path) -> None:
    out = tmp_path / "progenitor_inventory.parquet"
    path = build_inventory(out_path=out, reviewed_utc=T0)
    assert path.is_file()
    inv = load_inventory(path)
    assert len(inv) >= 10
    bet = inv.get("* alf Ori")
    assert bet is not None
    assert bet.ra_deg == pytest.approx(88.792939, abs=1e-4)
    assert bet.life_expectancy.optical_breakout_window == "about 1 day"
    assert bet.composition
    assert 0.0 <= bet.sn_potential <= 1.0
    # Betelgeuse has ADS evidence in the literature index → stage note or evidence.
    assert bet.lit.confidence >= 0.0
    assert bet.last_reviewed_utc == T0


def test_profile_never_invents_bibcodes() -> None:
    row = {
        "star_id": "TEST STAR",
        "ra_deg": 10.0,
        "dec_deg": -5.0,
        "class": "RSG",
        "spectral_type": "M2 I",
        "lit": {
            "mass_loss": 0.5,
            "variability": 0.5,
            "evolved_stage": 0.5,
            "confidence": 0.5,
            "evidence": [
                {"bibcode": "", "claim": "should drop"},
                {"bibcode": "2020ApJ...902...63J", "claim": "real claim"},
            ],
        },
    }
    profile = profile_from_row(row, reviewed_utc=T0)
    assert profile is not None
    assert len(profile.lit.evidence) == 1
    assert profile.lit.evidence[0].bibcode == "2020ApJ...902...63J"


def test_rank_with_grok_offline_enriches_and_sorts(tmp_path: Path) -> None:
    inv_path = tmp_path / "inv.parquet"
    build_inventory(out_path=inv_path, reviewed_utc=T0)

    index_path = tmp_path / "index.parquet"
    pd.DataFrame(
        [
            {
                "star_id": "* alf Ori",
                "mass_loss": 0.85,
                "variability": 0.9,
                "evolved_stage": 0.95,
                "confidence": 0.9,
                "evidence_json": json.dumps(
                    [
                        {
                            "bibcode": "2020ApJ...902...63J",
                            "claim": "Joyce et al. 2020 distance/mass for Betelgeuse.",
                        }
                    ]
                ),
                "simulated": False,
            },
            {
                "star_id": "other",
                "mass_loss": 0.1,
                "variability": 0.1,
                "evolved_stage": 0.1,
                "confidence": 0.1,
                "evidence_json": "[]",
                "simulated": False,
            },
        ]
    ).to_parquet(index_path, index=False)

    candidates = [
        {
            "star_id": "* alf Ori",
            "ra_deg": 88.79,
            "dec_deg": 7.41,
            "class": "RSG",
            "spectral_type": "M2 I",
            "distance_kpc": 0.222,
            "p_sky": 0.4,
            "simulated": True,
        },
        {
            "star_id": "other",
            "ra_deg": 90.0,
            "dec_deg": 8.0,
            "class": "RSG",
            "spectral_type": "M1",
            "distance_kpc": None,
            "p_sky": 0.2,
            "simulated": True,
        },
    ]
    scores = rank_with_grok(
        candidates,
        skymap=_skymap(),
        t0_utc=T0,
        watchlist=set(),
        inventory_path=inv_path,
        index=index_path,
        force_offline=True,
    )
    assert len(scores) == 2
    assert scores[0].star_id == "* alf Ori"
    assert sum(s.posterior for s in scores) == pytest.approx(1.0, abs=1e-9)
    top = scores[0]
    assert isinstance(top, CandidateScore)
    assert top.rank_confidence is not None
    assert top.life_expectancy is not None
    assert top.life_expectancy.optical_breakout_window == "about 1 day"
    assert top.composition
    assert top.rank_reasoning
    assert "Offline inventory" in (top.rank_reasoning or "")


def test_rank_with_grok_live_mocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv_path = tmp_path / "inv.parquet"
    build_inventory(out_path=inv_path, reviewed_utc=T0)
    candidates = [
        {
            "star_id": "a",
            "ra_deg": 1.0,
            "dec_deg": 1.0,
            "class": "RSG",
            "spectral_type": "M1",
            "p_sky": 0.5,
            "simulated": False,
        },
        {
            "star_id": "b",
            "ra_deg": 2.0,
            "dec_deg": 2.0,
            "class": "WR",
            "spectral_type": "WN",
            "p_sky": 0.4,
            "simulated": False,
        },
    ]
    index_path = tmp_path / "index.parquet"
    pd.DataFrame(
        [
            {
                "star_id": "a",
                "mass_loss": 0.2,
                "variability": 0.2,
                "evolved_stage": 0.2,
                "confidence": 0.2,
                "evidence_json": "[]",
                "simulated": False,
            },
            {
                "star_id": "b",
                "mass_loss": 0.8,
                "variability": 0.8,
                "evolved_stage": 0.8,
                "confidence": 0.8,
                "evidence_json": "[]",
                "simulated": False,
            },
        ]
    ).to_parquet(index_path, index=False)

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "rankings": [
                                        {
                                            "star_id": "b",
                                            "confidence": 0.95,
                                            "reasoning": "Higher lit confidence in shortlist.",
                                        },
                                        {
                                            "star_id": "a",
                                            "confidence": 0.2,
                                            "reasoning": "Lower lit confidence.",
                                        },
                                        {
                                            "star_id": "invented",
                                            "confidence": 1.0,
                                            "reasoning": "must be dropped",
                                        },
                                    ]
                                }
                            )
                        }
                    }
                ]
            }

    def fake_post(*_a, **_k):
        return _Resp()

    from backend.progenitors import rank_runtime as rr

    monkeypatch.setattr(rr, "_live_grok_allowed", lambda: True)
    scores = rank_with_grok(
        candidates,
        skymap=_skymap(),
        t0_utc=T0,
        inventory_path=inv_path,
        index=index_path,
        force_offline=False,
        http_post=fake_post,
    )

    assert [s.star_id for s in scores] == ["b", "a"]
    assert scores[0].rank_confidence == pytest.approx(0.95)
    assert "invented" not in {s.star_id for s in scores}
    assert "Higher lit" in (scores[0].rank_reasoning or "")


def test_monitor_replay_dry_run(tmp_path: Path) -> None:
    inv = tmp_path / "inv.parquet"
    build_inventory(out_path=inv, reviewed_utc=T0)
    wm = tmp_path / "wm.json"
    result = monitor_publications(
        inventory_path=inv,
        watermark_path=wm,
        replay_dir=FIXTURES_LIT,
        star_ids=["* alf Ori"],
        dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["live_network"] is False
    assert result["n_targets"] == 1
