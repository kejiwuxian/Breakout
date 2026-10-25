"""BREAKOUT Apify Actor: ATel + arXiv discovery for curated stars.

Built at Cal Hacks 13.0 from `apify create ... --template python-start`.

Input (see .actor/input_schema.json):
  stars: [{ star_id, aliases }], sources: [atel|arxiv], max_items_per_star

Each dataset item:
  { star_id, source, item_id, title, date, url, abstract_or_summary, simulated }

Only keeps hits that actually mention the star. Respects site rate limits.
These rows are discovery feeds — ranked claims still need ADS bibcodes.
"""

from __future__ import annotations

import logging
from typing import Any

from apify import Actor

from .fetchers import collect_for_star

logger = logging.getLogger("breakout.apify.actor")


def _normalize_input(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(raw or {})
    stars = data.get("stars") or []
    if not isinstance(stars, list):
        raise ValueError("input.stars must be a list")
    sources = data.get("sources") or ["atel", "arxiv"]
    if not isinstance(sources, list) or not sources:
        sources = ["atel", "arxiv"]
    # Accept legacy max_per_source as a fallback alias.
    max_items = data.get("max_items_per_star")
    if max_items is None:
        max_items = data.get("max_per_source", 20)
    max_items = max(1, min(100, int(max_items)))
    return {
        "stars": stars,
        "sources": [str(s).strip().lower() for s in sources],
        "max_items_per_star": max_items,
    }


def run_collect(
    input_data: dict[str, Any],
    *,
    http_get: Any = None,
) -> list[dict[str, Any]]:
    """Collect items (used by Actor main and unit tests)."""
    cfg = _normalize_input(input_data)
    items: list[dict[str, Any]] = []
    for star in cfg["stars"]:
        if not isinstance(star, dict) or not str(star.get("star_id") or "").strip():
            logger.warning("Skipping star without star_id: %r", star)
            continue
        star_items = collect_for_star(
            star,
            cfg["sources"],
            max_items_per_star=cfg["max_items_per_star"],
            http_get=http_get,
        )
        items.extend(star_items)
    return items


async def main() -> None:
    async with Actor:
        raw = await Actor.get_input() or {}
        cfg = _normalize_input(raw)
        Actor.log.info(
            "BREAKOUT literature actor: %s star(s), sources=%s, max_items_per_star=%s",
            len(cfg["stars"]),
            cfg["sources"],
            cfg["max_items_per_star"],
        )
        total = 0
        for star in cfg["stars"]:
            if not isinstance(star, dict) or not str(star.get("star_id") or "").strip():
                Actor.log.warning("Skipping star without star_id: %r", star)
                continue
            star_id = str(star["star_id"]).strip()
            star_items = collect_for_star(
                star,
                cfg["sources"],
                max_items_per_star=cfg["max_items_per_star"],
            )
            for item in star_items:
                await Actor.push_data(item)
                total += 1
            Actor.log.info("Star %s → %s item(s)", star_id, len(star_items))
        await Actor.set_value(
            "OUTPUT_SUMMARY",
            {"n_items": total, "simulated": False, "n_stars": len(cfg["stars"])},
        )
        Actor.log.info("Pushed %s item(s); all simulated=false", total)
