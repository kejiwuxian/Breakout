"""Tests for offline literature build_index (recorded responses)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.literature.build_index import (
    build_index,
    star_id_slug,
    validate_literature,
)
from backend.schemas import Literature

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "literature"


def test_star_id_slug_filesystem_safe() -> None:
    assert star_id_slug("* alf Ori") == "alf_Ori"
    assert "/" not in star_id_slug("foo/bar")


def test_validate_literature_drops_unknown_bibcodes() -> None:
    lit = validate_literature(
        {
            "mass_loss": 0.4,
            "variability": 0.5,
            "evolved_stage": 0.6,
            "confidence": 0.7,
            "evidence": [
                {"bibcode": "2020ApJ...902...63J", "claim": "distance 168 pc from Joyce+2020"},
                {"bibcode": "2099ApJ...999...99Z", "claim": "invented citation"},
            ],
        },
        allowed_bibcodes={"2020ApJ...902...63J"},
    )
    assert isinstance(lit, Literature)
    assert [e.bibcode for e in lit.evidence] == ["2020ApJ...902...63J"]
    assert lit.confidence == pytest.approx(0.7)


def test_validate_literature_insufficient_when_all_unknown() -> None:
    lit = validate_literature(
        {
            "mass_loss": 0.9,
            "variability": 0.9,
            "evolved_stage": 0.9,
            "confidence": 0.9,
            "evidence": [
                {"bibcode": "NOT_REAL", "claim": "should vanish"},
            ],
        },
        allowed_bibcodes={"2020ApJ...902...63J"},
    )
    # No inventing scores when evidence collapses — zeros + empty evidence.
    assert lit.evidence == []
    assert lit.mass_loss == 0.0
    assert lit.confidence == 0.0


def test_validate_literature_schema_enforced() -> None:
    with pytest.raises(Exception):
        validate_literature(
            {
                "mass_loss": 1.5,  # out of range
                "variability": 0.1,
                "evolved_stage": 0.1,
                "confidence": 0.1,
                "evidence": [{"bibcode": "2020ApJ...902...63J", "claim": "ok"}],
            },
            allowed_bibcodes={"2020ApJ...902...63J"},
        )


def test_build_index_replay_drops_unknown_and_writes_raw(tmp_path: Path) -> None:
    stars = [
        {
            "star_id": "test_star",
            "common_name": "Test",
            "class": "RSG",
            "spectral_type": "M1",
        }
    ]
    out = tmp_path / "index.parquet"
    raw_dir = tmp_path / "raw"
    path = build_index(
        stars,
        out_path=out,
        raw_dir=raw_dir,
        replay_dir=FIXTURES / "replay_unknown",
        resume=False,
        force=True,
        rate_limit_s=0.0,
    )
    assert path == out
    df = pd.read_parquet(out)
    row = df.loc[df["star_id"] == "test_star"].iloc[0]
    evidence = json.loads(row["evidence_json"])
    assert evidence == []
    assert float(row["confidence"]) == 0.0

    raw = json.loads((raw_dir / "test_star.json").read_text(encoding="utf-8"))
    assert "reasoning" in raw
    assert "insufficient evidence" in raw["reasoning"].lower()
    assert raw["literature"]["evidence"] == []
    # Full model payload preserved for the UI — not canned.
    assert raw.get("raw_response") is not None
    assert raw.get("content_text")


def test_build_index_replay_betelgeuse_schema_and_bibcodes(tmp_path: Path) -> None:
    stars = [
        {
            "star_id": "* alf Ori",
            "common_name": "Betelgeuse",
            "class": "RSG",
            "spectral_type": "M1-M2Ia-Iab",
        }
    ]
    out = tmp_path / "index.parquet"
    raw_dir = tmp_path / "raw"
    build_index(
        stars,
        out_path=out,
        raw_dir=raw_dir,
        replay_dir=FIXTURES,
        resume=False,
        force=True,
        rate_limit_s=0.0,
    )
    df = pd.read_parquet(out)
    row = df.loc[df["star_id"] == "* alf Ori"].iloc[0]
    evidence = json.loads(row["evidence_json"])
    bibs = {e["bibcode"] for e in evidence}
    assert "2099ApJ...999...99Z" not in bibs  # unknown dropped
    assert "2020ApJ...902...63J" in bibs
    assert "2017AJ....154...11H" in bibs
    assert "2016ApJ...819....7D" in bibs
    Literature.model_validate(
        {
            "mass_loss": float(row["mass_loss"]),
            "variability": float(row["variability"]),
            "evolved_stage": float(row["evolved_stage"]),
            "confidence": float(row["confidence"]),
            "evidence": evidence,
        }
    )

    raw = json.loads((raw_dir / "alf_Ori.json").read_text(encoding="utf-8"))
    assert raw["star_id"] == "* alf Ori"
    assert len(raw["reasoning"]) > 100  # real recorded reasoning, not a stub line
    assert "2020ApJ...902...63J" in raw["reasoning"]
    allowed = set(raw["allowed_bibcodes"])
    for ev in raw["literature"]["evidence"]:
        assert ev["bibcode"] in allowed


def test_build_index_resume_skips_existing(tmp_path: Path) -> None:
    stars = [
        {
            "star_id": "* alf Ori",
            "common_name": "Betelgeuse",
            "class": "RSG",
            "spectral_type": "M1-M2Ia-Iab",
        }
    ]
    out = tmp_path / "index.parquet"
    raw_dir = tmp_path / "raw"
    build_index(
        stars,
        out_path=out,
        raw_dir=raw_dir,
        replay_dir=FIXTURES,
        resume=True,
        force=False,
        rate_limit_s=0.0,
    )
    raw_file = raw_dir / "alf_Ori.json"
    first = raw_file.read_text(encoding="utf-8")
    # Corrupt marker — resume must not rewrite.
    raw_file.write_text(first.replace("Betelgeuse", "MARKER_SHOULD_REMAIN"), encoding="utf-8")
    build_index(
        stars,
        out_path=out,
        raw_dir=raw_dir,
        replay_dir=FIXTURES,
        resume=True,
        force=False,
        rate_limit_s=0.0,
    )
    assert "MARKER_SHOULD_REMAIN" in raw_file.read_text(encoding="utf-8")
