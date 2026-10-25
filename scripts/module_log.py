#!/usr/bin/env python3
"""Append a module-scoped commit note to docs/prompt-log.md.

Usage:
  python scripts/module_log.py --who Light --module ingest/cache --note "replay stub"
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "docs" / "prompt-log.md"
PT = ZoneInfo("America/Los_Angeles")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--who", required=True, help="Team member name")
    parser.add_argument("--module", required=True, help="Module path or label")
    parser.add_argument("--note", required=True, help="What the prompt did")
    args = parser.parse_args()

    when = datetime.now(timezone.utc).astimezone(PT).strftime("%a %-d %b %Y, %-I:%M %p PT")
    row = f"| {when} | {args.who} | {args.module}: {args.note} | logged |\n"

    text = LOG.read_text(encoding="utf-8") if LOG.is_file() else (
        "# Cursor / Grok Bot prompt log\n\n"
        "| When (PT) | Who | Prompt / task | Outcome |\n"
        "| --- | --- | --- | --- |\n"
    )
    if not text.endswith("\n"):
        text += "\n"
    # Insert before trailing Notes section if present.
    marker = "\nNotes:\n"
    if marker in text:
        head, tail = text.split(marker, 1)
        text = head.rstrip("\n") + "\n" + row + marker + tail
    else:
        text = text + row
    LOG.write_text(text, encoding="utf-8")
    print(f"appended to {LOG.relative_to(ROOT)}: {row.strip()}")


if __name__ == "__main__":
    main()
