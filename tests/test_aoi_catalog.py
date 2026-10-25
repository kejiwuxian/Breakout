"""AOI evaluation catalog: curated ∪ Yale BSC5, capped field stars."""

from __future__ import annotations

from backend.candidates.catalog import (
    cap_aoi_candidates,
    load_aoi_evaluation_catalog,
    load_curated_stars,
    load_sky_background_stars,
)


def test_aoi_catalog_merges_background_and_curated() -> None:
    curated = load_curated_stars()
    bg = load_sky_background_stars()
    assert len(curated) >= 40
    assert len(bg) >= 1000
    # Yale BSC5 SpType committed for offline enrichment.
    with_sp = sum(1 for r in bg if r.get("spectral_type"))
    assert with_sp >= 1000
    # Most bright field stars are not CCSN progenitors (stay UNK).
    unk = sum(1 for r in bg if r.get("class") == "UNK")
    assert unk >= 1000
    merged = load_aoi_evaluation_catalog()
    assert len(merged) >= len(curated)
    assert len(merged) >= len(bg)  # mostly BSC5 + curated extras
    # Curated classes preserved (not all UNK).
    classes = {str(r.get("class")) for r in merged}
    assert "RSG" in classes or "BSG" in classes or "WR" in classes
    assert "UNK" in classes
    with_vmag = sum(1 for r in merged if r.get("vmag") is not None)
    assert with_vmag >= 1000


def test_cap_aoi_keeps_progenitors_limits_field() -> None:
    rows = [
        {"star_id": "prog", "class": "RSG", "p_sky": 0.01},
        *[
            {"star_id": f"f{i}", "class": "UNK", "p_sky": float(i)}
            for i in range(100)
        ],
    ]
    capped = cap_aoi_candidates(rows, max_field=10)
    assert any(r["star_id"] == "prog" for r in capped)
    field = [r for r in capped if r["class"] == "UNK"]
    assert len(field) == 10
    assert field[0]["p_sky"] == 99.0
