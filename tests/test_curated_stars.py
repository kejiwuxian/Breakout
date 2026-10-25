"""Validation gate for the hand-reviewed BREAKOUT stellar literature index.

Run from the repository root:
    python -m pytest -q tests/test_curated_stars.py

The tests never mutate curated_stars.json. Failures identify entries for manual review.
"""

import json
import math
from pathlib import Path

import pytest


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "stars" / "curated_stars.json"
ALLOWED_CLASSES = {"RSG", "BSG", "YSG", "WR", "LBV"}
REQUIRED_STAR_FIELDS = {
    "star_id",
    "ra_deg",
    "dec_deg",
    "class",
    "spectral_type",
    "distance_kpc",
    "extinction_av_mag",
    "lit",
    "sources",
    "uncertain",
    "simulated",
}
REQUIRED_LIT_FIELDS = {
    "mass_loss", "variability", "evolved_stage", "confidence", "evidence"
}


def _read_stars():
    assert DATA_FILE.is_file(), f"Missing catalog: {DATA_FILE}"
    with DATA_FILE.open(encoding="utf-8") as handle:
        stars = json.load(handle)
    assert isinstance(stars, list), "Catalog root must be a JSON array"
    return stars


def _star_label(star, index):
    if isinstance(star, dict):
        return f"star[{index}] ({star.get('star_id') or '<missing star_id>'})"
    return f"star[{index}] ({type(star).__name__})"


def _walk_numbers(value, path=""):
    """Yield numeric value paths; booleans are flags, not measured numbers."""
    if isinstance(value, dict):
        for key, child in value.items():
            if path == "" and key in {"sources", "uncertain"}:
                continue
            next_path = f"{path}.{key}" if path else key
            yield from _walk_numbers(child, next_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_numbers(child, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield path, value


def test_star_count():
    stars = _read_stars()
    assert 30 <= len(stars) <= 50, f"Expected 30–50 stars; found {len(stars)}"


def test_required_fields_and_ranges():
    errors = []
    for index, star in enumerate(_read_stars()):
        label = _star_label(star, index)
        if not isinstance(star, dict):
            errors.append(f"{label}: expected a JSON object")
            continue
        for field in sorted(REQUIRED_STAR_FIELDS - star.keys()):
            errors.append(f"{label}: missing required field {field}")
        if not isinstance(star.get("star_id"), str) or not star["star_id"].strip():
            errors.append(f"{label}: star_id must be a nonempty SIMBAD identifier")
        if star.get("class") not in ALLOWED_CLASSES:
            errors.append(f"{label}: invalid class {star.get('class')!r}")
        for field, low, high, inclusive_high in (
            ("ra_deg", 0, 360, False),
            ("dec_deg", -90, 90, True),
        ):
            v = star.get(field)
            if (not isinstance(v, (int, float)) or isinstance(v, bool)
                    or not math.isfinite(v)
                    or not (low <= v <= high if inclusive_high else low <= v < high)):
                edge = "≤" if inclusive_high else "<"
                errors.append(f"{label}: {field}={v!r} must satisfy {low} ≤ value {edge} {high}")
        lit = star.get("lit")
        if not isinstance(lit, dict):
            errors.append(f"{label}: lit must be a JSON object")
        else:
            for field in sorted(REQUIRED_LIT_FIELDS - lit.keys()):
                errors.append(f"{label}: lit missing required field {field}")
            for field in ("mass_loss", "variability", "evolved_stage", "confidence"):
                item = lit.get(field)
                if not isinstance(item, dict) or not {"value", "reason"}.issubset(item):
                    errors.append(f"{label}: lit.{field} requires value and reason")
            confidence = lit.get("confidence")
            if isinstance(confidence, dict):
                score = confidence.get("value")
                if score is not None and (
                    not isinstance(score, (int, float)) or isinstance(score, bool)
                    or not math.isfinite(score) or not 0 <= score <= 1
                ):
                    errors.append(f"{label}: lit.confidence.value={score!r} must be null or 0..1")
            if not isinstance(lit.get("evidence"), list) or not lit.get("evidence"):
                errors.append(f"{label}: lit.evidence must be a nonempty JSON array")
        if not isinstance(star.get("sources"), dict):
            errors.append(f"{label}: sources must be a JSON object")
        if not isinstance(star.get("uncertain"), list):
            errors.append(f"{label}: uncertain must be a JSON array")
        for field in ("distance_kpc", "extinction_av_mag"):
            v = star.get(field)
            if v is not None and (
                not isinstance(v, (int, float)) or isinstance(v, bool)
                or not math.isfinite(v)
            ):
                errors.append(f"{label}: {field}={v!r} must be null or a finite number")
        if "simulated" in star and not isinstance(star["simulated"], bool):
            errors.append(f"{label}: simulated must be a boolean")
    assert not errors, "\n" + "\n".join(errors)


def test_every_evidence_has_a_bibcode():
    errors = []
    for index, star in enumerate(_read_stars()):
        if not isinstance(star, dict) or not isinstance(star.get("lit"), dict):
            continue
        for evidence_index, item in enumerate(star["lit"].get("evidence", [])):
            label = f"{_star_label(star, index)} lit.evidence[{evidence_index}]"
            if not isinstance(item, dict):
                errors.append(f"{label}: evidence must be a JSON object")
            elif not isinstance(item.get("bibcode"), str) or not item["bibcode"].strip():
                errors.append(f"{label}: missing bibcode (found {item.get('bibcode')!r})")
            if isinstance(item, dict) and (
                not isinstance(item.get("claim"), str) or not item["claim"].strip()
            ):
                errors.append(f"{label}: missing evidence claim")
    assert not errors, "\n" + "\n".join(errors)


def test_every_nonnull_number_has_a_source():
    errors = []
    for index, star in enumerate(_read_stars()):
        if not isinstance(star, dict):
            continue
        sources = star.get("sources")
        if not isinstance(sources, dict):
            continue  # already covered in the schema test
        for field_path, value in _walk_numbers(star):
            url = sources.get(field_path)
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                errors.append(
                    f"{_star_label(star, index)}: {field_path}={value!r} lacks "
                    f"sources[{field_path!r}] URL"
                )
    assert not errors, "\n" + "\n".join(errors)
