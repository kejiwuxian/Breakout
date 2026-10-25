"""Apify Actor entry: ATel + arXiv discovery feed for BREAKOUT stars.

Run locally (from this directory, with Apify CLI):
    apify run --input-file=storage/key_value_stores/default/INPUT.json

Or without the CLI (stdlib fallback used in tests):
    python -m src.main --input path/to/input.json --out path/to/dataset.jsonl

Items are public notices/preprints with real URLs. They are NOT literature
claims — BREAKOUT still requires an ADS bibcode before a claim enters the
ranked index.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Allow `python -m src.main` from the actor root.
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fetchers import collect_items  # noqa: E402

logger = logging.getLogger("breakout.apify.actor")


def _normalize_input(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(raw or {})
    stars = data.get("stars") or []
    if not isinstance(stars, list):
        raise ValueError("input.stars must be a list")
    sources = data.get("sources") or ["atel", "arxiv"]
    if not isinstance(sources, list) or not sources:
        sources = ["atel", "arxiv"]
    max_per = int(data.get("max_per_source") or 10)
    max_per = max(1, min(50, max_per))
    return {"stars": stars, "sources": sources, "max_per_source": max_per}


def run_local(input_data: dict[str, Any], http_get: Any = None) -> list[dict[str, Any]]:
    """Pure local run used by tests and the CLI fallback (no Apify SDK)."""
    cfg = _normalize_input(input_data)
    items: list[dict[str, Any]] = []
    for star in cfg["stars"]:
        if not isinstance(star, dict) or not str(star.get("star_id") or "").strip():
            logger.warning("skipping star without star_id: %r", star)
            continue
        items.extend(
            collect_items(
                star,
                cfg["sources"],
                max_per_source=cfg["max_per_source"],
                http_get=http_get,
            )
        )
    return items


async def run_apify() -> None:
    """Apify platform / `apify run` entry when the SDK is installed."""
    from apify import Actor  # type: ignore[import-untyped]

    async with Actor:
        raw = await Actor.get_input() or {}
        items = run_local(raw)
        for item in items:
            await Actor.push_data(item)
        await Actor.set_value(
            "OUTPUT_SUMMARY",
            {"n_items": len(items), "simulated": False},
        )
        Actor.log.info("Pushed %s literature items (all simulated=false)", len(items))


def _cli(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="BREAKOUT star literature actor (local)")
    parser.add_argument("--input", type=Path, required=True, help="Actor input JSON")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional JSONL dataset path (default: print JSON array)",
    )
    args = parser.parse_args(argv)
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    items = run_local(raw)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"wrote {len(items)} item(s) to {args.out}")
    else:
        print(json.dumps(items, indent=2, ensure_ascii=False))
    return 0


def main() -> None:
    # Prefer Apify SDK when present (platform / `apify run`); else local CLI.
    if any(arg.startswith("--input") for arg in sys.argv[1:]):
        raise SystemExit(_cli())
    try:
        import apify  # noqa: F401
    except ImportError:
        raise SystemExit(
            "apify package not installed. Use: python -m src.main --input INPUT.json"
        )
    asyncio.run(run_apify())


if __name__ == "__main__":
    main()
