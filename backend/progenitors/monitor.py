"""Publication monitor: poll ADS/arXiv for new progenitor papers and refresh inventory.

Offline/async only — not on the neutrino trigger path. When ADS/XAI keys are
missing or ``USE_CACHED_STREAM=True``, uses replay fixtures / dry-run and never
hits the network.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import ROOT, settings
from backend.literature.build_index import (
    FIXTURES_LITERATURE,
    LiteratureBuildError,
    merge_papers,
    query_ads,
    query_arxiv,
    query_grok,
    star_id_slug,
    validate_literature,
)
from backend.progenitors.inventory import (
    INVENTORY_PATH,
    ProgenitorProfile,
    build_inventory,
    inventory_status,
    load_inventory,
    profile_from_row,
    upsert_profile,
)
from backend.schemas import Literature

logger = logging.getLogger("breakout.progenitors.monitor")

WATERMARK_PATH = ROOT / "data" / "stars" / "publication_monitor_watermark.json"
MONITOR_FIXTURES = ROOT / "tests" / "fixtures" / "progenitors"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_watermark(path: Path = WATERMARK_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"last_check_utc": None, "seen_bibcodes": {}, "updates": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"last_check_utc": None, "seen_bibcodes": {}, "updates": []}
    if not isinstance(data, dict):
        return {"last_check_utc": None, "seen_bibcodes": {}, "updates": []}
    data.setdefault("seen_bibcodes", {})
    data.setdefault("updates", [])
    return data


def _save_watermark(data: dict[str, Any], path: Path = WATERMARK_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _network_allowed() -> bool:
    """Live ADS/Grok only when keys exist and cached-stream (trigger) mode is off."""
    if settings.use_cached_stream:
        return False
    if not (settings.ads_api_token or "").strip():
        return False
    if not (settings.xai_api_key or "").strip():
        return False
    return True


def _papers_for_star_replay(star_id: str, replay_dir: Path) -> list[dict[str, str]]:
    slug = star_id_slug(star_id)
    star_dir = replay_dir / slug
    if not star_dir.is_dir():
        # Fall back to literature fixtures layout.
        star_dir = FIXTURES_LITERATURE / slug
    if not star_dir.is_dir():
        return []
    from backend.literature.build_index import _papers_from_replay

    return _papers_from_replay(star_dir)


def _new_bibcodes(
    papers: list[dict[str, str]],
    *,
    seen: dict[str, Any],
    star_id: str,
) -> list[dict[str, str]]:
    known = set(seen.get(star_id) or [])
    fresh: list[dict[str, str]] = []
    for paper in papers:
        bib = str(paper.get("bibcode") or "").strip()
        if not bib:
            continue
        if bib in known:
            continue
        fresh.append(paper)
    return fresh


def _apply_literature_to_profile(
    profile: ProgenitorProfile,
    lit: Literature,
    *,
    reviewed_utc: str,
) -> ProgenitorProfile:
    """Rebuild inventory fields that depend on literature scores."""
    row = {
        "star_id": profile.star_id,
        "common_name": profile.common_name,
        "ra_deg": profile.ra_deg,
        "dec_deg": profile.dec_deg,
        "class": profile.class_,
        "spectral_type": profile.spectral_type,
        "distance_kpc": profile.distance_kpc,
        "extinction_av_mag": profile.extinction_av_mag,
        "notes": profile.composition,
        "catalog_refs": profile.catalog_refs,
        "simulated": profile.simulated,
        "lit": lit.model_dump(mode="json"),
    }
    updated = profile_from_row(
        row,
        index_rows={
            profile.star_id: {
                "star_id": profile.star_id,
                **lit.model_dump(mode="json"),
                "evidence_json": json.dumps(
                    [e.model_dump(mode="json") for e in lit.evidence]
                ),
            }
        },
        reviewed_utc=reviewed_utc,
    )
    return updated or profile.model_copy(update={"last_reviewed_utc": reviewed_utc})


def refresh_star_from_papers(
    profile: ProgenitorProfile,
    papers: list[dict[str, str]],
    *,
    use_grok: bool,
    replay_dir: Path | None = None,
) -> tuple[ProgenitorProfile, dict[str, Any]]:
    """Score papers with Grok (or replay) and return updated profile + meta."""
    allowed = {str(p["bibcode"]) for p in papers if p.get("bibcode")}
    meta: dict[str, Any] = {
        "star_id": profile.star_id,
        "n_papers": len(papers),
        "mode": "offline_replay" if replay_dir or not use_grok else "live_grok",
    }
    if not papers:
        meta["note"] = "no papers"
        return profile, meta

    content_text = ""
    if use_grok and _network_allowed():
        try:
            grok = query_grok(
                {
                    "star_id": profile.star_id,
                    "common_name": profile.common_name,
                    "class": profile.class_,
                    "spectral_type": profile.spectral_type,
                },
                papers,
                api_key=settings.xai_api_key,
            )
            content_text = str(grok.get("content_text") or "")
        except LiteratureBuildError as exc:
            logger.warning("Grok refresh failed for %s: %s", profile.star_id, exc)
            meta["error"] = str(exc)
            return profile, meta
    else:
        # Replay-only path: prefer recorded Grok JSON when present.
        slug = star_id_slug(profile.star_id)
        for base in (replay_dir, FIXTURES_LITERATURE, MONITOR_FIXTURES):
            if base is None:
                continue
            grok_path = Path(base) / slug / "grok_response.json"
            if grok_path.is_file():
                payload = json.loads(grok_path.read_text(encoding="utf-8"))
                if "choices" in payload:
                    content_text = str(
                        ((payload.get("choices") or [{}])[0].get("message") or {}).get(
                            "content"
                        )
                        or ""
                    )
                else:
                    content_text = str(
                        payload.get("content_text")
                        or payload.get("content")
                        or json.dumps(payload)
                    )
                meta["mode"] = "offline_replay"
                break
        if not content_text:
            # Keep existing lit; mark review time only.
            meta["note"] = "no replay Grok payload; inventory lit unchanged"
            reviewed = _utcnow_iso()
            return profile.model_copy(update={"last_reviewed_utc": reviewed}), meta

    from backend.literature.build_index import _extract_json_object

    try:
        parsed = _extract_json_object(content_text)
    except Exception as exc:  # noqa: BLE001
        meta["error"] = f"parse_failed: {exc}"
        return profile, meta

    lit = validate_literature(parsed, allowed_bibcodes=allowed)
    reviewed = _utcnow_iso()
    updated = _apply_literature_to_profile(profile, lit, reviewed_utc=reviewed)
    meta["confidence"] = lit.confidence
    meta["n_evidence"] = len(lit.evidence)
    return updated, meta


def monitor_publications(
    *,
    inventory_path: Path | None = None,
    watermark_path: Path | None = None,
    replay_dir: Path | None = None,
    star_ids: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scan for new publications and refresh affected inventory rows.

    Returns a status summary. Network ADS/Grok only when keys are set and
    ``USE_CACHED_STREAM=False``. Otherwise uses replay fixtures / dry-run.
    """
    inv_path = Path(inventory_path) if inventory_path else INVENTORY_PATH
    if not inv_path.is_file():
        build_inventory(out_path=inv_path)

    wm_path = Path(watermark_path) if watermark_path else WATERMARK_PATH
    watermark = _load_watermark(wm_path)
    seen: dict[str, Any] = dict(watermark.get("seen_bibcodes") or {})

    inventory = load_inventory(inv_path)
    targets = list(inventory.values())
    if star_ids:
        want = set(star_ids)
        targets = [p for p in targets if p.star_id in want]

    live = _network_allowed() and replay_dir is None
    updates: list[dict[str, Any]] = []
    refreshed = 0

    for profile in targets:
        star_blob = {
            "star_id": profile.star_id,
            "common_name": profile.common_name,
            "class": profile.class_,
            "spectral_type": profile.spectral_type,
        }
        if live:
            try:
                ads = query_ads(
                    star_blob,
                    token=settings.ads_api_token,
                    rows=10,
                )
                arxiv = query_arxiv(star_blob, max_results=10)
                papers = merge_papers(ads, arxiv)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ADS/arXiv poll failed for %s: %s", profile.star_id, exc)
                continue
        else:
            papers = _papers_for_star_replay(
                profile.star_id, Path(replay_dir or FIXTURES_LITERATURE)
            )

        fresh = _new_bibcodes(papers, seen=seen, star_id=profile.star_id)
        # First run: record all bibcodes without forcing a rescore unless requested.
        prior = seen.get(profile.star_id)
        if prior is None and not dry_run:
            seen[profile.star_id] = sorted(
                {str(p["bibcode"]) for p in papers if p.get("bibcode")}
            )
            # Still refresh stars that have replay papers and empty/zero inventory lit.
            if profile.lit.confidence <= 0 and papers:
                fresh = papers
            else:
                continue

        if not fresh and prior is not None:
            continue

        use_papers = fresh or papers
        if dry_run:
            updates.append(
                {
                    "star_id": profile.star_id,
                    "n_new_bibcodes": len(fresh),
                    "bibcodes": [p.get("bibcode") for p in fresh][:10],
                    "dry_run": True,
                }
            )
            continue

        updated, meta = refresh_star_from_papers(
            profile,
            use_papers,
            use_grok=live,
            replay_dir=Path(replay_dir) if replay_dir else None,
        )
        upsert_profile(updated, path=inv_path)
        bibs = sorted({str(p["bibcode"]) for p in papers if p.get("bibcode")})
        seen[profile.star_id] = sorted(set(seen.get(profile.star_id) or []) | set(bibs))
        meta["n_new_bibcodes"] = len(fresh)
        updates.append(meta)
        refreshed += 1

    now = _utcnow_iso()
    if not dry_run:
        watermark["last_check_utc"] = now
        watermark["seen_bibcodes"] = seen
        hist = list(watermark.get("updates") or [])
        hist.extend(updates)
        watermark["updates"] = hist[-50:]
        _save_watermark(watermark, wm_path)

    return {
        "checked_utc": now,
        "live_network": live,
        "dry_run": dry_run,
        "n_targets": len(targets),
        "n_refreshed": refreshed,
        "updates": updates,
        "inventory": inventory_status(inv_path),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.progenitors.monitor",
        description="Monitor ADS/arXiv for new progenitor publications.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report new bibcodes without writing inventory.",
    )
    parser.add_argument(
        "--replay-dir",
        type=Path,
        default=None,
        help="Use recorded ADS/Grok fixtures (no network).",
    )
    parser.add_argument(
        "--star",
        action="append",
        default=None,
        help="Limit to star_id (repeatable).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = monitor_publications(
        dry_run=bool(args.dry_run),
        replay_dir=args.replay_dir,
        star_ids=args.star,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
