"""OFFLINE: Grok reads ADS/arXiv once per star → index.parquet.

Every literature claim MUST store an ADS bibcode; no bibcode, no claim.
Not called on the trigger path when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.config import ROOT

INDEX_PATH = ROOT / "backend" / "literature" / "index.parquet"
RAW_DIR = ROOT / "data" / "index" / "raw"


def build_index(
    stars: list[dict[str, Any]],
    *,
    out_path: Path = INDEX_PATH,
    raw_dir: Path = RAW_DIR,
) -> Path:
    """Query ADS/arXiv via Grok offline and write structured scores + evidence.

    Requires ADS_API_TOKEN and XAI_API_KEY. Writes per-star JSON under
    data/index/raw/<star_id>.json and the parquet index.
    """
    raise NotImplementedError("build_index is filled in a later prompt.")
