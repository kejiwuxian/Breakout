"""Replay/offline enrichment for AOI ranked stars (same schema as inventory).

Production Grok flow (offline-safe):
1. Catalog rows carry published fields (curated lit / Yale BSC5 SpType, etc.).
2. ``profile_from_row`` builds a ``ProgenitorProfile`` (life window, composition,
   SN-potential, lit) — identical to ``build_inventory``.
3. ``rank_with_grok`` attaches those fields onto ``CandidateScore``.
4. Live Grok shortlist ranking is optional and separate (needs XAI key +
   ``USE_CACHED_STREAM=False``); literature scoring needs ADS + XAI via
   ``literature.build_index`` / ``progenitors.monitor``.

This module materializes step (2) for every star that appears in replay
scenario ranked lists into ``data/stars/replay_rank_enrichment.parquet`` so
offline replays stay deterministic without live API calls.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from backend.config import ROOT
from backend.literature.rerank import load_index
from backend.progenitors.inventory import (
    INVENTORY_PATH,
    ProgenitorProfile,
    load_inventory,
    profile_from_row,
    upsert_profile,
)
from backend.schemas import Alert

logger = logging.getLogger("breakout.progenitors.enrich")

ENRICHMENT_PATH = ROOT / "data" / "stars" / "replay_rank_enrichment.parquet"
ENRICHMENT_META_PATH = ROOT / "data" / "stars" / "replay_rank_enrichment_meta.json"

# Scenario caches under data/cache/ used for offline replay enrichment.
_DEFAULT_SCENARIOS = (
    "scenario_a_galactic_ccsn",
    "scenario_b_icecube_170922a",
    "scenario_c_icecube_230416a",
    "scenario_d_icecube_191001a",
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def merge_profiles(
    primary: dict[str, ProgenitorProfile],
    *extras: dict[str, ProgenitorProfile],
) -> dict[str, ProgenitorProfile]:
    """Merge profile maps; earlier maps win on star_id conflicts."""
    out = dict(primary)
    for extra in extras:
        for sid, profile in extra.items():
            if sid not in out:
                out[sid] = profile
    return out


def load_enrichment(path: Path | None = None) -> dict[str, ProgenitorProfile]:
    """Load replay enrichment parquet (empty dict if missing)."""
    target = Path(path) if path is not None else ENRICHMENT_PATH
    if not target.is_file():
        return {}
    return load_inventory(target)


def profiles_for_candidates(
    candidates: list[dict[str, Any]],
    *,
    inventory: dict[str, ProgenitorProfile] | None = None,
    enrichment: dict[str, ProgenitorProfile] | None = None,
    index_rows: dict[str, dict[str, Any]] | None = None,
    reviewed_utc: str | None = None,
) -> dict[str, ProgenitorProfile]:
    """Resolve a ProgenitorProfile for every candidate (inventory → cache → row).

    Mirrors production inventory attachment: curated inventory first, then the
    committed replay enrichment cache, then on-the-fly ``profile_from_row`` from
    the (BSC5/curated) catalog row so SpType/composition/life are never dropped
    when the row already carries published fields.
    """
    inv = inventory if inventory is not None else load_inventory()
    enrich = enrichment if enrichment is not None else load_enrichment()
    profiles = merge_profiles(inv, enrich)
    reviewed = reviewed_utc or _utcnow_iso()
    for row in candidates:
        sid = str(row.get("star_id") or "").strip()
        if not sid or sid in profiles:
            continue
        built = profile_from_row(row, index_rows=index_rows, reviewed_utc=reviewed)
        if built is not None:
            profiles[sid] = built
    return profiles


def _alerts_from_scenario(cache_dir: Path) -> list[Alert]:
    alerts_path = cache_dir / "alerts.jsonl"
    if not alerts_path.is_file():
        return []
    out: list[Alert] = []
    for line in alerts_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        blob = raw.get("alert") if isinstance(raw, dict) and "alert" in raw else raw
        try:
            alert = Alert.model_validate(blob)
        except Exception as exc:  # noqa: BLE001
            logger.warning("skip alert in %s: %s", cache_dir.name, exc)
            continue
        if alert.kind in {"SN_BURST", "HE_NEUTRINO"}:
            out.append(alert)
    return out


def collect_ranked_candidate_rows(
    *,
    scenarios: tuple[str, ...] | list[str] = _DEFAULT_SCENARIOS,
    cache_root: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Run offline AOI filter for each scenario; return unique candidate rows.

    Uses the same catalog + filter path as ``pipeline.process_sn_burst`` (no
    live Grok). Returns (rows, scenario→star_ids).
    """
    from backend.candidates.catalog import (
        cap_aoi_candidates,
        load_aoi_evaluation_catalog,
    )
    from backend.candidates.filter import candidates_in_region
    from backend.localize.fuse import fuse
    import healpy as hp
    import numpy as np

    root = Path(cache_root) if cache_root is not None else ROOT / "data" / "cache"
    catalog = load_aoi_evaluation_catalog()
    by_id: dict[str, dict[str, Any]] = {}
    per_scenario: dict[str, list[str]] = {}

    for name in scenarios:
        cache_dir = root / name
        if not cache_dir.is_dir():
            logger.info("enrich: skip missing scenario cache %s", name)
            continue
        star_ids: list[str] = []
        for alert in _alerts_from_scenario(cache_dir):
            try:
                skymap = fuse(alert)
                fits = Path(skymap.prob_path)
                if not fits.is_file():
                    fits = ROOT / skymap.prob_path
                prob = np.asarray(hp.read_map(str(fits), nest=True))
                rows = candidates_in_region(
                    skymap, catalog, level=0.9, prob=prob
                )
                rows = cap_aoi_candidates(rows)
            except Exception as exc:  # noqa: BLE001
                logger.warning("enrich: filter failed for %s: %s", alert.alert_id, exc)
                continue
            for row in rows:
                sid = str(row.get("star_id") or "").strip()
                if not sid:
                    continue
                star_ids.append(sid)
                # Prefer curated / already-enriched rows over thinner duplicates.
                prev = by_id.get(sid)
                if prev is None:
                    by_id[sid] = dict(row)
                    continue
                if not prev.get("spectral_type") and row.get("spectral_type"):
                    by_id[sid] = dict(row)
                elif prev.get("class") in {None, "", "UNK"} and row.get("class") not in {
                    None,
                    "",
                    "UNK",
                }:
                    by_id[sid] = dict(row)
        per_scenario[name] = sorted(set(star_ids))
        logger.info(
            "enrich: scenario=%s n_ranked=%d", name, len(per_scenario[name])
        )

    return list(by_id.values()), per_scenario


def build_replay_enrichment(
    *,
    out_path: Path | None = None,
    scenarios: tuple[str, ...] | list[str] = _DEFAULT_SCENARIOS,
    inventory_path: Path | None = None,
    index_path: Path | None = None,
    reviewed_utc: str | None = None,
) -> Path:
    """Materialize enrichment profiles for all replay-ranked stars.

    Curated inventory stars are skipped (already covered). Field/AOI stars get
    inventory-schema profiles from BSC5 SpType + optional literature index.
    """
    reviewed = reviewed_utc or _utcnow_iso()
    rows, per_scenario = collect_ranked_candidate_rows(scenarios=scenarios)
    inv = load_inventory(inventory_path)
    index_rows = load_index(index_path)
    profiles: list[ProgenitorProfile] = []
    for row in rows:
        sid = str(row.get("star_id") or "")
        if sid in inv:
            # Keep curated inventory as source of truth; still record coverage.
            continue
        profile = profile_from_row(row, index_rows=index_rows, reviewed_utc=reviewed)
        if profile is not None:
            profiles.append(profile)

    target = Path(out_path) if out_path is not None else ENRICHMENT_PATH
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)

    # Write via upsert loop so schema matches inventory parquet exactly.
    if target.is_file():
        target.unlink()
    for profile in profiles:
        upsert_profile(profile, path=target)

    if not profiles:
        # Ensure an empty parquet with the right columns exists.
        pd.DataFrame(
            columns=[
                "star_id",
                "common_name",
                "ra_deg",
                "dec_deg",
                "class",
                "spectral_type",
                "distance_kpc",
                "extinction_av_mag",
                "composition",
                "life_expectancy_json",
                "sn_potential",
                "lit_json",
                "last_reviewed_utc",
                "catalog_refs_json",
                "simulated",
            ]
        ).to_parquet(target, index=False)

    n_with_sp = sum(1 for p in profiles if p.spectral_type)
    n_classified = sum(1 for p in profiles if p.class_ not in {"UNK", "AGN"})
    n_breakout = sum(
        1
        for p in profiles
        if p.life_expectancy.optical_breakout_window != "n/a"
    )
    meta = {
        "path": (
            str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target)
        ),
        "built_utc": reviewed,
        "n_profiles": len(profiles),
        "n_with_spectral_type": n_with_sp,
        "n_inferred_progenitor_class": n_classified,
        "n_with_breakout_window": n_breakout,
        "scenarios": per_scenario,
        "note": (
            "Replay enrichment uses the same ProgenitorProfile schema as "
            "progenitor_inventory.parquet. Built offline from AOI filter hits "
            "(curated ∪ Yale BSC5 SpType). Live ADS/Grok literature scoring "
            "requires ADS_API_TOKEN + XAI_API_KEY and USE_CACHED_STREAM=False."
        ),
    }
    meta_path = target.with_name(target.stem + "_meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "Wrote %d replay enrichment profiles to %s (spectral=%d classified=%d)",
        len(profiles),
        target,
        n_with_sp,
        n_classified,
    )
    return target


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.progenitors.enrich",
        description="Materialize offline replay rank enrichment for AOI stars.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ENRICHMENT_PATH,
        help="Output parquet path.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=None,
        help="Scenario cache name (repeatable). Default: all offline scenarios.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    scenarios = tuple(args.scenario) if args.scenario else _DEFAULT_SCENARIOS
    path = build_replay_enrichment(out_path=args.out, scenarios=scenarios)
    meta_path = path.with_name(path.stem + "_meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    print(json.dumps({"path": str(path), **meta}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
