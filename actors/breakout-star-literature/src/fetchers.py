"""ATel + arXiv fetchers with mention filtering and polite rate limits.

Only returns items that were actually retrieved and whose title/summary
mentions the star (star_id or an alias). Never invents rows.
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Callable
from urllib.parse import quote_plus, urljoin

import httpx

logger = logging.getLogger("breakout.apify.fetchers")

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATEL_BASE_URL = "https://www.astronomerstelegram.org/"
_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

# Polite defaults (arXiv asks for pauses; ATel is a small volunteer site).
ARXIV_PAUSE_S = 3.0
ATEL_PAUSE_S = 2.0

HttpGet = Callable[..., httpx.Response]


def query_names(star: dict[str, Any]) -> list[str]:
    """Deduped search/mention names: aliases first (human names), then star_id."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in [*(star.get("aliases") or []), star.get("star_id")]:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _normalize_for_match(text: str) -> str:
    # Collapse whitespace; keep letters/digits so "ρ Cas" / "Rho Cas" still work via aliases.
    return re.sub(r"\s+", " ", text or "").strip().lower()


def mentions_star(text: str, star: dict[str, Any]) -> bool:
    """True if title/abstract/body text mentions star_id or any alias."""
    blob = _normalize_for_match(text)
    if not blob:
        return False
    for name in query_names(star):
        needle = _normalize_for_match(name)
        if len(needle) < 2:
            continue
        if needle in blob:
            return True
        # SIMBAD-style ids often appear without the leading "* ".
        stripped = needle.lstrip("* ").strip()
        if stripped and stripped != needle and stripped in blob:
            return True
    return False


def fetch_arxiv(
    star: dict[str, Any],
    *,
    max_results: int = 20,
    http_get: HttpGet | None = None,
    pause_s: float = ARXIV_PAUSE_S,
) -> list[dict[str, Any]]:
    names = query_names(star)
    if not names:
        return []
    star_id = str(star.get("star_id") or "").strip()
    primary = names[0]
    safe = primary.replace('"', "")
    params = {
        "search_query": f'all:"{safe}"',
        "start": 0,
        "max_results": int(max_results),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    getter = http_get or httpx.get
    if pause_s > 0 and http_get is None:
        time.sleep(pause_s)
    try:
        resp = getter(ARXIV_API_URL, params=params, timeout=60.0)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("arXiv fetch failed for %s: %s", star_id, exc)
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        logger.warning("arXiv XML parse failed for %s: %s", star_id, exc)
        return []

    items: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", _ATOM_NS):
        entry_id = entry.findtext("a:id", default="", namespaces=_ATOM_NS) or ""
        m = re.search(r"arxiv\.org/abs/([^v?\s]+)", entry_id)
        arxiv_id = m.group(1).strip() if m else ""
        title = (entry.findtext("a:title", default="", namespaces=_ATOM_NS) or "").replace(
            "\n", " "
        ).strip()
        summary = (
            entry.findtext("a:summary", default="", namespaces=_ATOM_NS) or ""
        ).replace("\n", " ").strip()
        published = (
            entry.findtext("a:published", default="", namespaces=_ATOM_NS) or ""
        ).strip()
        if not arxiv_id or not title:
            continue
        haystack = f"{title}\n{summary}"
        if not mentions_star(haystack, star):
            continue
        items.append(
            {
                "star_id": star_id,
                "source": "arxiv",
                "item_id": arxiv_id,
                "title": title,
                "date": published[:10] if published else None,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "abstract_or_summary": summary or None,
                "simulated": False,
            }
        )
        if len(items) >= max_results:
            break
    return items


def _parse_atel_search_html(html: str, star: dict[str, Any], *, max_results: int) -> list[dict[str, Any]]:
    star_id = str(star.get("star_id") or "").strip()
    pattern = re.compile(
        r'href="(\?read=(\d+))"[^>]*>(.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in pattern.finditer(html):
        rel, num, raw_title = match.group(1), match.group(2), match.group(3)
        title = re.sub(r"<[^>]+>", "", raw_title)
        title = re.sub(r"\s+", " ", title).strip()
        if not title or num in seen:
            continue
        if title.lower() in {"read", "home", "search", "submit"}:
            continue
        if not mentions_star(title, star):
            continue
        seen.add(num)
        items.append(
            {
                "star_id": star_id,
                "source": "atel",
                "item_id": num,
                "title": title,
                "date": None,
                "url": urljoin(ATEL_BASE_URL, rel),
                "abstract_or_summary": title,
                "simulated": False,
            }
        )
        if len(items) >= max_results:
            break
    return items


def _parse_atel_rss(xml_text: str, star: dict[str, Any], *, max_results: int) -> list[dict[str, Any]]:
    """Filter the public ATel RSS feed for items that mention the star."""
    star_id = str(star.get("star_id") or "").strip()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("ATel RSS parse failed for %s: %s", star_id, exc)
        return []

    items: list[dict[str, Any]] = []
    # RSS 1.0 (RDF) or RSS 2.0
    candidates = list(root.findall(".//{http://purl.org/rss/1.0/}item"))
    candidates += list(root.findall(".//item"))
    for node in candidates:
        title = (
            node.findtext("{http://purl.org/rss/1.0/}title")
            or node.findtext("title")
            or ""
        ).strip()
        link = (
            node.findtext("{http://purl.org/rss/1.0/}link")
            or node.findtext("link")
            or ""
        ).strip()
        desc = (
            node.findtext("{http://purl.org/rss/1.0/}description")
            or node.findtext("description")
            or ""
        ).strip()
        date = (
            node.findtext("{http://purl.org/dc/elements/1.1/}date")
            or node.findtext("pubDate")
            or ""
        ).strip()
        haystack = f"{title}\n{desc}"
        if not title or not mentions_star(haystack, star):
            continue
        num_m = re.search(r"read=(\d+)", link) or re.search(r"/(\d+)\b", link)
        item_id = num_m.group(1) if num_m else link
        if not link:
            continue
        items.append(
            {
                "star_id": star_id,
                "source": "atel",
                "item_id": str(item_id),
                "title": title,
                "date": date[:10] if date else None,
                "url": link,
                "abstract_or_summary": desc or title,
                "simulated": False,
            }
        )
        if len(items) >= max_results:
            break
    return items


def fetch_atel(
    star: dict[str, Any],
    *,
    max_results: int = 20,
    http_get: HttpGet | None = None,
    pause_s: float = ATEL_PAUSE_S,
) -> list[dict[str, Any]]:
    names = query_names(star)
    if not names:
        return []
    star_id = str(star.get("star_id") or "").strip()
    primary = names[0]
    search_url = f"{ATEL_BASE_URL}?read=0&selno=100&searchtext={quote_plus(primary)}"
    getter = http_get or httpx.get
    if pause_s > 0 and http_get is None:
        time.sleep(pause_s)
    # Prefer HTML search; fall back to the public RSS feed when search is down.
    try:
        resp = getter(search_url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
        return _parse_atel_search_html(resp.text, star, max_results=max_results)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ATel HTML search failed for %s (%s); trying RSS", star_id, exc)

    rss_url = f"{ATEL_BASE_URL}?rss"
    try:
        if pause_s > 0 and http_get is None:
            time.sleep(pause_s)
        resp = getter(rss_url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
        return _parse_atel_rss(resp.text, star, max_results=max_results)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ATel RSS fetch failed for %s: %s", star_id, exc)
        return []


def collect_for_star(
    star: dict[str, Any],
    sources: list[str],
    *,
    max_items_per_star: int = 20,
    http_get: HttpGet | None = None,
) -> list[dict[str, Any]]:
    wanted = {str(s).strip().lower() for s in sources}
    # Fetch a bit extra per source, then truncate to max_items_per_star.
    per_source = max(1, min(50, max_items_per_star))
    out: list[dict[str, Any]] = []
    if "arxiv" in wanted:
        out.extend(
            fetch_arxiv(star, max_results=per_source, http_get=http_get)
        )
    if "atel" in wanted:
        out.extend(
            fetch_atel(star, max_results=per_source, http_get=http_get)
        )
    return out[: max(1, int(max_items_per_star))]
