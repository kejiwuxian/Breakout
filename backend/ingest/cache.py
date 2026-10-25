"""Replay recorded scenarios from data/cache/.

Save Alerts to data/cache/<scenario>/alerts.jsonl and replay them as an
async generator that preserves relative timing (scaled by a speed factor).
No LLM or network calls; used when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterable
from pathlib import Path

from astropy.time import Time

from backend.config import ROOT
from backend.schemas import Alert

CACHE_ROOT = ROOT / "data" / "cache"
ALERTS_FILENAME = "alerts.jsonl"


def scenario_dir(scenario: str) -> Path:
    """Return the absolute path to a named cache scenario."""
    return CACHE_ROOT / scenario


def alerts_path(scenario: str) -> Path:
    """Return data/cache/<scenario>/alerts.jsonl."""
    return scenario_dir(scenario) / ALERTS_FILENAME


def save_scenario(
    scenario: str,
    alerts: Iterable[Alert],
    *,
    overwrite: bool = True,
) -> Path:
    """Write Alerts to data/cache/<scenario>/alerts.jsonl (one JSON object per line).

    Preserves each Alert's ``simulated`` flag as stored; does not invent values.
    """
    path = alerts_path(scenario)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(path)

    alert_list = list(alerts)
    with path.open("w", encoding="utf-8") as fh:
        for alert in alert_list:
            fh.write(alert.model_dump_json() + "\n")
    return path


def load_alerts(scenario: str) -> list[Alert]:
    """Load Alert objects from data/cache/<scenario>/alerts.jsonl.

    Each line is one Alert JSON object. Simulated vs real is per-record
    via the simulated field; do not invent values. Empty files yield [].
    """
    path = alerts_path(scenario)
    if not path.is_file():
        raise FileNotFoundError(f"Missing cache file: {path}")

    alerts: list[Alert] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            alerts.append(Alert.model_validate_json(stripped))
        except Exception as exc:  # noqa: BLE001 — rewrap with line context
            raise ValueError(f"Invalid Alert JSONL at {path}:{line_no}: {exc}") from exc
    return alerts


def _alert_sort_key(alert: Alert) -> float:
    """Sort key: t0_utc as MJD (UTC)."""
    return float(Time(alert.t0_utc, scale="utc").mjd)


async def replay_scenario(
    scenario: str,
    *,
    speed: float = 1.0,
) -> AsyncIterator[Alert]:
    """Yield Alerts from a cached scenario, preserving relative timing.

    Parameters
    ----------
    scenario:
        Directory name under data/cache/.
    speed:
        Timing scale factor. ``1.0`` plays gaps in real time; ``10.0`` is 10×
        faster. ``speed <= 0`` emits as fast as possible (tests).

    Notes
    -----
    Relative delays are taken from successive ``t0_utc`` values after sorting.
    No network or LLM calls.
    """
    alerts = sorted(load_alerts(scenario), key=_alert_sort_key)
    if not alerts:
        return

    t_ref = Time(alerts[0].t0_utc, scale="utc")
    wall0 = time.monotonic()

    for alert in alerts:
        if speed > 0:
            offset_s = float((Time(alert.t0_utc, scale="utc") - t_ref).to_value("s"))
            target = wall0 + offset_s / speed
            delay = target - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
        yield alert


async def collect_replay(
    scenario: str,
    *,
    speed: float = 0.0,
) -> list[Alert]:
    """Convenience: materialize replay_scenario into a list (speed<=0 by default)."""
    return [alert async for alert in replay_scenario(scenario, speed=speed)]
