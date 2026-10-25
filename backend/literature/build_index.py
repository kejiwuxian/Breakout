"""OFFLINE: Grok reads ADS/arXiv once per star → index.parquet.

Every literature claim MUST store an ADS bibcode; no bibcode, no claim.
Not called on the trigger path when USE_CACHED_STREAM=True.

Live path requires ADS_API_TOKEN and XAI_API_KEY from .env.
Tests inject recorded HTTP responses; ``--replay-dir`` rebuilds without network.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable
import httpx
import pandas as pd

from backend.config import ROOT, settings
from backend.schemas import Literature

logger = logging.getLogger("breakout.literature.build_index")

INDEX_PATH = ROOT / "backend" / "literature" / "index.parquet"
RAW_DIR = ROOT / "data" / "index" / "raw"
# Recorded ADS / arXiv / Grok payloads used to materialize raw reasoning offline.
FIXTURES_LITERATURE = ROOT / "tests" / "fixtures" / "literature"

ADS_SEARCH_URL = "https://api.adsabs.harvard.edu/v1/search/query"
ARXIV_API_URL = "https://export.arxiv.org/api/query"
XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"
XAI_MODEL_DEFAULT = "grok-2-latest"

# Default pacing between external calls (resume-safe offline build).
DEFAULT_RATE_LIMIT_S = 1.0
DEFAULT_ADS_ROWS = 20
DEFAULT_ARXIV_ROWS = 20

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

_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


HttpGet = Callable[..., httpx.Response]
HttpPost = Callable[..., httpx.Response]


class LiteratureBuildError(RuntimeError):
    """Raised when the offline literature build cannot proceed."""


def star_id_slug(star_id: str) -> str:
    """Filesystem-safe slug for raw/<slug>.json (keeps identity readable)."""
    cleaned = re.sub(r"[^\w.\-]+", "_", str(star_id).strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._") or "unknown"
    return cleaned[:180]


def raw_path_for(star_id: str, raw_dir: Path = RAW_DIR) -> Path:
    return Path(raw_dir) / f"{star_id_slug(star_id)}.json"


def write_index_rows(
    rows: list[dict[str, Any]],
    *,
    out_path: Path = INDEX_PATH,
) -> Path:
    """Write literature index rows to parquet (evidence stored as evidence_json)."""
    records: list[dict[str, Any]] = []
    for row in rows:
        evidence = row.get("evidence") or []
        if isinstance(evidence, str):
            evidence = json.loads(evidence) if evidence.strip() else []
        records.append(
            {
                "star_id": str(row["star_id"]),
                "mass_loss": float(row.get("mass_loss", 0.0) or 0.0),
                "variability": float(row.get("variability", 0.0) or 0.0),
                "evolved_stage": float(row.get("evolved_stage", 0.0) or 0.0),
                "confidence": float(row.get("confidence", 0.0) or 0.0),
                "evidence_json": json.dumps(evidence),
                "simulated": bool(row.get("simulated", False)),
            }
        )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_parquet(out_path, index=False)
    return out_path


def seed_betelgeuse_index(*, out_path: Path = INDEX_PATH) -> Path:
    """Write the Betelgeuse ADS seed index + raw reasoning (no network)."""
    path = write_index_rows([BETELGEUSE_SEED], out_path=out_path)
    ensure_raw_for_star(
        "* alf Ori",
        star={
            "star_id": "* alf Ori",
            "common_name": "Betelgeuse",
            "class": "RSG",
            "spectral_type": "M1-M2Ia-Iab",
        },
    )
    return path


def _evidence_from_index_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw_ev = row.get("evidence_json") or row.get("evidence") or []
    if isinstance(raw_ev, str):
        try:
            raw_ev = json.loads(raw_ev) if raw_ev.strip() else []
        except json.JSONDecodeError:
            raw_ev = []
    out: list[dict[str, Any]] = []
    for item in raw_ev or []:
        if not isinstance(item, dict):
            continue
        bib = str(item.get("bibcode") or "").strip()
        claim = str(item.get("claim") or "").strip()
        if bib and claim:
            out.append({"bibcode": bib, "claim": claim})
    return out


def _raw_from_index_evidence(
    star_id: str,
    *,
    evidence: list[dict[str, Any]],
    lit_scores: dict[str, float],
) -> dict[str, Any]:
    """Build a raw artifact whose reasoning is only the indexed ADS claims."""
    lines = [
        f"Offline literature index for {star_id} (ADS bibcodes only; no invented claims):",
    ]
    for ev in evidence:
        lines.append(f"- {ev['bibcode']}: {ev['claim']}")
    reasoning = "\n".join(lines) if evidence else "insufficient evidence"
    return {
        "star_id": star_id,
        "reasoning": reasoning,
        "literature": {
            "mass_loss": float(lit_scores.get("mass_loss", 0.0) or 0.0),
            "variability": float(lit_scores.get("variability", 0.0) or 0.0),
            "evolved_stage": float(lit_scores.get("evolved_stage", 0.0) or 0.0),
            "confidence": float(lit_scores.get("confidence", 0.0) or 0.0),
            "evidence": evidence,
        },
        "raw_missing": False,
        "simulated": False,
        "source": "index.parquet",
    }


def ensure_raw_for_star(
    star_id: str,
    *,
    raw_dir: Path = RAW_DIR,
    replay_dir: Path | None = None,
    index_path: Path = INDEX_PATH,
    star: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Load or materialize ``data/index/raw/<slug>.json`` from real offline data.

    Order:
    1. Existing raw file
    2. Recorded ADS/arXiv/Grok fixtures under ``tests/fixtures/literature``
    3. Claims already stored in ``index.parquet`` (no invented text)

    Returns ``None`` only when none of the above exist.
    """
    star_id = str(star_id or "").strip()
    if not star_id:
        return None

    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_path_for(star_id, raw_dir)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Corrupt raw literature file %s; regenerating", path)

    replay = Path(replay_dir) if replay_dir is not None else FIXTURES_LITERATURE
    slug = star_id_slug(star_id)
    slug_dir = replay / slug
    if slug_dir.is_dir():
        star_payload = {
            "star_id": star_id,
            "common_name": (star or {}).get("common_name"),
            "class": (star or {}).get("class") or "RSG",
            "spectral_type": (star or {}).get("spectral_type") or "",
        }
        if star_payload["common_name"] is None and "alf Ori" in star_id:
            star_payload["common_name"] = "Betelgeuse"
            star_payload["spectral_type"] = star_payload["spectral_type"] or "M1-M2Ia-Iab"
        result = score_star(
            star_payload,
            ads_token="",
            xai_api_key="",
            replay_dir=replay,
            rate_limit_s=0.0,
        )
        path.write_text(json.dumps(result["raw"], indent=2) + "\n", encoding="utf-8")
        logger.info("Materialized raw literature for %s from fixtures", star_id)
        return result["raw"]

    index_path = Path(index_path)
    if index_path.is_file():
        df = pd.read_parquet(index_path)
        hit = df.loc[df["star_id"].astype(str) == star_id]
        if len(hit) == 0:
            needle = star_id.replace("*", "").strip()
            if needle:
                hit = df.loc[
                    df["star_id"].astype(str).str.contains(needle, regex=False)
                ]
        if len(hit) > 0:
            row = hit.iloc[0].to_dict()
            evidence = _evidence_from_index_row(row)
            artifact = _raw_from_index_evidence(
                star_id,
                evidence=evidence,
                lit_scores={
                    "mass_loss": float(row.get("mass_loss", 0.0) or 0.0),
                    "variability": float(row.get("variability", 0.0) or 0.0),
                    "evolved_stage": float(row.get("evolved_stage", 0.0) or 0.0),
                    "confidence": float(row.get("confidence", 0.0) or 0.0),
                },
            )
            path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
            logger.info(
                "Materialized raw literature for %s from index.parquet (%d claims)",
                star_id,
                len(evidence),
            )
            return artifact

    return None


def _title_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(v) for v in value if v).strip()
    return str(value).strip()


def _paper_dict(
    *,
    bibcode: str,
    title: str,
    abstract: str,
    source: str,
    arxiv_id: str | None = None,
) -> dict[str, str] | None:
    bib = (bibcode or "").strip()
    if not bib:
        return None
    return {
        "bibcode": bib,
        "title": (title or "").strip(),
        "abstract": (abstract or "").strip(),
        "source": source,
        "arxiv_id": (arxiv_id or "").strip(),
    }


def query_ads(
    star: dict[str, Any],
    *,
    token: str,
    rows: int = DEFAULT_ADS_ROWS,
    http_get: HttpGet | None = None,
    rate_limit_s: float = 0.0,
) -> list[dict[str, str]]:
    """Query NASA ADS for papers on this star. Requires ADS_API_TOKEN."""
    if not token:
        raise LiteratureBuildError("ADS_API_TOKEN is empty; cannot query NASA ADS.")

    names: list[str] = []
    for key in ("common_name", "star_id"):
        val = star.get(key)
        if val and str(val).strip():
            names.append(str(val).strip())
    if not names:
        return []

    # Prefer common name; quote for phrase search.
    primary = names[0]
    q = f'abs:"{primary}" OR title:"{primary}"'
    params = {
        "q": q,
        "fl": "bibcode,title,abstract,arxiv_class,identifier",
        "rows": str(int(rows)),
        "sort": "citation_count desc",
    }
    headers = {"Authorization": f"Bearer {token}"}
    getter = http_get or httpx.get
    if rate_limit_s > 0:
        time.sleep(rate_limit_s)
    resp = getter(ADS_SEARCH_URL, params=params, headers=headers, timeout=60.0)
    resp.raise_for_status()
    payload = resp.json()
    docs = (payload.get("response") or {}).get("docs") or []
    out: list[dict[str, str]] = []
    for doc in docs:
        paper = _paper_dict(
            bibcode=str(doc.get("bibcode") or ""),
            title=_title_to_str(doc.get("title")),
            abstract=str(doc.get("abstract") or ""),
            source="ADS",
        )
        if paper:
            out.append(paper)
    return out


def _arxiv_id_to_bibcode(arxiv_id: str, published: str) -> str:
    """Best-effort ADS-style bibcode for an arXiv id (year from published date)."""
    aid = arxiv_id.strip()
    year = "0000"
    if published:
        m = re.match(r"(\d{4})", published)
        if m:
            year = m.group(1)
    # New-style ids: YYMM.NNNNN → keep digits; ADS often uses 2020arXiv2006.09837J
    compact = aid.replace(".", "")
    return f"{year}arXiv{compact}"


def query_arxiv(
    star: dict[str, Any],
    *,
    max_results: int = DEFAULT_ARXIV_ROWS,
    http_get: HttpGet | None = None,
    rate_limit_s: float = 0.0,
) -> list[dict[str, str]]:
    """Query arXiv Atom API for papers on this star (no ADS token required)."""
    names: list[str] = []
    for key in ("common_name", "star_id"):
        val = star.get(key)
        if val and str(val).strip():
            names.append(str(val).strip())
    if not names:
        return []
    primary = names[0]
    # Escape quotes in arXiv query language.
    safe = primary.replace('"', "")
    search_query = f'all:"{safe}"'
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": int(max_results),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    getter = http_get or httpx.get
    if rate_limit_s > 0:
        time.sleep(rate_limit_s)
    resp = getter(ARXIV_API_URL, params=params, timeout=60.0)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    out: list[dict[str, str]] = []
    for entry in root.findall("a:entry", _ATOM_NS):
        entry_id = entry.findtext("a:id", default="", namespaces=_ATOM_NS) or ""
        m = re.search(r"arxiv\.org/abs/([^v\s]+)", entry_id)
        arxiv_id = m.group(1) if m else ""
        title = (entry.findtext("a:title", default="", namespaces=_ATOM_NS) or "").replace(
            "\n", " "
        ).strip()
        abstract = (
            entry.findtext("a:summary", default="", namespaces=_ATOM_NS) or ""
        ).replace("\n", " ").strip()
        published = entry.findtext("a:published", default="", namespaces=_ATOM_NS) or ""
        if not arxiv_id:
            continue
        bibcode = _arxiv_id_to_bibcode(arxiv_id, published)
        paper = _paper_dict(
            bibcode=bibcode,
            title=title,
            abstract=abstract,
            source="arXiv",
            arxiv_id=arxiv_id,
        )
        if paper:
            out.append(paper)
    return out


def merge_papers(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    """Deduplicate by bibcode; prefer ADS rows when both sources match."""
    by_bib: dict[str, dict[str, str]] = {}
    for group in groups:
        for paper in group:
            bib = paper["bibcode"]
            if bib not in by_bib:
                by_bib[bib] = paper
                continue
            # Prefer non-empty abstract / ADS source.
            existing = by_bib[bib]
            if existing.get("source") != "ADS" and paper.get("source") == "ADS":
                by_bib[bib] = paper
            elif not existing.get("abstract") and paper.get("abstract"):
                by_bib[bib] = {**existing, "abstract": paper["abstract"]}
    return list(by_bib.values())


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model reply (allows fenced markdown)."""
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1)
    else:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    return json.loads(stripped)


def build_grok_prompt(star: dict[str, Any], papers: list[dict[str, str]]) -> str:
    """Prompt: score from retrieved papers only; never invent bibcodes."""
    catalog = [
        {
            "bibcode": p["bibcode"],
            "title": p.get("title") or "",
            "abstract": p.get("abstract") or "",
            "source": p.get("source") or "",
        }
        for p in papers
    ]
    star_blob = {
        "star_id": star.get("star_id"),
        "common_name": star.get("common_name"),
        "class": star.get("class"),
        "spectral_type": star.get("spectral_type"),
    }
    return (
        "You are scoring progenitor literature for BREAKOUT (supernova early warning).\n"
        "Use ONLY the retrieved papers below. Do not invent bibcodes, numbers, or claims.\n"
        "If the papers are insufficient to support a score, answer with "
        '"insufficient evidence": set mass_loss, variability, evolved_stage, and '
        "confidence to 0, and either leave evidence empty or include a single "
        'evidence item whose claim is exactly "insufficient evidence" citing one '
        "retrieved bibcode.\n"
        "Return ONLY JSON with this schema:\n"
        "{\n"
        '  "mass_loss": float 0..1,\n'
        '  "variability": float 0..1,\n'
        '  "evolved_stage": float 0..1,\n'
        '  "confidence": float 0..1,\n'
        '  "evidence": [{"bibcode": "<retrieved bibcode>", "claim": "<text>"}],\n'
        '  "reasoning": "<your full reasoning; this is shown in the UI>"\n'
        "}\n"
        "Every evidence.bibcode MUST appear in the retrieved list.\n\n"
        f"STAR:\n{json.dumps(star_blob, indent=2)}\n\n"
        f"RETRIEVED_PAPERS:\n{json.dumps(catalog, indent=2)}\n"
    )


def query_grok(
    star: dict[str, Any],
    papers: list[dict[str, str]],
    *,
    api_key: str,
    model: str = XAI_MODEL_DEFAULT,
    http_post: HttpPost | None = None,
    rate_limit_s: float = 0.0,
) -> dict[str, Any]:
    """Call xAI Grok chat completions; return raw + parsed fields."""
    if not api_key:
        raise LiteratureBuildError("XAI_API_KEY is empty; cannot call Grok.")

    prompt = build_grok_prompt(star, papers)
    body = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You extract literature scores for stellar progenitors. "
                    "Never invent citations. Prefer insufficient evidence over guesses."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    poster = http_post or httpx.post
    if rate_limit_s > 0:
        time.sleep(rate_limit_s)
    resp = poster(XAI_CHAT_URL, headers=headers, json=body, timeout=120.0)
    resp.raise_for_status()
    payload = resp.json()
    choices = payload.get("choices") or []
    content = ""
    if choices:
        message = choices[0].get("message") or {}
        content = str(message.get("content") or "")
    return {
        "raw_response": payload,
        "content_text": content,
        "prompt": prompt,
    }


def validate_literature(
    data: dict[str, Any],
    *,
    allowed_bibcodes: set[str],
) -> Literature:
    """Validate against Literature; drop evidence whose bibcode was not retrieved."""
    raw_evidence = data.get("evidence") or []
    kept: list[dict[str, str]] = []
    dropped: list[str] = []
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        bib = str(item.get("bibcode") or "").strip()
        claim = str(item.get("claim") or "").strip()
        if not bib or not claim:
            continue
        if bib not in allowed_bibcodes:
            dropped.append(bib)
            continue
        if claim.lower() == "insufficient evidence":
            # Model admitted insufficiency — do not keep as a scientific claim.
            continue
        kept.append({"bibcode": bib, "claim": claim})

    if dropped:
        logger.info("Dropped evidence with unknown bibcodes: %s", dropped)

    # If nothing usable remains, force insufficient-evidence zeros (never invent).
    if not kept:
        return Literature(
            mass_loss=0.0,
            variability=0.0,
            evolved_stage=0.0,
            confidence=0.0,
            evidence=[],
        )

    payload = {
        "mass_loss": data.get("mass_loss", 0.0),
        "variability": data.get("variability", 0.0),
        "evolved_stage": data.get("evolved_stage", 0.0),
        "confidence": data.get("confidence", 0.0),
        "evidence": kept,
    }
    return Literature.model_validate(payload)


def _load_replay_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _papers_from_replay(replay_star_dir: Path) -> list[dict[str, str]]:
    """Load recorded ADS + arXiv paper lists from a replay directory."""
    papers: list[dict[str, str]] = []
    ads_path = replay_star_dir / "ads_docs.json"
    arxiv_path = replay_star_dir / "arxiv_docs.json"
    if ads_path.is_file():
        docs = _load_replay_json(ads_path)
        if isinstance(docs, dict):
            docs = (docs.get("response") or {}).get("docs") or docs.get("docs") or []
        for doc in docs:
            paper = _paper_dict(
                bibcode=str(doc.get("bibcode") or ""),
                title=_title_to_str(doc.get("title")),
                abstract=str(doc.get("abstract") or ""),
                source="ADS",
            )
            if paper:
                papers.append(paper)
    if arxiv_path.is_file():
        docs = _load_replay_json(arxiv_path)
        if isinstance(docs, dict):
            docs = docs.get("docs") or []
        for doc in docs:
            paper = _paper_dict(
                bibcode=str(doc.get("bibcode") or ""),
                title=_title_to_str(doc.get("title")),
                abstract=str(doc.get("abstract") or ""),
                source="arXiv",
                arxiv_id=str(doc.get("arxiv_id") or ""),
            )
            if paper:
                papers.append(paper)
    return merge_papers(papers)


def _grok_from_replay(replay_star_dir: Path) -> dict[str, Any]:
    path = replay_star_dir / "grok_response.json"
    if not path.is_file():
        raise LiteratureBuildError(f"Missing recorded Grok response: {path}")
    payload = _load_replay_json(path)
    # Allow either full chat-completions payload or a thin {content, reasoning,...}.
    if "choices" in payload:
        content = str(((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        return {"raw_response": payload, "content_text": content, "prompt": ""}
    content = payload.get("content_text") or payload.get("content") or ""
    if not content and "mass_loss" in payload:
        # Fixture stored the scored JSON directly.
        content = json.dumps(payload)
    return {
        "raw_response": payload.get("raw_response", payload),
        "content_text": str(content),
        "prompt": str(payload.get("prompt") or ""),
    }


def score_star(
    star: dict[str, Any],
    *,
    ads_token: str,
    xai_api_key: str,
    http_get: HttpGet | None = None,
    http_post: HttpPost | None = None,
    rate_limit_s: float = DEFAULT_RATE_LIMIT_S,
    replay_dir: Path | None = None,
    model: str = XAI_MODEL_DEFAULT,
) -> dict[str, Any]:
    """Retrieve papers, call Grok, validate Literature; return row + raw artifact."""
    star_id = str(star.get("star_id") or "")
    if not star_id:
        raise LiteratureBuildError("star is missing star_id")

    if replay_dir is not None:
        slug_dir = Path(replay_dir) / star_id_slug(star_id)
        if not slug_dir.is_dir():
            # Also try literal star_id directory name.
            alt = Path(replay_dir) / star_id
            slug_dir = alt if alt.is_dir() else slug_dir
        papers = _papers_from_replay(slug_dir)
        grok = _grok_from_replay(slug_dir)
    else:
        ads_papers = query_ads(
            star, token=ads_token, http_get=http_get, rate_limit_s=rate_limit_s
        )
        arxiv_papers = query_arxiv(
            star, http_get=http_get, rate_limit_s=rate_limit_s
        )
        papers = merge_papers(ads_papers, arxiv_papers)
        grok = query_grok(
            star,
            papers,
            api_key=xai_api_key,
            model=model,
            http_post=http_post,
            rate_limit_s=rate_limit_s,
        )

    allowed = {p["bibcode"] for p in papers}
    content_text = str(grok.get("content_text") or "")
    parsed: dict[str, Any]
    try:
        parsed = _extract_json_object(content_text) if content_text.strip() else {}
    except json.JSONDecodeError:
        logger.warning("Grok returned non-JSON for %s; treating as insufficient evidence", star_id)
        parsed = {
            "mass_loss": 0.0,
            "variability": 0.0,
            "evolved_stage": 0.0,
            "confidence": 0.0,
            "evidence": [],
            "reasoning": content_text or "insufficient evidence",
        }

    literature = validate_literature(parsed, allowed_bibcodes=allowed)
    reasoning = str(parsed.get("reasoning") or "").strip()
    if not reasoning:
        # Prefer the full model text over canned placeholders.
        reasoning = content_text.strip() or "insufficient evidence"

    raw_artifact = {
        "star_id": star_id,
        "common_name": star.get("common_name"),
        "class": star.get("class"),
        "retrieved_papers": papers,
        "allowed_bibcodes": sorted(allowed),
        "prompt": grok.get("prompt") or build_grok_prompt(star, papers),
        "raw_response": grok.get("raw_response"),
        "content_text": content_text,
        "reasoning": reasoning,
        "literature": literature.model_dump(),
        "simulated": False,
        "source": "replay" if replay_dir is not None else "live",
    }

    row = {
        "star_id": star_id,
        "mass_loss": literature.mass_loss,
        "variability": literature.variability,
        "evolved_stage": literature.evolved_stage,
        "confidence": literature.confidence,
        "evidence": [e.model_dump() for e in literature.evidence],
        "simulated": False,
    }
    return {"row": row, "raw": raw_artifact}


def _read_existing_index(out_path: Path) -> dict[str, dict[str, Any]]:
    if not Path(out_path).is_file():
        return {}
    df = pd.read_parquet(out_path)
    if "star_id" not in df.columns:
        return {}
    return {str(r["star_id"]): r for r in df.to_dict(orient="records")}


def build_index(
    stars: list[dict[str, Any]],
    *,
    out_path: Path = INDEX_PATH,
    raw_dir: Path = RAW_DIR,
    resume: bool = True,
    rate_limit_s: float = DEFAULT_RATE_LIMIT_S,
    ads_token: str | None = None,
    xai_api_key: str | None = None,
    http_get: HttpGet | None = None,
    http_post: HttpPost | None = None,
    replay_dir: Path | None = None,
    model: str = XAI_MODEL_DEFAULT,
    force: bool = False,
) -> Path:
    """Query ADS/arXiv, score with Grok, write raw JSON + index.parquet.

    Resume-safe: stars with an existing raw artifact and index row are skipped
    unless ``force=True``. Rate-limited between network calls.
    """
    out_path = Path(out_path)
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    token = ads_token if ads_token is not None else settings.ads_api_token
    xai_key = xai_api_key if xai_api_key is not None else settings.xai_api_key
    if replay_dir is None and (not token or not xai_key):
        raise LiteratureBuildError(
            "build_index requires ADS_API_TOKEN and XAI_API_KEY in .env "
            "(or pass replay_dir= for recorded responses)."
        )

    existing = _read_existing_index(out_path)
    rows_by_id: dict[str, dict[str, Any]] = dict(existing)

    for star in stars:
        star_id = str(star.get("star_id") or "")
        if not star_id:
            continue
        raw_file = raw_path_for(star_id, raw_dir)
        if resume and not force and raw_file.is_file() and star_id in rows_by_id:
            logger.info("Resume skip %s (raw+index present)", star_id)
            continue

        result = score_star(
            star,
            ads_token=token or "",
            xai_api_key=xai_key or "",
            http_get=http_get,
            http_post=http_post,
            rate_limit_s=rate_limit_s if replay_dir is None else 0.0,
            replay_dir=replay_dir,
            model=model,
        )
        raw_file.write_text(json.dumps(result["raw"], indent=2) + "\n", encoding="utf-8")
        rows_by_id[star_id] = result["row"]
        logger.info(
            "Indexed %s confidence=%.2f evidence=%d",
            star_id,
            result["row"]["confidence"],
            len(result["row"]["evidence"]),
        )

    batch_ids = [str(s.get("star_id")) for s in stars if s.get("star_id")]
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sid in batch_ids:
        if sid in rows_by_id and sid not in seen:
            ordered.append(_row_for_write(rows_by_id[sid]))
            seen.add(sid)
    for sid, row in rows_by_id.items():
        if sid not in seen:
            ordered.append(_row_for_write(row))
            seen.add(sid)
    return write_index_rows(ordered, out_path=out_path)


def _row_for_write(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize an index row (fresh or parquet-loaded) for write_index_rows."""
    if "evidence" in row and row["evidence"] is not None and not isinstance(
        row.get("evidence"), float
    ):
        evidence = row["evidence"]
    elif row.get("evidence_json"):
        raw = row["evidence_json"]
        evidence = json.loads(raw) if isinstance(raw, str) else (raw or [])
    else:
        evidence = []
    return {
        "star_id": str(row["star_id"]),
        "mass_loss": float(row.get("mass_loss", 0.0) or 0.0),
        "variability": float(row.get("variability", 0.0) or 0.0),
        "evolved_stage": float(row.get("evolved_stage", 0.0) or 0.0),
        "confidence": float(row.get("confidence", 0.0) or 0.0),
        "evidence": evidence,
        "simulated": bool(row.get("simulated", False)),
    }


def load_stars_for_index(
    star_table_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Load star_table.parquet, falling back to curated_stars.json."""
    from backend.candidates.catalog import CURATED_PATH, STAR_TABLE_PATH, load_curated_stars

    path = Path(star_table_path) if star_table_path is not None else STAR_TABLE_PATH
    if path.is_file():
        df = pd.read_parquet(path)
        rows = df.to_dict(orient="records")
        if rows:
            return rows
    if CURATED_PATH.is_file():
        return load_curated_stars(CURATED_PATH)
    return []


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.literature.build_index",
        description="OFFLINE literature index: ADS + arXiv → Grok → index.parquet",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=INDEX_PATH,
        help="Output parquet path (default backend/literature/index.parquet)",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=RAW_DIR,
        help="Directory for per-star raw JSON (default data/index/raw)",
    )
    parser.add_argument(
        "--replay-dir",
        type=Path,
        default=None,
        help="Use recorded ADS/arXiv/Grok JSON under this directory (no network).",
    )
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Write Betelgeuse seed index only (no ADS/Grok).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-score stars even if raw+index already exist.",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=DEFAULT_RATE_LIMIT_S,
        help="Seconds to sleep between network calls (default 1.0).",
    )
    parser.add_argument(
        "--curated-only",
        action="store_true",
        help="Index only data/stars/curated_stars.json (ignore full parquet).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_arg_parser().parse_args(argv)
    if args.seed_only:
        path = seed_betelgeuse_index(out_path=args.out)
        print(f"wrote seed index to {path}")
        return 0

    if args.curated_only:
        from backend.candidates.catalog import load_curated_stars

        stars = load_curated_stars()
    else:
        stars = load_stars_for_index()
    if not stars:
        raise SystemExit("No stars found in star_table.parquet or curated_stars.json")

    path = build_index(
        stars,
        out_path=args.out,
        raw_dir=args.raw_dir,
        resume=not args.force,
        force=args.force,
        rate_limit_s=args.rate_limit,
        replay_dir=args.replay_dir,
    )
    print(f"wrote index for {len(stars)} star(s) to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
