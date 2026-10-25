"""Tony ranking conforms to CandidateScore v1 (filter SkyMap → rerank).

Runs filter + rerank against data/fixtures/skymap_example.json and validates
every output row with ``CandidateScore``. Does not change the frozen schema.
"""

from __future__ import annotations

import json
from pathlib import Path

import healpy as hp
import numpy as np
import pytest

from backend.candidates.filter import candidates_in_region, filter_candidates
from backend.config import ROOT
from backend.literature.rerank import rerank
from backend.localize.pointing import pointing_map
from backend.schemas import CandidateScore, SkyMap, SkyPeak

FIXTURES = ROOT / "data" / "fixtures"
CURATED = ROOT / "data" / "stars" / "curated_stars.json"
T0 = "2026-10-24T21:46:00Z"


def _materialize_fixture_skymap(tmp_path: Path) -> tuple[SkyMap, np.ndarray, Path]:
    """Build a simulated NESTED FITS map for the frozen skymap fixture.

    The fixture JSON is contract metadata only — the FITS path may not exist on
    disk. We write a temporary map peaked on curated Betelgeuse so filter can
    select a real catalog row. All values remain simulated=true.
    """
    wrapper = json.loads((FIXTURES / "skymap_example.json").read_text(encoding="utf-8"))
    assert wrapper.get("simulated") is True
    skymap = SkyMap.model_validate(wrapper["skymap"])
    assert skymap.simulated is True

    curated = json.loads(CURATED.read_text(encoding="utf-8"))
    betel = next(s for s in curated if "alf Ori" in str(s.get("star_id", "")))
    ra = float(betel["ra_deg"])
    dec = float(betel["dec_deg"])

    nside = int(skymap.nside)
    prob = pointing_map(ra, dec, 5.0, nside=nside)
    assert float(prob.sum()) == pytest.approx(1.0, abs=1e-6)

    fits_dir = tmp_path / "fixture-skymap-v1"
    fits_dir.mkdir(parents=True)
    fits_path = fits_dir / "skymap.fits"
    hp.write_map(
        str(fits_path),
        prob,
        nest=True,
        coord="C",
        column_names=["PROB"],
        overwrite=True,
    )
    # Point the SkyMap at the materialized fixture map (still simulated).
    skymap = skymap.model_copy(
        update={
            "prob_path": str(fits_path),
            "peak": SkyPeak(ra_deg=ra, dec_deg=dec),
            "simulated": True,
        }
    )
    return skymap, prob, CURATED


def test_filter_consumes_skymap_type() -> None:
    with pytest.raises(TypeError, match="SkyMap"):
        filter_candidates({"alert_id": "nope"}, CURATED)  # type: ignore[arg-type]


def test_filter_plus_rerank_on_skymap_fixture_validates_candidate_score(
    tmp_path: Path,
) -> None:
    skymap, prob, star_table = _materialize_fixture_skymap(tmp_path)

    # filter consumes SkyMap (v1).
    filtered = candidates_in_region(skymap, star_table, level=0.9, prob=prob)
    assert isinstance(filtered, list)
    assert len(filtered) >= 1
    for row in filtered:
        assert "star_id" in row
        assert "ra_deg" in row and "dec_deg" in row
        assert "p_sky" in row
        assert row.get("simulated") is True  # skymap fixture is simulated

    # rerank returns list[CandidateScore]. Empty offline index falls back to
    # curated lit_json on catalog rows (bibcoded evidence only; no invented cites).
    scores = rerank(
        filtered,
        {},
        set(),
        skymap=skymap,
        t0_utc=T0,
        prob=prob,
    )
    assert isinstance(scores, list)
    assert len(scores) >= 1
    assert sum(s.posterior for s in scores) == pytest.approx(1.0, abs=1e-9)

    for score in scores:
        assert isinstance(score, CandidateScore)
        # Round-trip through the frozen v1 model (alias "class" included).
        validated = CandidateScore.model_validate(
            score.model_dump(mode="json", by_alias=True)
        )
        assert validated.star_id == score.star_id
        assert validated.simulated is True
        assert validated.breakout.countdown_from == T0
        assert 0.0 <= validated.lit.confidence <= 1.0
        for ev in validated.lit.evidence:
            assert ev.bibcode.strip()  # never invent empty bibcodes
            assert ev.claim.strip()


def test_candidate_scores_fixture_still_validates() -> None:
    """Frozen example CandidateScore rows remain the contract reference."""
    wrapper = json.loads(
        (FIXTURES / "candidate_scores_example.json").read_text(encoding="utf-8")
    )
    assert wrapper.get("simulated") is True
    for row in wrapper["candidates"]:
        score = CandidateScore.model_validate(row)
        assert score.simulated is True
