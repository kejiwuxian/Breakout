#!/usr/bin/env python3
"""Build the compact all-sky background star catalog for the SVG skymap.

Source
------
Yale Bright Star Catalogue, 5th Revised Ed. (Hoffleit & Warren 1991),
CDS/VizieR catalogue ``V/50`` — the same Hoffleit+1991 dataset underlying
NASA HEASARC ``BSC5P`` (https://heasarc.gsfc.nasa.gov/W3Browse/star-catalog/bsc5p.html).

Default download (HTTPS, redistributable CDS archive)::

    https://cdsarc.cds.unistra.fr/ftp/cats/V/50/catalog.gz

Magnitude cut
-------------
Keep stars with a finite visual magnitude ``V <= VMAX`` (default **6.5**,
matching the classical BSC bright-star limit). Empty / non-stellar rows
without J2000 coordinates are dropped.

Output (committed for offline cold start)
-----------------------------------------
- ``data/stars/sky_background.json`` — compact star rows for ``/api/sky/base``
- ``data/stars/sky_background_meta.json`` — provenance / license / counts

Usage::

    python scripts/build_sky_background_catalog.py
    python scripts/build_sky_background_catalog.py --vmax 6.0
    python scripts/build_sky_background_catalog.py --from-file /tmp/catalog.dat
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "data" / "stars" / "sky_background.json"
OUT_META = ROOT / "data" / "stars" / "sky_background_meta.json"

CDS_URL = "https://cdsarc.cds.unistra.fr/ftp/cats/V/50/catalog.gz"
HEASARC_BSC5P = "https://heasarc.gsfc.nasa.gov/W3Browse/star-catalog/bsc5p.html"
VIZIER_V50 = "https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=V/50"
BIBCODE = "1991bsc..book.....H"
ATTRIBUTION = (
    "Bright Star Catalogue, 5th Revised Ed. (Hoffleit+, 1991). "
    "CDS catalogue V/50; NASA HEASARC BSC5P is derived from the same edition. "
    "Redistributed here as a compact magnitude-limited subset for offline SVG rendering."
)

DEFAULT_VMAX = 6.5


def _parse_float(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_int(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def sexagesimal_ra_to_deg(h: int, m: int, s: float) -> float:
    return (h + m / 60.0 + s / 3600.0) * 15.0


def sexagesimal_dec_to_deg(sign: str, d: int, m: int, s: float) -> float:
    val = d + m / 60.0 + s / 3600.0
    if sign.strip() == "-":
        val = -val
    return val


def parse_catalog_line(line: str) -> dict[str, Any] | None:
    """Parse one fixed-width V/50 ``catalog`` row into a compact star dict."""
    if len(line) < 107:
        return None
    hr = _parse_int(line[0:4])
    if hr is None:
        return None
    name = line[4:14].strip() or None

    rah = _parse_int(line[75:77])
    ram = _parse_int(line[77:79])
    ras = _parse_float(line[79:83])
    des = line[83:84]
    ded = _parse_int(line[84:86])
    dem = _parse_int(line[86:88])
    dess = _parse_float(line[88:90])
    if None in (rah, ram, ras, ded, dem, dess) or not des.strip():
        return None

    vmag = _parse_float(line[102:107])
    ra = sexagesimal_ra_to_deg(rah, ram, ras) % 360.0
    dec = max(-90.0, min(90.0, sexagesimal_dec_to_deg(des, ded, dem, dess)))

    row: dict[str, Any] = {
        "star_id": f"HR{hr}",
        "ra_deg": round(ra, 6),
        "dec_deg": round(dec, 6),
    }
    if name:
        row["common_name"] = name
    if vmag is not None:
        row["vmag"] = round(vmag, 2)
    return row


def iter_catalog_lines(path: Path) -> list[str]:
    raw = path.read_bytes()
    if path.suffix == ".gz" or raw[:2] == b"\x1f\x8b":
        text = gzip.decompress(raw).decode("latin-1")
    else:
        text = raw.decode("latin-1")
    return [ln.rstrip("\n") for ln in text.splitlines() if ln.strip()]


def download_catalog(url: str, dest: Path) -> bytes:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "breakout-sky-background-builder/1.0"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 — trusted CDS URL
        data = resp.read()
    dest.write_bytes(data)
    return data


def build_stars(
    lines: list[str],
    *,
    vmax: float,
) -> list[dict[str, Any]]:
    stars: list[dict[str, Any]] = []
    for line in lines:
        row = parse_catalog_line(line)
        if row is None:
            continue
        v = row.get("vmag")
        if v is None or float(v) > vmax:
            continue
        stars.append(row)
    stars.sort(key=lambda r: (float(r.get("vmag", 99.0)), r["star_id"]))
    return stars


def coverage_stats(stars: list[dict[str, Any]]) -> dict[str, Any]:
    if not stars:
        return {"n": 0}
    ras = [float(s["ra_deg"]) for s in stars]
    decs = [float(s["dec_deg"]) for s in stars]
    vmags = [float(s["vmag"]) for s in stars if s.get("vmag") is not None]
    # 12×6 RA/Dec bins — expect most occupied for a bright all-sky catalog.
    bins = set()
    for ra, dec in zip(ras, decs, strict=False):
        i = min(11, int(ra / 30.0))
        j = min(5, int((dec + 90.0) / 30.0))
        bins.add((i, j))
    return {
        "n": len(stars),
        "ra_min_deg": round(min(ras), 4),
        "ra_max_deg": round(max(ras), 4),
        "dec_min_deg": round(min(decs), 4),
        "dec_max_deg": round(max(decs), 4),
        "vmag_min": round(min(vmags), 2) if vmags else None,
        "vmag_max": round(max(vmags), 2) if vmags else None,
        "sky_bins_occupied_of_72": len(bins),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--url",
        default=CDS_URL,
        help="HTTPS URL of V/50 catalog.gz (default: CDS archive)",
    )
    ap.add_argument(
        "--from-file",
        type=Path,
        default=None,
        help="Use a local catalog.dat / catalog.gz instead of downloading",
    )
    ap.add_argument(
        "--vmax",
        type=float,
        default=DEFAULT_VMAX,
        help=f"Keep stars with V <= this (default {DEFAULT_VMAX})",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=OUT_JSON,
        help="Output JSON path",
    )
    ap.add_argument(
        "--meta-out",
        type=Path,
        default=OUT_META,
        help="Output metadata JSON path",
    )
    args = ap.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="bsc5-") as tmp:
        tmp_path = Path(tmp)
        if args.from_file is not None:
            src = Path(args.from_file)
            if not src.is_file():
                print(f"error: file not found: {src}", file=sys.stderr)
                return 2
            raw = src.read_bytes()
            local = tmp_path / src.name
            local.write_bytes(raw)
            source_url = f"file://{src.resolve()}"
        else:
            local = tmp_path / "catalog.gz"
            print(f"Downloading {args.url} …")
            raw = download_catalog(args.url, local)
            source_url = args.url

        digest = hashlib.sha256(raw).hexdigest()
        lines = iter_catalog_lines(local)
        stars = build_stars(lines, vmax=float(args.vmax))
        stats = coverage_stats(stars)

        payload = {
            "schema": "breakout.sky_background.v1",
            "frame": "ICRS",
            "epoch": "J2000",
            "catalog": "Yale Bright Star Catalogue 5th Revised Ed. (Hoffleit+ 1991)",
            "vizier": "V/50",
            "nasa_heasarc": "BSC5P",
            "bibcode": BIBCODE,
            "vmax": float(args.vmax),
            "n_stars": len(stars),
            "stars": stars,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        meta = {
            "path": str(args.out.relative_to(ROOT)),
            "built_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_url": source_url,
            "source_sha256": digest,
            "cds_vizier": VIZIER_V50,
            "nasa_heasarc_bsc5p": HEASARC_BSC5P,
            "bibcode": BIBCODE,
            "attribution": ATTRIBUTION,
            "license_note": (
                "Astronomical catalogue data from CDS/VizieR; redistributed as a "
                "compact derived table for BREAKOUT offline rendering. Cite Hoffleit "
                "& Warren 1991 (bibcode 1991bsc..book.....H) and CDS V/50."
            ),
            "vmax": float(args.vmax),
            "n_raw_rows": len(lines),
            "coverage": stats,
            "rebuild": "python scripts/build_sky_background_catalog.py",
        }
        args.meta_out.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print(
        f"Wrote {args.out} ({stats['n']} stars, V<={args.vmax}, "
        f"bins={stats.get('sky_bins_occupied_of_72')}/72)"
    )
    print(f"Wrote {args.meta_out}")
    if stats["n"] < 1000:
        print("warning: expected thousands of stars; check parse / vmax", file=sys.stderr)
        return 1
    if int(stats.get("sky_bins_occupied_of_72") or 0) < 50:
        print("warning: sparse sky coverage", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
