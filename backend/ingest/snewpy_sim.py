"""Simulated bursts per detector (snewpy).

Uses snewpy progenitor models + SNOwGLoBES event rates, then stamps each
detector with a geometric light-travel arrival time from the source direction
and WGS84 EarthLocation. Every output Alert has simulated=True.
"""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
from astropy import units as u
from astropy.constants import c as speed_of_light
from astropy.coordinates import EarthLocation, SkyCoord
from astropy.time import Time

from backend.config import (
    DEFAULT_T_ERR_MS,
    DETECTOR_TABLE,
    ROOT,
    SNOWGLOBES_DETECTOR_MAP,
)
from backend.schemas import Alert, DetectorHit, Pointing

# Default Super-K directional uncertainty for a simulated pointing (degrees).
# Few-degree scale matches the science-basis note; value is simulated.
DEFAULT_SUPERK_POINTING_ERR_DEG = 3.0

EventCountFn = Callable[[float, str, Iterable[str]], dict[str, int]]


def earth_location_for(detector: str) -> EarthLocation:
    """Return astropy EarthLocation for a named detector (WGS84)."""
    if detector not in DETECTOR_TABLE:
        raise KeyError(f"Unknown detector {detector!r}; known={sorted(DETECTOR_TABLE)}")
    row = DETECTOR_TABLE[detector]
    return EarthLocation(
        lat=row["lat_deg"] * u.deg,
        lon=row["lon_deg"] * u.deg,
        height=row["height_m"] * u.m,
    )


def source_unit_vector(ra_deg: float, dec_deg: float) -> np.ndarray:
    """ICRS unit vector toward the source (dimensionless)."""
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    vec = np.asarray(coord.cartesian.xyz.value, dtype=float)
    return vec / np.linalg.norm(vec)


def detector_position_m(detector: str, obstime: Time) -> np.ndarray:
    """Detector position vector from geocenter in meters (GCRS at obstime)."""
    loc = earth_location_for(detector)
    gcrs = loc.get_gcrs(obstime)
    return np.asarray(gcrs.cartesian.xyz.to(u.m).value, dtype=float)


def geocenter_delay_s(
    ra_deg: float,
    dec_deg: float,
    detector: str,
    obstime: Time,
) -> float:
    """Light-travel delay relative to geocenter: −r·û / c (seconds).

    Detectors on the source-facing hemisphere arrive earlier (negative delay).
    Triangulation baseline across Earth is at most about 42 ms.
    """
    r = detector_position_m(detector, obstime)
    uhat = source_unit_vector(ra_deg, dec_deg)
    return float(-np.dot(r, uhat) / speed_of_light.value)


def baseline_length_m(det_a: str, det_b: str, obstime: Time) -> float:
    """Euclidean baseline between two detectors (meters) at obstime."""
    return float(np.linalg.norm(detector_position_m(det_a, obstime) - detector_position_m(det_b, obstime)))


def pair_delay_s(
    ra_deg: float,
    dec_deg: float,
    det_a: str,
    det_b: str,
    obstime: Time,
) -> float:
    """Arrival time difference t_a − t_b from geometry alone (seconds)."""
    return geocenter_delay_s(ra_deg, dec_deg, det_a, obstime) - geocenter_delay_s(
        ra_deg, dec_deg, det_b, obstime
    )


def max_pair_delay_s(det_a: str, det_b: str, obstime: Time) -> float:
    """Maximum |Δt| for a pair = baseline / c."""
    return baseline_length_m(det_a, det_b, obstime) / speed_of_light.value


def _sum_snowglobes_events(frame: Any) -> float:
    """Sum a SNOwGLoBES/snewpy smeared rate table to a scalar event count."""
    values = np.ravel(np.asarray(frame.values, dtype=object))
    total = 0.0
    for x in values:
        total += float(x.value) if hasattr(x, "value") else float(x)
    return total


def expected_events_snewpy(
    distance_kpc: float,
    model: str,
    detectors: Iterable[str],
    *,
    transformation: str = "AdiabaticMSW_NMO",
) -> dict[str, int]:
    """Expected detected events per named detector via snewpy + SNOwGLoBES.

    All returned counts are simulated. Detectors are mapped through
    SNOWGLOBES_DETECTOR_MAP (mass scales are documented approximations).
    """
    from snewpy import snowglobes
    from snewpy.models import ccsn

    if not hasattr(ccsn, model):
        raise ValueError(f"Unknown snewpy CCSN model {model!r}")
    model_cls = getattr(ccsn, model)

    # Prefer a small, commonly available Nakazato combination when applicable.
    if model == "Nakazato_2013":
        sn_model = model_cls(
            progenitor_mass=20 * u.solMass,
            revival_time=200 * u.ms,
            metallicity=0.02,
            eos="shen",
        )
    else:
        # First valid parameter combination for other models.
        combos = list(model_cls.get_param_combinations())
        if not combos:
            raise RuntimeError(f"No parameter combinations for model {model}")
        sn_model = model_cls(**combos[0])

    model_path = sn_model.request_file(sn_model.filename)
    det_list = list(detectors)
    snow_names = sorted(
        {
            str(SNOWGLOBES_DETECTOR_MAP[d]["snowglobes"])
            for d in det_list
            if d in SNOWGLOBES_DETECTOR_MAP
        }
    )

    with tempfile.TemporaryDirectory(prefix="breakout_snewpy_") as tmp:
        fluence_path = snowglobes.generate_fluence(
            str(model_path),
            model,
            transformation,
            float(distance_kpc),
            output_filename=str(Path(tmp) / "fluence"),
        )
        rates = snowglobes.simulate(None, fluence_path, detector_input=snow_names)

    snow_totals: dict[str, float] = {}
    for snow_name, time_bins in rates.items():
        total = 0.0
        for payload in time_bins.values():
            smeared = payload["weighted"]["smeared"]
            total += _sum_snowglobes_events(smeared)
        snow_totals[snow_name] = total

    out: dict[str, int] = {}
    for det in det_list:
        mapping = SNOWGLOBES_DETECTOR_MAP[det]
        snow = str(mapping["snowglobes"])
        scale = float(mapping["mass_scale"])
        out[det] = int(round(snow_totals.get(snow, 0.0) * scale))
    return out


def _alert_id(ra_deg: float, dec_deg: float, distance_kpc: float, model: str, t0_utc: str) -> str:
    digest = hashlib.sha1(
        f"{ra_deg:.6f}|{dec_deg:.6f}|{distance_kpc:.6f}|{model}|{t0_utc}".encode()
    ).hexdigest()[:12]
    return f"sim-burst-{digest}"


def simulate_burst(
    ra_deg: float,
    dec_deg: float,
    distance_kpc: float,
    model: str,
    t0_utc: str,
    *,
    detectors: Iterable[str] | None = None,
    transformation: str = "AdiabaticMSW_NMO",
    event_counts: dict[str, int] | None = None,
    event_count_fn: EventCountFn | None = None,
    pointing_err_deg: float = DEFAULT_SUPERK_POINTING_ERR_DEG,
) -> list[Alert]:
    """Simulate an SN_BURST Alert for each configured detector site.

    Parameters
    ----------
    ra_deg, dec_deg:
        Source direction in ICRS degrees.
    distance_kpc:
        Distance used by snewpy for expected event rates.
    model:
        snewpy CCSN model class name (e.g. ``Nakazato_2013``).
    t0_utc:
        Burst reference time (ISO-8601 UTC) at geocenter.
    event_counts / event_count_fn:
        Optional overrides for tests; default path calls snewpy.

    Returns
    -------
    list[Alert]
        A one-element list containing the multi-detector SN_BURST Alert.
        ``simulated`` is always True.
    """
    det_names = list(detectors) if detectors is not None else list(DETECTOR_TABLE.keys())
    for name in det_names:
        if name not in DETECTOR_TABLE:
            raise KeyError(f"Unknown detector {name!r}")

    t0 = Time(t0_utc, scale="utc")
    if event_counts is not None:
        counts = {d: int(event_counts.get(d, 0)) for d in det_names}
    elif event_count_fn is not None:
        counts = event_count_fn(distance_kpc, model, det_names)
    else:
        counts = expected_events_snewpy(
            distance_kpc, model, det_names, transformation=transformation
        )

    hits: list[DetectorHit] = []
    for name in det_names:
        row = DETECTOR_TABLE[name]
        delay_s = geocenter_delay_s(ra_deg, dec_deg, name, t0)
        t_arrival = t0 + delay_s * u.s
        pointing: Pointing | None = None
        if name == "Super-K":
            pointing = Pointing(
                ra_deg=float(ra_deg),
                dec_deg=float(dec_deg),
                err_deg=float(pointing_err_deg),
            )
        hits.append(
            DetectorHit(
                name=name,  # type: ignore[arg-type]
                lat_deg=float(row["lat_deg"]),
                lon_deg=float(row["lon_deg"]),
                height_m=float(row["height_m"]),
                t_arrival_utc=t_arrival.utc.isot,
                t_err_ms=float(DEFAULT_T_ERR_MS.get(name, 1.0)),
                n_events=int(counts.get(name, 0)),
                pointing=pointing,
            )
        )

    total_events = sum(h.n_events for h in hits)
    # Simulated significance proxy from total counts (not a published statistic).
    significance = float(np.sqrt(max(total_events, 0)))

    alert = Alert(
        alert_id=_alert_id(ra_deg, dec_deg, distance_kpc, model, t0.utc.isot),
        kind="SN_BURST",
        source="snewpy_sim",
        simulated=True,
        t0_utc=t0.utc.isot,
        detectors=hits,
        significance=significance,
        raw={
            "ra_deg": float(ra_deg),
            "dec_deg": float(dec_deg),
            "distance_kpc": float(distance_kpc),
            "model": model,
            "transformation": transformation,
            "note": "All numeric fields from this path are simulated.",
        },
    )
    return [alert]


def simulate_presn(
    *,
    star_id: str,
    alert_id: str,
    extras: dict[str, Any] | None = None,
) -> Alert:
    """Build a simulated PRESN Alert (Stage 0). Filled further in a later prompt."""
    raise NotImplementedError("simulate_presn is filled in a later prompt.")


def save_alerts_jsonl(alerts: list[Alert], out_path: Path) -> Path:
    """Write Alerts as JSONL (one Alert per line)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for alert in alerts:
            fh.write(alert.model_dump_json() + "\n")
    return out_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.ingest.snewpy_sim",
        description="Simulate a galactic CCSN burst with snewpy and write alerts.jsonl.",
    )
    parser.add_argument("--ra", type=float, required=True, help="Source RA (ICRS degrees)")
    parser.add_argument("--dec", type=float, required=True, help="Source Dec (ICRS degrees)")
    parser.add_argument(
        "--distance-kpc",
        type=float,
        required=True,
        help="Distance in kpc for snewpy event rates",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path: data/cache/<scenario> or .../alerts.jsonl",
    )
    parser.add_argument(
        "--model",
        default="Nakazato_2013",
        help="snewpy CCSN model class name (default Nakazato_2013)",
    )
    parser.add_argument(
        "--t0-utc",
        default="2026-10-24T21:46:00",
        help="Burst geocenter time UTC (ISO-8601)",
    )
    parser.add_argument(
        "--transformation",
        default="AdiabaticMSW_NMO",
        help="snewpy flavor transformation name",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    alerts = simulate_burst(
        args.ra,
        args.dec,
        args.distance_kpc,
        args.model,
        args.t0_utc,
        transformation=args.transformation,
    )
    out = Path(args.out)
    if out.suffix != ".jsonl":
        out = out / "alerts.jsonl"
    # Resolve relative to repo root when needed.
    if not out.is_absolute():
        out = ROOT / out
    save_alerts_jsonl(alerts, out)
    print(f"wrote {len(alerts)} simulated Alert(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
