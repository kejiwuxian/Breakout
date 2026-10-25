"""CLI: python -m backend.progenitors {refresh|monitor|status}."""

from __future__ import annotations

import argparse
import json
import sys

from backend.progenitors.inventory import build_inventory, inventory_status
from backend.progenitors.monitor import monitor_publications


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.progenitors",
        description="Progenitor inventory refresh / publication monitor / status.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_refresh = sub.add_parser("refresh", help="Rebuild inventory from curated + index.")
    p_refresh.add_argument("--out", default=None, help="Optional output parquet path.")

    p_mon = sub.add_parser("monitor", help="Poll publications and refresh affected stars.")
    p_mon.add_argument("--dry-run", action="store_true")
    p_mon.add_argument("--replay-dir", default=None)
    p_mon.add_argument("--star", action="append", default=None)

    sub.add_parser("status", help="Print inventory status JSON.")

    args = parser.parse_args(argv)

    if args.cmd == "refresh":
        from pathlib import Path

        path = build_inventory(out_path=Path(args.out) if args.out else None)
        print(json.dumps(inventory_status(path), indent=2))
        return 0

    if args.cmd == "monitor":
        from pathlib import Path

        result = monitor_publications(
            dry_run=bool(args.dry_run),
            replay_dir=Path(args.replay_dir) if args.replay_dir else None,
            star_ids=args.star,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "status":
        print(json.dumps(inventory_status(), indent=2))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
