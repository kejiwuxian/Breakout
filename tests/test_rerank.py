"""Tests for backend.literature.rerank: ordering, normalization, timing."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pandas as pd
import pytest

from backend.config import RANKING_CLASS_WEIGHT, RANKING_WATCH_BOOST
from backend.literature.rerank import rerank
from backend.schemas import SkyMap, SkyPeak


T0 = "2026-10-24T21:46:00Z"


def _skymap(*, simulated: bool = True) -> SkyMap:
    return SkyMap(
        alert_id="rerank-test",
        nside=64,
        ordering="NESTED",
        frame="ICRS",
        prob_path="data/run/rerank-test/skymap.fits",
        components=["test"],
        credible_90_deg2=10.0,
        peak=SkyPeak(ra_deg=88.79, dec_deg=7.41),
        simulated=simulated,
    )


def _cand(
    star_id: str,
    *,
    p_sky: float,
    cls: str = "RSG",
    av: float | None = None,
    simulated: bool = False,
) -> dict:
    return {
        "star_id": star_id,
        "ra_deg": 88.79,
        "dec_deg": 7.41,
        "class": cls,
        "spectral_type": "M1",
        "p_sky": p_sky,
        "extinction_av_mag": av,
        "distance_kpc": None,
        "simulated": simulated,
    }


def _write_index(path: Path, rows: list[dict]) -> Path:
    records = []
    for row in rows:
        records.append(
            {
                "star_id": row["star_id"],
                "mass_loss": row.get("mass_loss", 0.0),
                "variability": row.get("variability", 0.0),
                "evolved_stage": row.get("evolved_stage", 0.0),
                "confidence": row.get("confidence", 0.0),
                "evidence_json": json.dumps(row.get("evidence") or []),
                "simulated": False,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_parquet(path, index=False)
    return path


def test_rerank_ordering_and_normalization(tmp_path: Path) -> None:
    index = _write_index(
        tmp_path / "index.parquet",
        [
            {"star_id": "a", "confidence": 0.9},
            {"star_id": "b", "confidence": 0.1},
            {"star_id": "c", "confidence": 0.5},
        ],
    )
    candidates = [
        _cand("a", p_sky=0.2),
        _cand("b", p_sky=0.5),
        _cand("c", p_sky=0.3),
    ]
    scores = rerank(candidates, index, set(), t0_utc=T0, skymap=_skymap())
    assert [s.star_id for s in scores] == sorted(
        [s.star_id for s in scores],
        key=lambda sid: next(x.posterior for x in scores if x.star_id == sid),
        reverse=True,
    )
    # Explicit: posteriors sorted descending
    posts = [s.posterior for s in scores]
    assert posts == sorted(posts, reverse=True)
    assert sum(posts) == pytest.approx(1.0, abs=1e-9)
    assert all(s.breakout.countdown_from == T0 for s in scores)
    assert all(s.breakout.class_window == "about 1 day" for s in scores)  # all RSG


def test_rerank_watchlist_boost_changes_order(tmp_path: Path) -> None:
    index = _write_index(
        tmp_path / "index.parquet",
        [
            {"star_id": "low_sky_watch", "confidence": 0.5},
            {"star_id": "high_sky", "confidence": 0.5},
        ],
    )
    candidates = [
        _cand("low_sky_watch", p_sky=0.2),
        _cand("high_sky", p_sky=0.4),
    ]
    plain = rerank(candidates, index, set(), t0_utc=T0)
    assert plain[0].star_id == "high_sky"

    boosted = rerank(candidates, index, {"low_sky_watch"}, t0_utc=T0)
    assert RANKING_WATCH_BOOST > 1.0
    assert boosted[0].star_id == "low_sky_watch"
    assert boosted[0].presn_watch is True
    assert sum(s.posterior for s in boosted) == pytest.approx(1.0, abs=1e-9)


def test_rerank_class_weight_prefers_rsg_over_wr_at_equal_p_sky(tmp_path: Path) -> None:
    index = _write_index(
        tmp_path / "index.parquet",
        [
            {"star_id": "rsg", "confidence": 0.5},
            {"star_id": "wr", "confidence": 0.5},
        ],
    )
    candidates = [
        _cand("rsg", p_sky=0.3, cls="RSG"),
        _cand("wr", p_sky=0.3, cls="WR"),
    ]
    scores = rerank(candidates, index, set(), t0_utc=T0)
    assert RANKING_CLASS_WEIGHT["RSG"] > RANKING_CLASS_WEIGHT["WR"]
    assert scores[0].star_id == "rsg"
    assert scores[0].breakout.class_window == "about 1 day"
    assert scores[1].breakout.class_window == "minutes"


def test_rerank_unk_field_stars_do_not_clone_rsg_breakout(tmp_path: Path) -> None:
    """AOI BSC5/UNK rows must keep absent breakout — not RSG 'about 1 day'."""
    index = _write_index(
        tmp_path / "index.parquet",
        [
            {"star_id": "* alf Ori", "confidence": 0.9},
            {"star_id": "HR 1234", "confidence": 0.0},
            {"star_id": "HR 5678", "confidence": 0.0},
        ],
    )
    candidates = [
        _cand("* alf Ori", p_sky=0.5, cls="RSG"),
        _cand("HR 1234", p_sky=0.3, cls="UNK"),
        _cand("HR 5678", p_sky=0.2, cls="UNK"),
    ]
    scores = rerank(candidates, index, set(), t0_utc=T0)
    by_id = {s.star_id: s for s in scores}
    assert by_id["* alf Ori"].breakout.class_window == "about 1 day"
    assert by_id["HR 1234"].breakout.class_window == "n/a"
    assert by_id["HR 5678"].breakout.class_window == "n/a"
    # Inventory life is attached later; rerank itself leaves life null.
    assert by_id["HR 1234"].life_expectancy is None
    assert by_id["HR 5678"].life_expectancy is None


def test_rerank_ir_flag_from_extinction(tmp_path: Path) -> None:
    index = _write_index(tmp_path / "index.parquet", [{"star_id": "dusty", "confidence": 0.2}])
    scores = rerank(
        [_cand("dusty", p_sky=0.5, av=2.5)],
        index,
        set(),
        t0_utc=T0,
    )
    assert scores[0].ir_followup is True


def test_rerank_runtime_under_one_second(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    index = _write_index(
        tmp_path / "index.parquet",
        [{"star_id": f"s{i}", "confidence": 0.1 * (i % 10)} for i in range(50)],
    )
    candidates = [_cand(f"s{i}", p_sky=0.01 * ((i % 10) + 1)) for i in range(50)]
    caplog.set_level(logging.INFO, logger="breakout.literature.rerank")
    t0 = time.perf_counter()
    scores = rerank(candidates, index, set(), t0_utc=T0)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0
    assert len(scores) == 50
    assert sum(s.posterior for s in scores) == pytest.approx(1.0, abs=1e-8)
    assert any("rerank" in r.message and "elapsed_s=" in r.message for r in caplog.records)


def test_rerank_propagates_simulated_flag(tmp_path: Path) -> None:
    index = _write_index(tmp_path / "index.parquet", [{"star_id": "sim", "confidence": 0.0}])
    scores = rerank(
        [_cand("sim", p_sky=1.0, simulated=True)],
        index,
        set(),
        t0_utc=T0,
        skymap=_skymap(simulated=True),
    )
    assert scores[0].simulated is True


def test_rerank_accepts_in_memory_index() -> None:
    index = {
        "x": {
            "star_id": "x",
            "mass_loss": 0.1,
            "variability": 0.2,
            "evolved_stage": 0.3,
            "confidence": 1.0,
            "evidence_json": "[]",
        }
    }
    scores = rerank([_cand("x", p_sky=1.0)], index, set(), t0_utc=T0)
    assert scores[0].lit.confidence == pytest.approx(1.0)
    assert scores[0].posterior == pytest.approx(1.0)
