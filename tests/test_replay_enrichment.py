"""Replay enrichment: AOI-ranked stars get inventory-schema predictions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import ROOT
from backend.pipeline import process_sn_burst
from backend.progenitors.enrich import ENRICHMENT_PATH, load_enrichment
from backend.schemas import Alert


def _sn_burst_alert(scenario: str) -> Alert:
    path = ROOT / "data" / "cache" / scenario / "alerts.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = json.loads(line)
        blob = raw.get("alert") if isinstance(raw, dict) and "alert" in raw else raw
        if blob.get("kind") in {"SN_BURST", "HE_NEUTRINO"}:
            return Alert.model_validate(blob)
    raise AssertionError(f"no SN_BURST/HE_NEUTRINO in {scenario}")


@pytest.mark.parametrize(
    "scenario",
    ["scenario_b_icecube_170922a", "scenario_a_galactic_ccsn"],
)
def test_replay_ranked_stars_have_distinct_enrichment(scenario: str) -> None:
    assert ENRICHMENT_PATH.is_file()
    enrich = load_enrichment()
    assert len(enrich) >= 10

    scores = process_sn_burst(_sn_burst_alert(scenario))[1]
    assert len(scores) >= 5

    field = [s for s in scores if str(s.star_id).startswith("HR")]
    assert field, "expected Yale BSC5 field stars in ranked list"
    # Every field star carries published SpType + composition + life schema.
    assert all(s.spectral_type for s in field)
    assert all(s.composition for s in field)
    assert all(s.life_expectancy is not None for s in field)
    assert all(s.rank_reasoning for s in field)
    # Dwarf/giant SpTypes stay UNK / n/a — never clone Betelgeuse RSG window.
    unk = [s for s in field if s.class_ == "UNK"]
    assert unk
    assert all(s.breakout.class_window == "n/a" for s in unk)
    assert all(
        s.life_expectancy and s.life_expectancy.optical_breakout_window == "n/a"
        for s in unk
    )
    # Compositions are per-star (not cloned from the top row).
    comps = {s.composition for s in field}
    assert len(comps) >= min(3, len(field))
