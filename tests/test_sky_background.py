"""All-sky Yale BSC5 background catalog for SVG skymap rendering."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from backend.config import ROOT
from backend.localize.region import (
    SKY_BACKGROUND_PATH,
    load_public_field_stars,
    public_sky_base,
)

META_PATH = ROOT / "data" / "stars" / "sky_background_meta.json"


def test_sky_background_file_is_committed() -> None:
    assert SKY_BACKGROUND_PATH.is_file()
    assert META_PATH.is_file()
    payload = json.loads(SKY_BACKGROUND_PATH.read_text(encoding="utf-8"))
    assert payload["schema"] == "breakout.sky_background.v1"
    assert payload["vizier"] == "V/50"
    assert payload["nasa_heasarc"] == "BSC5P"
    assert payload["vmax"] == 6.5
    assert payload["n_stars"] >= 1000
    assert len(payload["stars"]) == payload["n_stars"]


def test_load_public_field_stars_is_dense_allsky() -> None:
    stars = load_public_field_stars()
    assert len(stars) >= 1000
    assert stars[0]["source"] == "yale_bsc5_v50"
    ras = [float(s["ra_deg"]) for s in stars]
    decs = [float(s["dec_deg"]) for s in stars]
    assert min(ras) < 30.0
    assert max(ras) > 330.0
    assert min(decs) < -60.0
    assert max(decs) > 60.0
    bins: set[tuple[int, int]] = set()
    for ra, dec in zip(ras, decs, strict=False):
        i = min(11, int(ra / 30.0))
        j = min(5, int((dec + 90.0) / 30.0))
        bins.add((i, j))
    assert len(bins) >= 60
    with_vmag = sum(1 for s in stars if s.get("vmag") is not None)
    assert with_vmag == len(stars)


def test_public_sky_base_reports_bsc5() -> None:
    base = public_sky_base()
    assert base["n_field_stars"] == len(base["field_stars"]) >= 1000
    assert "yale_bsc5" in base["source"]
    assert "Hoffleit" in base["field_catalog"]
    assert base.get("galactic_plane") == []
    assert base.get("render") == "svg_v2"


def test_build_script_parse_helpers() -> None:
    path = ROOT / "scripts" / "build_sky_background_catalog.py"
    spec = importlib.util.spec_from_file_location("build_sky_background_catalog", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.sexagesimal_ra_to_deg(6, 45, 8.9) == pytest.approx(101.287083, abs=1e-5)
    assert mod.sexagesimal_dec_to_deg("-", 16, 42, 58) == pytest.approx(
        -16.716111, abs=1e-5
    )
    assert mod.parse_catalog_line("too-short") is None


def test_sky_background_stars_include_spectral_types() -> None:
    payload = json.loads(SKY_BACKGROUND_PATH.read_text(encoding="utf-8"))
    stars = payload["stars"]
    with_sp = [s for s in stars if s.get("spectral_type")]
    assert len(with_sp) >= 1000
    # Sirius (HR2491) is A0/A1 in BSC5.
    sirius = next(s for s in stars if s["star_id"] == "HR2491")
    assert sirius.get("spectral_type")


def test_meta_documents_provenance() -> None:
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    assert "cdsarc" in meta["source_url"] or meta["source_url"].startswith("file://")
    assert meta["bibcode"] == "1991bsc..book.....H"
    assert meta["coverage"]["n"] >= 1000
    assert meta["coverage"]["sky_bins_occupied_of_72"] >= 60
    assert Path(ROOT / meta["path"]).is_file()
