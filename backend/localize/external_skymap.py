"""Load an external HEALPix probability map from a SNEWS/GCN notice.

Used when a coincidence notice includes ``healpix_url`` (SNEWS2 GCN schema).
Never invents a map: returns None when the URL is missing, is a placeholder,
or cannot be read. DiffPointing from detector times remains the primary
self-localization path.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import healpy as hp
import numpy as np

from backend.config import settings
from backend.schemas import Alert

logger = logging.getLogger("breakout.localize.external_skymap")

_BLOCKED_HOSTS = frozenset({"example.com", "example.org", "localhost", "127.0.0.1"})


def healpix_url_from_alert(alert: Alert) -> str | None:
    raw = alert.raw if isinstance(alert.raw, dict) else {}
    url = raw.get("healpix_url") or raw.get("skymap_url") or raw.get("healpix")
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return None
    host = (urlparse(url).hostname or "").lower()
    if host in _BLOCKED_HOSTS or host.endswith(".example"):
        return None
    return url


def load_healpix_prob(
    source: str | Path,
    *,
    nside: int,
    nest: bool = True,
) -> np.ndarray | None:
    """Read a FITS HEALPix map and regrade/normalize to ``nside`` NESTED."""
    path = Path(source)
    if not path.is_file():
        return None
    try:
        # healpy auto-detects nesting from header when nest=None in newer versions;
        # try NESTED first then RING.
        try:
            m = np.asarray(hp.read_map(str(path), nest=True), dtype=float)
            src_nest = True
        except Exception:
            m = np.asarray(hp.read_map(str(path), nest=False), dtype=float)
            src_nest = False
        if not src_nest:
            m = hp.reorder(m, r2n=True)
        src_nside = hp.npix2nside(len(m))
        if src_nside != nside:
            m = hp.ud_grade(m, nside, order_in="NESTED", order_out="NESTED")
        total = float(np.sum(m))
        if not np.isfinite(total) or total <= 0:
            return None
        return m / total
    except Exception:
        logger.exception("external_skymap_read_failed path=%s", path)
        return None


def fetch_notice_healpix(alert: Alert, *, nside: int) -> np.ndarray | None:
    """Download ``healpix_url`` when live network is allowed; else None."""
    url = healpix_url_from_alert(alert)
    if url is None:
        return None
    if settings.use_cached_stream:
        return None
    try:
        import httpx
    except ImportError:
        logger.warning("external_skymap_skip reason=httpx_missing")
        return None
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            suffix = ".fits.gz" if url.endswith(".gz") else ".fits"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = Path(tmp.name)
        try:
            return load_healpix_prob(tmp_path, nside=nside)
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:
        logger.exception("external_skymap_fetch_failed url=%s", url)
        return None
