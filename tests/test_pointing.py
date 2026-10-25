"""Tests for backend.localize.pointing."""

from __future__ import annotations

import healpy as hp
import numpy as np
import pytest

from backend.localize.pointing import pointing_map
from backend.schemas import Pointing
from backend.localize.pointing import pointing_map_from_pointing


NSIDE = 64


def test_pointing_map_sums_to_one() -> None:
    prob = pointing_map(88.7929, 7.4071, 3.0, nside=NSIDE)
    assert prob.shape == (hp.nside2npix(NSIDE),)
    assert float(prob.sum()) == pytest.approx(1.0, rel=1e-12, abs=1e-12)
    assert np.all(prob >= 0.0)


def test_pointing_map_peak_near_center() -> None:
    ra, dec, err = 123.4, -45.6, 2.5
    prob = pointing_map(ra, dec, err, nside=NSIDE)
    peak = int(np.argmax(prob))
    ra_p, dec_p = hp.pix2ang(NSIDE, peak, nest=True, lonlat=True)
    v0 = np.asarray(hp.ang2vec(ra, dec, lonlat=True))
    vp = np.asarray(hp.ang2vec(ra_p, dec_p, lonlat=True))
    ang = float(np.degrees(np.arccos(np.clip(np.dot(v0, vp), -1.0, 1.0))))
    assert ang < err


def test_pointing_map_from_pointing_schema() -> None:
    p = Pointing(ra_deg=10.0, dec_deg=20.0, err_deg=4.0)
    prob = pointing_map_from_pointing(p, nside=NSIDE)
    assert float(prob.sum()) == pytest.approx(1.0)
