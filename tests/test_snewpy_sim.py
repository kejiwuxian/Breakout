"""Geometry and schema tests for backend.ingest.snewpy_sim."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from astropy.constants import c as speed_of_light
from astropy.time import Time

from backend.config import DETECTOR_TABLE
from backend.ingest.snewpy_sim import (
    build_scenario_alerts_from_curated,
    detector_position_m,
    geocenter_delay_s,
    max_pair_delay_s,
    pair_delay_s,
    save_alerts_jsonl,
    simulate_burst,
    simulate_presn,
    source_unit_vector,
)
from backend.schemas import Alert


T0 = Time("2026-10-24T21:46:00", scale="utc")
DETECTORS = list(DETECTOR_TABLE.keys())


def _fake_counts(distance_kpc: float, model: str, detectors) -> dict[str, int]:
    return {d: 100 + i for i, d in enumerate(detectors)}


def test_alert_schema_validation_simulated_true() -> None:
    alerts = simulate_burst(
        88.79,
        7.41,
        0.2,
        "Nakazato_2013",
        T0.utc.isot,
        event_count_fn=_fake_counts,
    )
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.simulated is True
    assert alert.kind == "SN_BURST"
    assert alert.source == "snewpy_sim"
    # Round-trip through pydantic / JSON preserves schema.
    parsed = Alert.model_validate_json(alert.model_dump_json())
    assert parsed.alert_id == alert.alert_id
    assert all(d.name in DETECTOR_TABLE for d in parsed.detectors)
    sk = next(d for d in parsed.detectors if d.name == "Super-K")
    assert sk.pointing is not None
    assert sk.pointing.ra_deg == pytest.approx(88.79)
    assert sk.pointing.dec_deg == pytest.approx(7.41)


def test_no_pair_delay_exceeds_baseline_over_c() -> None:
    ra, dec = 180.0, 0.0
    for i, a in enumerate(DETECTORS):
        for b in DETECTORS[i + 1 :]:
            dt = abs(pair_delay_s(ra, dec, a, b, T0))
            limit = max_pair_delay_s(a, b, T0)
            assert dt <= limit + 1e-12
            assert limit <= (2 * 6371e3) / speed_of_light.value + 1e-6  # ~Earth diameter


def test_source_along_baseline_gives_largest_delay() -> None:
    """A source along the baseline unit vector maximizes |Δt| ≈ baseline/c."""
    a, b = "Super-K", "IceCube"
    r_a = detector_position_m(a, T0)
    r_b = detector_position_m(b, T0)
    baseline = r_b - r_a
    uhat = baseline / np.linalg.norm(baseline)
    # Convert unit vector to RA/Dec.
    from astropy.coordinates import CartesianRepresentation, SkyCoord
    from astropy import units as u

    coord = SkyCoord(CartesianRepresentation(*(uhat * u.one)), frame="icrs")
    ra = float(coord.ra.deg)
    dec = float(coord.dec.deg)

    dt_along = abs(pair_delay_s(ra, dec, a, b, T0))
    limit = max_pair_delay_s(a, b, T0)
    assert dt_along == pytest.approx(limit, rel=1e-6)

    # Off-axis directions yield smaller |Δt|.
    for ra_off, dec_off in [(0.0, 0.0), (90.0, 45.0), (270.0, -30.0)]:
        dt_off = abs(pair_delay_s(ra_off, dec_off, a, b, T0))
        assert dt_off <= dt_along + 1e-12


def test_arrival_order_matches_geometry() -> None:
    alerts = simulate_burst(
        88.79,
        7.41,
        0.2,
        "Nakazato_2013",
        T0.utc.isot,
        event_count_fn=_fake_counts,
    )
    alert = alerts[0]
    delays = {
        d.name: geocenter_delay_s(88.79, 7.41, d.name, T0) for d in alert.detectors
    }
    # Earlier arrival <=> smaller (more negative) geocenter delay.
    ordered = sorted(alert.detectors, key=lambda d: Time(d.t_arrival_utc))
    expected = sorted(alert.detectors, key=lambda d: delays[d.name])
    assert [d.name for d in ordered] == [d.name for d in expected]


def test_cli_write_jsonl(tmp_path: Path) -> None:
    alerts = simulate_burst(
        10.0,
        -20.0,
        10.0,
        "Nakazato_2013",
        T0.utc.isot,
        event_counts={d: 1 for d in DETECTORS},
    )
    out = tmp_path / "scenario_test" / "alerts.jsonl"
    save_alerts_jsonl(alerts, out)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["simulated"] is True
    assert payload["source"] == "snewpy_sim"
    Alert.model_validate(payload)


def test_source_unit_vector_normalized() -> None:
    v = source_unit_vector(12.3, -45.6)
    assert v.shape == (3,)
    assert float(np.linalg.norm(v)) == pytest.approx(1.0)


def test_simulate_presn_simulated_true() -> None:
    alert = simulate_presn(
        star_id="* alf Ori",
        alert_id="sim-presn-test",
        extras={"t0_utc": "2026-10-24T20:46:00", "false_alarm_rate_per_century": 0.5},
    )
    assert alert.simulated is True
    assert alert.kind == "PRESN"
    assert alert.source == "snewpy_sim"
    assert alert.raw["star_id"] == "* alf Ori"
    assert {d.name for d in alert.detectors} == {"KamLAND", "Super-K"}


def test_build_scenario_from_curated_betelgeuse() -> None:
    alerts = build_scenario_alerts_from_curated(
        "Betelgeuse",
        event_count_fn=_fake_counts,
        presn_lead_s=60.0,
    )
    assert len(alerts) == 2
    assert alerts[0].kind == "PRESN" and alerts[0].simulated is True
    assert alerts[1].kind == "SN_BURST" and alerts[1].simulated is True
    assert alerts[1].raw["ra_deg"] == pytest.approx(88.792939)
    assert alerts[1].raw["distance_kpc"] == pytest.approx(0.168)

