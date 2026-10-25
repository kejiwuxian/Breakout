"""Phase 2.3 — Apify literature actor bridge (OFFLINE only).

When APIFY_ENABLED=False (default): no ApifyClient import, no network, no-op.
When True: ``ApifyClient(APIFY_TOKEN).actor(APIFY_ACTOR_ID).call(run_input=...)``
with stars from curated_stars.json, then save ``data/index/apify/<star_id>.json``.

Failures are logged; callers on the offline path must not let this break the
MVP trigger loop. Ranked claims still require ADS bibcodes in build_index.
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
    seen: set[str] = set()
    out: list[str] = []
    for name in aliases:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def stars_to_run_input(
    stars: list[dict[str, Any]],
    *,
    sources: list[str] | None = None,
    max_items_per_star: int = 20,
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
        "max_items_per_star": int(max_items_per_star),
    }


def write_star_items(
    star_id: str,
    items: list[dict[str, Any]],
    *,
    out_dir: Path | None = None,
) -> Path:
    path = apify_path_for(star_id, out_dir=out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = [dict(item) for item in items if isinstance(item, dict)]
    for item in clean:
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


def load_star_items(star_id: str, *, out_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load previously saved Apify items for a star (empty if missing)."""
    path = apify_path_for(star_id, out_dir=out_dir)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Corrupt Apify index file: %s", path)
        return []
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict)]


def run_apify_actor(
    stars: list[dict[str, Any]],
    *,
    sources: list[str] | None = None,
    max_items_per_star: int = 20,
    token: str | None = None,
    actor_id: str | None = None,
) -> list[dict[str, Any]]:
    """Call Apify cloud. Imports ApifyClient only when invoked (flag-on path)."""
    from apify_client import ApifyClient  # type: ignore[import-untyped]

    tok = (token if token is not None else settings.apify_token).strip()
    aid = (actor_id if actor_id is not None else settings.apify_actor_id).strip()
    if not tok:
        raise RuntimeError("APIFY_TOKEN is required when APIFY_ENABLED=True")
    if not aid:
        aid = DEFAULT_ACTOR_ID

    client = ApifyClient(tok)
    run_input = stars_to_run_input(
        stars, sources=sources, max_items_per_star=max_items_per_star
    )
    logger.info("Apify actor %s call for %s star(s)", aid, len(run_input["stars"]))
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
    sources: list[str] | None = None,
    max_items_per_star: int = 20,
) -> dict[str, Path]:
    """Run the Apify actor and write per-star JSON. No-op when flag is off.

    Never raises into the MVP trigger path — logs and returns {}.
    """
    if not is_enabled():
        logger.info("APIFY_ENABLED=False; skipping Apify literature fetch")
        return {}

    try:
        items = run_apify_actor(
            stars,
            sources=sources,
            max_items_per_star=max_items_per_star,
        )
        written: dict[str, Path] = {}
        for star_id, star_items in group_items_by_star(items).items():
            written[star_id] = write_star_items(star_id, star_items, out_dir=out_dir)
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
        description="OFFLINE: ApifyClient → data/index/apify/<star_id>.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=APIFY_INDEX_DIR,
        help="Output directory for per-star JSON.",
    )
    parser.add_argument(
        "--max-items-per-star",
        type=int,
        default=20,
        help="Passed through to the actor as max_items_per_star.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional cap on number of curated stars (0 = all).",
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
    if args.limit and args.limit > 0:
        stars = stars[: args.limit]
    written = fetch_and_store(
        stars,
        out_dir=args.out_dir,
        max_items_per_star=args.max_items_per_star,
    )
    print(f"wrote Apify index for {len(written)} star(s) under {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
