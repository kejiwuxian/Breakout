"""Freeze check: CandidateScore / Alert / SkyMap v1 fixtures and imports.

Tony's ranking code can `from backend.schemas import CandidateScore, ...`.
Any field change requires CONTRACT_VERSION bump + docs/schemas.md note.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.schemas import (
    CONTRACT_VERSION,
    Alert,
    Breakout,
    CandidateScore,
    Evidence,
    Literature,
    SkyMap,
    export_json_schemas,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "fixtures"
SCHEMA_DIR = ROOT / "docs" / "schemas"


def test_contract_version_is_v1() -> None:
    assert CONTRACT_VERSION == "v1"


def test_tony_can_import_contract_symbols() -> None:
    # Import surface Tony's ranking code relies on.
    assert CandidateScore.__name__ == "CandidateScore"
    assert Evidence.__name__ == "Evidence"
    assert Literature.__name__ == "Literature"
    assert Breakout.__name__ == "Breakout"
    assert Alert.__name__ == "Alert"
    assert SkyMap.__name__ == "SkyMap"


def test_skymap_fixture_validates() -> None:
    wrapper = json.loads((FIXTURES / "skymap_example.json").read_text(encoding="utf-8"))
    assert wrapper.get("simulated") is True
    assert "fixture" in wrapper.get("_note", "").lower()
    skymap = SkyMap.model_validate(wrapper["skymap"])
    assert skymap.simulated is True
    assert skymap.ordering == "NESTED"
    assert skymap.frame == "ICRS"


def test_candidate_scores_fixture_validates() -> None:
    wrapper = json.loads((FIXTURES / "candidate_scores_example.json").read_text(encoding="utf-8"))
    assert wrapper.get("simulated") is True
    assert "fixture" in wrapper.get("_note", "").lower()
    rows = [CandidateScore.model_validate(row) for row in wrapper["candidates"]]
    assert len(rows) >= 1
    row = rows[0]
    assert row.simulated is True
    assert row.class_ == "RSG"
    assert 0.0 <= row.lit.mass_loss <= 1.0
    assert 0.0 <= row.lit.confidence <= 1.0
    assert row.breakout.class_window == "about 1 day"
    # No invented citations in the fixture.
    assert row.lit.evidence == []


def test_literature_scores_are_bounded() -> None:
    with pytest.raises(Exception):
        Literature(
            mass_loss=1.5,
            variability=0.0,
            evolved_stage=0.0,
            confidence=0.0,
            evidence=[],
        )


def test_evidence_requires_bibcode() -> None:
    with pytest.raises(Exception):
        Evidence(bibcode="", claim="missing bibcode must fail")


def test_exported_json_schemas_exist_and_match() -> None:
    schemas = export_json_schemas()
    for name in ("Alert", "SkyMap", "CandidateScore"):
        path = SCHEMA_DIR / f"{name}.schema.json"
        assert path.is_file(), f"missing exported schema {path}"
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        live = schemas[name]
        assert CONTRACT_VERSION in on_disk.get("title", "")
        assert name in on_disk.get("title", "")
        # Required keys from the live model must appear on disk.
        live_props = set(live.get("properties", {}))
        disk_props = set(on_disk.get("properties", {}))
        assert live_props == disk_props, (name, live_props.symmetric_difference(disk_props))
