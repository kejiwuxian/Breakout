"""LCOGT RequestGroup builder (dry-run by default).

LCOGT_DRY_RUN stays True by default; nothing is submitted without a person.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.schemas import CandidateScore


def build_request_group(
    candidate: CandidateScore,
    *,
    proposal: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Build an LCO observe API RequestGroup JSON for the top candidate.

    When dry_run is True, do not call the LCO API; only return/write JSON.
    """
    raise NotImplementedError("build_request_group is filled in a later prompt.")


def write_request_group(
    request: dict[str, Any],
    *,
    alert_id: str,
    run_dir: Path,
) -> Path:
    """Write RequestGroup JSON to data/run/<alert_id>/lcogt_request.json."""
    raise NotImplementedError("write_request_group is filled in a later prompt.")
