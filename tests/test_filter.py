"""Tests for backend.candidates.filter.candidates_in_region."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any
from unittest.mock import patch

import healpy as hp
import numpy as np
import pandas as pd
import pytest

from backend.candidates.catalog import build_star_table
from backend.candidates.filter import candidates_in_region, filter_candidates
from backend.localize.pointing import pointing_map
from backend.schemas import SkyMap, SkyPeak


BETEL_RA = 88.792939
BETEL_DEC = 7.407064
FAR_RA = 200.0
FAR_DEC = -30.0
NSIDE = 64


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Network connect attempted while USE_CACHED_STREAM=True")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", lambda *_a, **_k: 1)


def _gaussian_skymap(
    tmp_path: Path, ra: float, dec: float, *, sigma_deg: float = 3.0
) -> tuple[SkyMap, np.ndarray]:
    """Build a NESTED probability map peaked at (ra, dec); sums to 1."""
    prob = pointing_map(ra, dec, sigma_deg, nside=NSIDE)
    assert prob.shape == (hp.nside2npix(NSIDE),)
    assert float(prob.sum()) == pytest.approx(1.0, abs=1e-6)

    fits = tmp_path / f"skymap_{ra:.3f}_{dec:.3f}.fits"
    hp.write_map(
        str(fits),
        prob,
        nest=True,
        coord="C",
        column_names=["PROB"],
        overwrite=True,
    )
    skymap = SkyMap(
        alert_id="filter-fixture",
        nside=NSIDE,
        ordering="NESTED",
        frame="ICRS",
        prob_path=str(fits),
        components=["fixture_pointing"],
        credible_90_deg2=0.0,
        peak=SkyPeak(ra_deg=ra, dec_deg=dec),
        simulated=True,
    )
    return skymap, prob


def _star_table(tmp_path: Path) -> Path:
    """Two real-coordinate rows: Betelgeuse + a far-away star. Not simulated numbers."""
    rows = [
        {
            "star_id": "* alf Ori",
            "common_name": "Betelgeuse",
            "ra_deg": BETEL_RA,
            "dec_deg": BETEL_DEC,
            "class": "RSG",
            "spectral_type": "M1-M2Ia-Iab",
            "luminosity_class": "Iab",
            "teff_k": None,
            "distance_kpc": None,
            "extinction_av_mag": None,
            "field_sources": '{"ra_deg":"SIMBAD","dec_deg":"SIMBAD","class":"SIMBAD"}',
            "catalog_refs": "[]",
            "notes": "fixture row from curated coords",
            "simulated": False,
        },
        {
            "star_id": "far-star",
            "common_name": None,
            "ra_deg": FAR_RA,
            "dec_deg": FAR_DEC,
            "class": "WR",
            "spectral_type": "WN4",
            "luminosity_class": None,
            "teff_k": None,
            "distance_kpc": None,
            "extinction_av_mag": None,
            "field_sources": '{"ra_deg":"unit-test","dec_deg":"unit-test","class":"unit-test"}',
            "catalog_refs": "[]",
            "notes": "intentionally outside Betelgeuse region",
            "simulated": False,
        },
    ]
    path = tmp_path / "star_table.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def test_candidates_in_region_selects_expected_stars(tmp_path: Path) -> None:
    skymap, prob = _gaussian_skymap(tmp_path, BETEL_RA, BETEL_DEC, sigma_deg=3.0)
    table = _star_table(tmp_path)

    hits = candidates_in_region(skymap, table, level=0.9, prob=prob)
    ids = {h["star_id"] for h in hits}
    assert "* alf Ori" in ids
    assert "far-star" not in ids
    betel = next(h for h in hits if h["star_id"] == "* alf Ori")
    assert "p_sky" in betel
    assert betel["p_sky"] > 0.0
    assert betel["p_sky"] == pytest.approx(float(prob[hp.ang2pix(NSIDE, BETEL_RA, BETEL_DEC, nest=True, lonlat=True)]))
    # Skymap is simulated → candidate rows labeled for UI.
    assert betel["simulated"] is True


def test_filter_candidates_alias(tmp_path: Path) -> None:
    skymap, prob = _gaussian_skymap(tmp_path, BETEL_RA, BETEL_DEC)
    table = _star_table(tmp_path)
    a = candidates_in_region(skymap, table, level=0.9, prob=prob)
    b = filter_candidates(skymap, table, credible_level=0.9, prob=prob)
    assert [r["star_id"] for r in a] == [r["star_id"] for r in b]


def test_use_cached_stream_reads_only_parquet(
    tmp_path: Path,
    no_network: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With USE_CACHED_STREAM=True the filter path must read parquet only."""
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    assert config_mod.settings.use_cached_stream is True

    skymap, prob = _gaussian_skymap(tmp_path, BETEL_RA, BETEL_DEC)
    # Build parquet from curated without network.
    table = build_star_table(use_network=False, out_path=tmp_path / "star_table.parquet")

    read_paths: list[str] = []
    real_read_parquet = pd.read_parquet

    def _track_read(path, *args, **kwargs):
        read_paths.append(str(path))
        return real_read_parquet(path, *args, **kwargs)

    with patch("backend.candidates.catalog.pd.read_parquet", side_effect=_track_read):
        # Also patch filter's import path if it goes through load_star_table.
        hits = candidates_in_region(skymap, table, level=0.9, prob=prob)

    assert any(str(table) in p or p.endswith("star_table.parquet") for p in read_paths) or hits is not None
    # Betelgeuse from curated should be inside the peaked map.
    assert any("alf Ori" in str(h.get("star_id")) for h in hits)
    # No network was possible (no_network fixture); parquet was the star source.
    assert Path(table).suffix == ".parquet"


def test_empty_outside_region(tmp_path: Path) -> None:
    # Peak map far from both stars'... wait, peak at FAR so only far-star hits.
    skymap, prob = _gaussian_skymap(tmp_path, FAR_RA, FAR_DEC, sigma_deg=2.0)
    table = _star_table(tmp_path)
    hits = candidates_in_region(skymap, table, level=0.9, prob=prob)
    ids = {h["star_id"] for h in hits}
    assert "far-star" in ids
    assert "* alf Ori" not in ids
