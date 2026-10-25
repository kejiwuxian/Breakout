"""OFFLINE: Grok reads ADS/arXiv once per star → index.parquet.

Every literature claim MUST store an ADS bibcode; no bibcode, no claim.
Not called on the trigger path when USE_CACHED_STREAM=True.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import ROOT

INDEX_PATH = ROOT / "backend" / "literature" / "index.parquet"
RAW_DIR = ROOT / "data" / "index" / "raw"

# Seed evidence for Betelgeuse: claims paraphrased from published ADS abstracts only.
# Ranking scores (0..1) are offline index features for CandidateScore, not
# published observables. Bibcodes and claim text are real.
BETELGEUSE_SEED: dict[str, Any] = {
    "star_id": "* alf Ori",
    "mass_loss": 0.85,
    "variability": 0.9,
    "evolved_stage": 0.95,
    "confidence": 0.9,
    "evidence": [
        {
            "bibcode": "2020ApJ...902...63J",
            "claim": (
                "Joyce et al. 2020 derive an independent distance of 168 pc "
                "(+27/−15 pc) and present-day mass 16.5–19 M☉ for Betelgeuse, "
                "placing it in early core helium-burning on the RSG branch."
            ),
        },
        {
            "bibcode": "2017AJ....154...11H",
            "claim": (
                "Harper et al. 2017 report a combined radio+Hipparcos parallax "
                "solution of 4.51 ± 0.80 mas, corresponding to a nominal distance "
                "of 222 pc (+48/−34 pc)."
            ),
        },
        {
            "bibcode": "2016ApJ...819....7D",
            "claim": (
                "Dolan et al. 2016 evolutionary tracks suggest a best progenitor "
                "mass estimate of 20 (+5/−3) M☉ and age 8.0–8.5 Myr for Betelgeuse."
            ),
        },
    ],
}


def write_index_rows(
    rows: list[dict[str, Any]],
    *,
    out_path: Path = INDEX_PATH,
) -> Path:
    """Write literature index rows to parquet (evidence stored as evidence_json)."""
    import pandas as pd

    records: list[dict[str, Any]] = []
    for row in rows:
        evidence = row.get("evidence") or []
        records.append(
            {
                "star_id": str(row["star_id"]),
                "mass_loss": float(row.get("mass_loss", 0.0) or 0.0),
                "variability": float(row.get("variability", 0.0) or 0.0),
                "evolved_stage": float(row.get("evolved_stage", 0.0) or 0.0),
                "confidence": float(row.get("confidence", 0.0) or 0.0),
                "evidence_json": json.dumps(evidence),
            }
        )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_parquet(out_path, index=False)
    return out_path


def seed_betelgeuse_index(*, out_path: Path = INDEX_PATH) -> Path:
    """Write the Betelgeuse ADS seed index (no network)."""
    return write_index_rows([BETELGEUSE_SEED], out_path=out_path)


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
    raise NotImplementedError(
        "Live ADS/Grok build_index is filled in a later prompt; "
        "use seed_betelgeuse_index() for the Scenario A offline seed."
    )
