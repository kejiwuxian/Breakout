"""Tests for backend.candidates.catalog (curated → star_table.parquet)."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from backend.candidates.catalog import (
    STAR_TABLE_PATH,
    build_star_table,
    load_curated_stars,
    load_star_table,
)


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Network connect attempted during offline catalog build")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", lambda *_a, **_k: 1)


def test_load_curated_stars_has_betelgeuse() -> None:
    stars = load_curated_stars()
    assert len(stars) >= 1
    betel = next(s for s in stars if "alf Ori" in str(s.get("star_id", "")))
    assert betel["ra_deg"] == pytest.approx(88.792939, abs=1e-5)
    assert betel["dec_deg"] == pytest.approx(7.407064, abs=1e-5)
    assert betel["class"] == "RSG"
    # Vincent curated: Harper et al. 2017 nominal ~222 pc (ADS 2017AJ....154...11H).
    assert betel.get("distance_kpc") == pytest.approx(0.222)


def test_build_star_table_offline_writes_parquet(
    tmp_path: Path, no_network: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()

    out = tmp_path / "star_table.parquet"
    path = build_star_table(use_network=False, out_path=out)
    assert path == out
    assert out.is_file()

    df = pd.read_parquet(out)
    assert len(df) >= 1
    assert "field_sources" in df.columns
    assert "teff_k" in df.columns
    assert "luminosity_class" in df.columns

    rows = load_star_table(out)
    betel = next(r for r in rows if "alf Ori" in r["star_id"])
    assert betel["ra_deg"] == pytest.approx(88.792939, abs=1e-5)
    assert betel["distance_kpc"] == pytest.approx(0.222)
    assert betel["teff_k"] is None
    assert betel["simulated"] is False
    sources = betel["field_sources"]
    assert isinstance(sources, dict)
    ra_src = str(sources.get("ra_deg") or "")
    assert ra_src and (
        ra_src in {"SIMBAD", "curated_stars.json"} or "simbad" in ra_src.lower()
    )
    # catalog_refs must not invent bibcodes
    for ref in betel.get("catalog_refs") or []:
        assert ref.get("bibcode")
        assert ref["bibcode"] != "curated"


def test_build_star_table_rejects_network_when_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("USE_CACHED_STREAM", "True")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    with pytest.raises(RuntimeError, match="USE_CACHED_STREAM"):
        build_star_table(use_network=True, out_path=tmp_path / "x.parquet")


def test_missing_values_stay_null(tmp_path: Path, no_network: None) -> None:
    curated = tmp_path / "curated.json"
    curated.write_text(
        json.dumps(
            [
                {
                    "star_id": "test-star",
                    "ra_deg": 10.0,
                    "dec_deg": -5.0,
                    "class": "RSG",
                    "spectral_type": "M1Iab",
                    "distance_kpc": None,
                    "extinction_av_mag": None,
                    "teff_k": None,
                    "source": "unit-test",
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "table.parquet"
    build_star_table(use_network=False, out_path=out, curated_path=curated)
    row = load_star_table(out)[0]
    assert row["distance_kpc"] is None
    assert row["extinction_av_mag"] is None
    assert row["teff_k"] is None
    assert row["luminosity_class"] == "Iab"
    assert row["field_sources"].get("spectral_type") == "unit-test"


def test_default_star_table_path_constant() -> None:
    assert STAR_TABLE_PATH.name == "star_table.parquet"
    assert STAR_TABLE_PATH.parent.name == "stars"
