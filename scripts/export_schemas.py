#!/usr/bin/env python3
"""Export Alert, SkyMap, and CandidateScore JSON Schema to docs/schemas/.

Run: python scripts/export_schemas.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.schemas import CONTRACT_VERSION, export_json_schemas  # noqa: E402

OUT_DIR = ROOT / "docs" / "schemas"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    schemas = export_json_schemas()
    for name, schema in schemas.items():
        schema = dict(schema)
        schema["$id"] = f"https://breakout.local/schemas/{name}.schema.json"
        schema["title"] = f"BREAKOUT {name} ({CONTRACT_VERSION})"
        path = OUT_DIR / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
