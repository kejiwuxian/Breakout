"""Tony: ranking conforms to CandidateScore v1."""

from __future__ import annotations

import pytest

from backend.literature.rerank import rerank
from backend.schemas import CandidateScore


def test_rerank_output_is_candidate_score_v1() -> None:
    scores = rerank(
        [
            {
                "star_id": "contract-star",
                "ra_deg": 1.0,
                "dec_deg": 2.0,
                "class": "RSG",
                "spectral_type": "M2",
                "p_sky": 1.0,
                "simulated": False,
            }
        ],
        {},  # empty index → lit zeros, empty evidence
        set(),
        t0_utc="2026-10-24T21:46:00Z",
    )
    assert len(scores) == 1
    row = scores[0]
    assert isinstance(row, CandidateScore)
    dumped = row.model_dump(mode="json", by_alias=True)
    assert dumped["class"] == "RSG"
    assert dumped["lit"]["evidence"] == []
    assert dumped["posterior"] == pytest.approx(1.0)
