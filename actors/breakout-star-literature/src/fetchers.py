"""Public ATel + arXiv fetchers for the BREAKOUT literature actor.

Only returns items that were actually retrieved. Empty results on failure —
never invent titles, ids, dates, or URLs. Every item is labeled simulated=false
because these are public notices/preprints, not synthetic demo rows.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Callable
from urllib.parse import quote_plus, urljoin

import httpx

logger = logging.getLogger("breakout.apify.actor.fetchers")

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATEL_SEARCH_URL = "https://www.astronomerstelegram.org/"
_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

HttpGet = Callable[..., httpx.Response]


def _queries_for_star(star: dict[str, Any]) -> list[str]:
    """Build search strings from star_id + aliases (deduped, non-empty)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in [star.get("star_id"), *(star.get("aliases") or [])]:
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


def fetch_arxiv(
    star: dict[str, Any],
    *,
    max_results: int = 10,
    http_get: HttpGet | None = None,
) -> list[dict[str, Any]]:
    """Query the public arXiv Atom API. Returns real entries only."""
    queries = _queries_for_star(star)
    if not queries:
        return []
    star_id = str(star.get("star_id") or "").strip()
    getter = http_get or httpx.get
    # Prefer the first human alias when present (usually the common name).
    primary = queries[-1] if len(queries) > 1 else queries[0]
    if len(queries) > 1:
        # aliases listed after star_id in input; use first alias if any
        aliases = [a for a in (star.get("aliases") or []) if str(a).strip()]
        if aliases:
            primary = str(aliases[0]).strip()
    safe = primary.replace('"', "")
    params = {
        "search_query": f'all:"{safe}"',
        "start": 0,
        "max_results": int(max_results),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    try:
        resp = getter(ARXIV_API_URL, params=params, timeout=60.0)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — actor must continue on network errors
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
        published = (
            entry.findtext("a:published", default="", namespaces=_ATOM_NS) or ""
        ).strip()
        if not arxiv_id or not title:
            continue
        url = f"https://arxiv.org/abs/{arxiv_id}"
        items.append(
            {
                "star_id": star_id,
                "source": "arxiv",
                "item_id": arxiv_id,
                "title": title,
                "date": published[:10] if published else None,
                "url": url,
                "simulated": False,
            }
        )
        if len(items) >= max_results:
            break
    return items


def fetch_atel(
    star: dict[str, Any],
    *,
    max_results: int = 10,
    http_get: HttpGet | None = None,
) -> list[dict[str, Any]]:
    """Search Astronomer's Telegram HTML for the star name.

    Parses public search HTML only. If the layout cannot be parsed or the
    request fails, returns [] — never fabricates telegram numbers.
    """
    queries = _queries_for_star(star)
    if not queries:
        return []
    star_id = str(star.get("star_id") or "").strip()
    aliases = [a for a in (star.get("aliases") or []) if str(a).strip()]
    primary = str(aliases[0]).strip() if aliases else queries[0]
    getter = http_get or httpx.get
    url = f"{ATEL_SEARCH_URL}?read=0&selno=100&searchtext={quote_plus(primary)}"
    try:
        resp = getter(url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("ATel fetch failed for %s: %s", star_id, exc)
        return []

    # Telegram links look like ?read=NNNNN with a nearby title.
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
        # Skip navigation chrome that is not a telegram title.
        if title.lower() in {"read", "home", "search", "submit"}:
            continue
        seen.add(num)
        items.append(
            {
                "star_id": star_id,
                "source": "atel",
                "item_id": num,
                "title": title,
                "date": None,  # ATel search HTML often omits a reliable date field
                "url": urljoin(ATEL_SEARCH_URL, rel),
                "simulated": False,
            }
        )
        if len(items) >= max_results:
            break
    return items


def collect_items(
    star: dict[str, Any],
    sources: list[str],
    *,
    max_per_source: int = 10,
    http_get: HttpGet | None = None,
) -> list[dict[str, Any]]:
    """Collect ATel/arXiv items for one star from the requested sources."""
    wanted = {str(s).strip().lower() for s in sources}
    out: list[dict[str, Any]] = []
    if "arxiv" in wanted:
        out.extend(fetch_arxiv(star, max_results=max_per_source, http_get=http_get))
    if "atel" in wanted:
        out.extend(fetch_atel(star, max_results=max_per_source, http_get=http_get))
    return out
