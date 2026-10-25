"""Tests for backend.ingest.cache save / async replay."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from backend.ingest import cache as cache_mod
from backend.ingest.snewpy_sim import simulate_burst
from backend.schemas import Alert


def _burst(t0: str, alert_suffix: str, n: int = 5) -> Alert:
    alerts = simulate_burst(
        10.0,
        -20.0,
        10.0,
        "Nakazato_2013",
        t0,
        event_counts={
            "Super-K": n,
            "SNO+": n,
            "IceCube": n,
            "KamLAND": n,
            "JUNO": n,
        },
    )
    alert = alerts[0]
    # Distinct ids for multi-alert scenarios.
    return alert.model_copy(update={"alert_id": f"{alert.alert_id}-{alert_suffix}"})


@pytest.fixture()
def cache_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "cache"
    root.mkdir()
    monkeypatch.setattr(cache_mod, "CACHE_ROOT", root)
    return root


def test_save_and_load_roundtrip(cache_root: Path) -> None:
    a1 = _burst("2026-10-24T21:46:00", "a")
    a2 = _burst("2026-10-24T21:46:05", "b")
    path = cache_mod.save_scenario("scenario_unit", [a1, a2])
    assert path == cache_root / "scenario_unit" / "alerts.jsonl"
    loaded = cache_mod.load_alerts("scenario_unit")
    assert len(loaded) == 2
    assert loaded[0].alert_id == a1.alert_id
    assert loaded[1].alert_id == a2.alert_id
    assert all(a.simulated is True for a in loaded)
    for row in path.read_text(encoding="utf-8").splitlines():
        Alert.model_validate(json.loads(row))


def test_replay_order(cache_root: Path) -> None:
    # Save out of chronological order; replay must sort by t0_utc.
    late = _burst("2026-10-24T21:46:10", "late")
    early = _burst("2026-10-24T21:46:00", "early")
    mid = _burst("2026-10-24T21:46:05", "mid")
    cache_mod.save_scenario("scenario_order", [late, early, mid])

    async def _run() -> list[str]:
        out = []
        async for alert in cache_mod.replay_scenario("scenario_order", speed=0.0):
            out.append(alert.alert_id)
        return out

    ids = asyncio.run(_run())
    assert ids == [early.alert_id, mid.alert_id, late.alert_id]


def test_replay_relative_timing(cache_root: Path) -> None:
    a0 = _burst("2026-10-24T21:46:00", "t0")
    a1 = _burst("2026-10-24T21:46:00.200", "t1")  # +200 ms
    cache_mod.save_scenario("scenario_timing", [a0, a1])

    async def _run(speed: float) -> float:
        t_start = time.monotonic()
        times: list[float] = []
        async for _alert in cache_mod.replay_scenario("scenario_timing", speed=speed):
            times.append(time.monotonic())
        return times[1] - times[0]

    # speed=1 → ~0.2 s gap; allow generous CI slack.
    gap = asyncio.run(_run(1.0))
    assert 0.12 <= gap <= 0.45

    # speed=10 → ~0.02 s gap (still ordered).
    gap_fast = asyncio.run(_run(10.0))
    assert gap_fast < gap
    assert gap_fast < 0.12


def test_replay_emits_valid_simulated_alerts(cache_root: Path) -> None:
    alerts = [
        _burst("2026-10-24T21:46:00", "x"),
        _burst("2026-10-24T21:46:01", "y"),
    ]
    cache_mod.save_scenario("scenario_valid", alerts)

    async def _run() -> list[Alert]:
        return [a async for a in cache_mod.replay_scenario("scenario_valid", speed=0.0)]

    replayed = asyncio.run(_run())
    assert len(replayed) == 2
    for alert in replayed:
        assert alert.simulated is True
        assert alert.kind == "SN_BURST"
        Alert.model_validate_json(alert.model_dump_json())
