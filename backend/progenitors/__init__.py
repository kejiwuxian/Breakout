"""Grok-maintained supernova-progenitor inventory and runtime ranking.

Offline inventory consolidates curated catalogs + literature index into
comparable SN-potential profiles (position, life expectancy, composition,
confidence). A publication monitor refreshes scores when new ADS/arXiv
papers appear. At neutrino-event runtime, AOI candidates are enriched from
the inventory and ranked (live Grok when keys + network are allowed;
deterministic offline fallback otherwise).
"""

from __future__ import annotations

from backend.progenitors.inventory import (
    INVENTORY_PATH,
    ProgenitorProfile,
    build_inventory,
    load_inventory,
    load_inventory_rows,
)
from backend.progenitors.rank_runtime import rank_with_grok

__all__ = [
    "INVENTORY_PATH",
    "ProgenitorProfile",
    "build_inventory",
    "load_inventory",
    "load_inventory_rows",
    "rank_with_grok",
]
