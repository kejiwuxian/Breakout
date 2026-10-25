"""Phase 2.3 — Apify literature actor bridge (offline only).

When APIFY_ENABLED=False (default): no Apify client import, no network, no-op.
When True: start the actor (or run local fetchers), write
``data/index/apify/<star_slug>.json``. Failures are logged; callers must not
let this block or fail the MVP trigger path.

Apify items are discovery feeds. Ranked literature claims still require ADS
bibcodes in ``backend/literature/build_index.py``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

from backend.config import ROOT, settings

logger = logging.getLogger("breakout.integrations.apify_literature")

APIFY_INDEX_DIR = ROOT / "data" / "index" / "apify"
ACTOR_ROOT = ROOT / "actors" / "breakout-star-literature"
DEFAULT_ACTOR_ID = "breakout-star-literature"


def star_id_slug(star_id: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", str(star_id).strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._") or "unknown"
    return cleaned[:180]


def apify_path_for(star_id: str, out_dir: Path | None = None) -> Path:
    base = Path(out_dir) if out_dir is not None else APIFY_INDEX_DIR
    return base / f"{star_id_slug(star_id)}.json"


def is_enabled() -> bool:
    return bool(settings.apify_enabled)


def _aliases_for_star(star: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for key in ("common_name", "name", "display_name"):
        val = star.get(key)
        if val and str(val).strip():
            aliases.append(str(val).strip())
    extra = star.get("aliases")
    if isinstance(extra, list):
        for item in extra:
            if item and str(item).strip():
                aliases.append(str(item).strip())
    # Dedup preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for name in aliases:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def stars_to_actor_input(
    stars: list[dict[str, Any]],
    *,
    sources: list[str] | None = None,
    max_per_source: int = 10,
) -> dict[str, Any]:
    payload_stars: list[dict[str, Any]] = []
    for star in stars:
        star_id = str(star.get("star_id") or "").strip()
        if not star_id:
            continue
        payload_stars.append(
            {
                "star_id": star_id,
                "aliases": _aliases_for_star(star),
            }
        )
    return {
        "stars": payload_stars,
        "sources": sources or ["atel", "arxiv"],
        "max_per_source": max_per_source,
    }


def write_star_items(
    star_id: str,
    items: list[dict[str, Any]],
    *,
    out_dir: Path | None = None,
) -> Path:
    """Write one star's Apify items. Does not invent rows."""
    path = apify_path_for(star_id, out_dir=out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = [dict(item) for item in items if isinstance(item, dict)]
    for item in clean:
        # Force honest labeling: only True if the payload already said so.
        if "simulated" not in item:
            item["simulated"] = False
        item.setdefault("star_id", star_id)
    payload = {
        "star_id": star_id,
        "n_items": len(clean),
        "simulated": any(bool(i.get("simulated")) for i in clean),
        "items": clean,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def group_items_by_star(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("star_id") or "").strip()
        if not sid:
            continue
        grouped.setdefault(sid, []).append(item)
    return grouped


def run_local_fetchers(
    stars: list[dict[str, Any]],
    *,
    sources: list[str] | None = None,
    max_per_source: int = 10,
    http_get: Any = None,
) -> list[dict[str, Any]]:
    """Run the actor fetchers in-process (no Apify cloud). Used by tests + offline."""
    import importlib.util

    actor_src = ACTOR_ROOT / "src"
    fetchers_path = actor_src / "fetchers.py"
    spec = importlib.util.spec_from_file_location(
        "breakout_apify_actor_fetchers", fetchers_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load actor fetchers from {fetchers_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    payload = stars_to_actor_input(
        stars, sources=sources, max_per_source=max_per_source
    )
    items: list[dict[str, Any]] = []
    for star in payload["stars"]:
        items.extend(
            mod.collect_items(
                star,
                payload["sources"],
                max_per_source=payload["max_per_source"],
                http_get=http_get,
            )
        )
    return items


def run_apify_cloud(
    stars: list[dict[str, Any]],
    *,
    sources: list[str] | None = None,
    max_per_source: int = 10,
    token: str | None = None,
    actor_id: str | None = None,
) -> list[dict[str, Any]]:
    """Start the Apify actor via API. Imports ApifyClient only when called."""
    from apify_client import ApifyClient  # type: ignore[import-untyped]

    tok = (token if token is not None else settings.apify_token).strip()
    aid = (actor_id if actor_id is not None else settings.apify_actor_id).strip()
    if not tok:
        raise RuntimeError("APIFY_TOKEN is required when APIFY_ENABLED=True (cloud run)")
    if not aid:
        aid = DEFAULT_ACTOR_ID
    client = ApifyClient(tok)
    run_input = stars_to_actor_input(stars, sources=sources, max_per_source=max_per_source)
    logger.info("Starting Apify actor %s for %s star(s)", aid, len(run_input["stars"]))
    run = client.actor(aid).call(run_input=run_input)
    if not run:
        return []
    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        return []
    items: list[dict[str, Any]] = []
    for row in client.dataset(dataset_id).iterate_items():
        if isinstance(row, dict):
            items.append(row)
    return items


def fetch_and_store(
    stars: list[dict[str, Any]],
    *,
    out_dir: Path | None = None,
    prefer_cloud: bool = True,
    sources: list[str] | None = None,
    max_per_source: int = 10,
    http_get: Any = None,
) -> dict[str, Path]:
    """Fetch literature items and write per-star JSON under data/index/apify/.

    No-op when APIFY_ENABLED is False. On error logs and returns {} (never raises
    into the MVP trigger path — callers on the offline path may still re-raise).
    """
    if not is_enabled():
        logger.info("APIFY_ENABLED=False; skipping Apify literature fetch")
        return {}

    try:
        items: list[dict[str, Any]]
        use_cloud = prefer_cloud and bool(settings.apify_token.strip())
        if use_cloud:
            items = run_apify_cloud(
                stars, sources=sources, max_per_source=max_per_source
            )
        else:
            logger.info("APIFY_TOKEN empty or prefer_cloud=False; using local fetchers")
            items = run_local_fetchers(
                stars,
                sources=sources,
                max_per_source=max_per_source,
                http_get=http_get,
            )
        written: dict[str, Path] = {}
        for star_id, star_items in group_items_by_star(items).items():
            written[star_id] = write_star_items(star_id, star_items, out_dir=out_dir)
        # Also write empty shells for stars with zero hits so callers can see coverage.
        for star in stars:
            sid = str(star.get("star_id") or "").strip()
            if sid and sid not in written:
                written[sid] = write_star_items(sid, [], out_dir=out_dir)
        return written
    except Exception:
        logger.exception("Apify literature fetch failed; continuing without Apify data")
        return {}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.integrations.apify_literature",
        description="OFFLINE: run Apify star-literature actor → data/index/apify/",
    )
    parser.add_argument(
        "--curated-only",
        action="store_true",
        help="Use data/stars/curated_stars.json (default).",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Force in-process fetchers (do not call Apify cloud).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=APIFY_INDEX_DIR,
        help="Output directory for per-star JSON.",
    )
    parser.add_argument(
        "--max-per-source",
        type=int,
        default=10,
        help="Max items per source per star.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional cap on number of stars (0 = all).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_arg_parser().parse_args(argv)
    if not is_enabled():
        print(
            "APIFY_ENABLED=False — refusing to run. "
            "Set APIFY_ENABLED=True in .env for the offline Apify build."
        )
        return 2

    from backend.candidates.catalog import load_curated_stars

    stars = load_curated_stars()
    # Attach common-name aliases from curated rows when present in lit/uncertain blobs.
    # curated_stars.json may not have common_name; leave aliases empty unless present.
    if args.limit and args.limit > 0:
        stars = stars[: args.limit]
    written = fetch_and_store(
        stars,
        out_dir=args.out_dir,
        prefer_cloud=not args.local,
        max_per_source=args.max_per_source,
    )
    print(f"wrote Apify index for {len(written)} star(s) under {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
