"""Apify Actor stub from python-start — literature fetch implemented next commit."""

from __future__ import annotations

from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        Actor.log.info("Stub actor received input keys: %s", sorted(actor_input.keys()))
        Actor.log.warning(
            "Literature fetch not wired yet — see follow-up commit for ATel/arXiv."
        )
