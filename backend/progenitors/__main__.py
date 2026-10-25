"""CLI: python -m backend.progenitors {refresh|monitor|enrich-replay|status}."""

from __future__ import annotations

import argparse
import json
import sys

from backend.progenitors.inventory import build_inventory, inventory_status
from backend.progenitors.monitor import monitor_publications


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.progenitors",
        description=(
            "Progenitor inventory refresh / publication monitor / "
            "replay enrichment / status."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_refresh = sub.add_parser("refresh", help="Rebuild inventory from curated + index.")
    p_refresh.add_argument("--out", default=None, help="Optional output parquet path.")

    p_mon = sub.add_parser("monitor", help="Poll publications and refresh affected stars.")
    p_mon.add_argument("--dry-run", action="store_true")
    p_mon.add_argument("--replay-dir", default=None)
    p_mon.add_argument("--star", action="append", default=None)

    p_enrich = sub.add_parser(
        "enrich-replay",
        help=(
            "Materialize inventory-schema profiles for every AOI-ranked star "
            "in offline scenario caches (BSC5 SpType → life/composition)."
        ),
    )
    p_enrich.add_argument("--out", default=None, help="Optional enrichment parquet path.")
    p_enrich.add_argument(
        "--scenario",
        action="append",
        default=None,
        help="Scenario cache name (repeatable).",
    )

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

    if args.cmd == "enrich-replay":
        from pathlib import Path

        from backend.progenitors.enrich import build_replay_enrichment

        scenarios = tuple(args.scenario) if args.scenario else None
        kwargs: dict = {"out_path": Path(args.out) if args.out else None}
        if scenarios:
            kwargs["scenarios"] = scenarios
        path = build_replay_enrichment(**kwargs)
        meta_path = path.with_name(path.stem + "_meta.json")
        meta = (
            json.loads(meta_path.read_text(encoding="utf-8"))
            if meta_path.is_file()
            else {}
        )
        print(json.dumps({"path": str(path), **meta}, indent=2))
        return 0

    if args.cmd == "status":
        print(json.dumps(inventory_status(), indent=2))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
