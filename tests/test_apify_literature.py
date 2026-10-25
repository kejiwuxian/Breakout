"""P2.3: Apify literature — mocked client; flag off means no import."""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

ACTOR_ROOT = Path(__file__).resolve().parents[1] / "actors" / "breakout-star-literature"


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2006.09837v1</id>
    <title>The Great Dimming of Betelgeuse: a Surface Mass Ejection</title>
    <published>2020-06-17T00:00:00Z</published>
    <summary>We discuss Betelgeuse and its historic dimming event in detail.</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/9999.99999v1</id>
    <title>Unrelated quasar survey with no target star</title>
    <published>2020-01-01T00:00:00Z</published>
    <summary>No mention of the requested object here.</summary>
  </entry>
</feed>
"""

ATEL_HTML = """
<html><body>
<a href="?read=13601">Betelgeuse optical fading notice</a>
<a href="?read=99999">Some other supernova in M31</a>
<a href="?read=0">Home</a>
</body></html>
"""


def _fake_http_get(url: str, params: dict | None = None, **_kwargs: Any) -> _FakeResponse:
    if "arxiv.org" in url:
        return _FakeResponse(ARXIV_ATOM)
    if "astronomerstelegram.org" in url:
        return _FakeResponse(ATEL_HTML)
    raise AssertionError(f"unexpected URL {url} params={params}")


def test_flag_off_means_no_apify_client_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APIFY_ENABLED", "False")
    sys.modules.pop("apify_client", None)

    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    import backend.integrations.apify_literature as mod

    importlib.reload(mod)
    assert mod.is_enabled() is False
    assert "apify_client" not in sys.modules

    written = mod.fetch_and_store([{"star_id": "* alf Ori"}])
    assert written == {}
    assert "apify_client" not in sys.modules


def test_actor_collect_filters_non_mentions() -> None:
    sys.path.insert(0, str(ACTOR_ROOT))
    from src.main import run_collect  # type: ignore[import-not-found]

    items = run_collect(
        {
            "stars": [{"star_id": "* alf Ori", "aliases": ["Betelgeuse"]}],
            "sources": ["arxiv", "atel"],
            "max_items_per_star": 10,
        },
        http_get=_fake_http_get,
    )
    assert items
    assert all("Betelgeuse" in (i["title"] + (i.get("abstract_or_summary") or "")) for i in items)
    assert all(i["simulated"] is False for i in items)
    assert {i["source"] for i in items} == {"arxiv", "atel"}
    assert all("url" in i and i["url"].startswith("http") for i in items)
    assert all("abstract_or_summary" in i for i in items)
    # Unrelated arXiv / ATel rows must be dropped by the mention filter.
    assert all(i["item_id"] != "9999.99999" for i in items)
    assert all(i["item_id"] != "99999" for i in items)


def test_apify_client_call_mocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APIFY_ENABLED", "True")
    monkeypatch.setenv("APIFY_TOKEN", "test-token")
    monkeypatch.setenv("APIFY_ACTOR_ID", "user/breakout-star-literature")

    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    import backend.integrations.apify_literature as mod

    importlib.reload(mod)

    class _Dataset:
        def iterate_items(self):
            yield {
                "star_id": "* alf Ori",
                "source": "arxiv",
                "item_id": "2006.09837",
                "title": "Mocked arXiv row about Betelgeuse",
                "date": "2020-06-17",
                "url": "https://arxiv.org/abs/2006.09837",
                "abstract_or_summary": "Summary text",
                "simulated": False,
            }

    class _ActorHandle:
        def call(self, run_input=None):
            assert run_input is not None
            assert "max_items_per_star" in run_input
            assert run_input["stars"][0]["star_id"] == "* alf Ori"
            return {"defaultDatasetId": "dataset-1"}

    class _Client:
        def __init__(self, token: str) -> None:
            assert token == "test-token"

        def actor(self, actor_id: str) -> _ActorHandle:
            assert actor_id == "user/breakout-star-literature"
            return _ActorHandle()

        def dataset(self, dataset_id: str) -> _Dataset:
            assert dataset_id == "dataset-1"
            return _Dataset()

    fake = types.ModuleType("apify_client")
    fake.ApifyClient = _Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "apify_client", fake)

    written = mod.fetch_and_store(
        [{"star_id": "* alf Ori", "aliases": ["Betelgeuse"]}],
        out_dir=tmp_path,
    )
    payload = json.loads(written["* alf Ori"].read_text(encoding="utf-8"))
    assert payload["items"][0]["item_id"] == "2006.09837"
    assert payload["items"][0]["url"] == "https://arxiv.org/abs/2006.09837"
    assert payload["items"][0]["simulated"] is False


def test_resolve_apify_item_drops_without_bibcode(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.literature import build_index as bi

    class _Resp:
        def __init__(self, docs: list[dict[str, Any]]) -> None:
            self._docs = docs

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"response": {"docs": self._docs}}

    def _get(url: str, params=None, headers=None, timeout=None):  # noqa: ANN001
        return _Resp([])  # ADS has nothing → drop

    paper = bi.resolve_apify_item_ads_bibcode(
        {
            "source": "arxiv",
            "item_id": "2006.09837",
            "title": "Betelgeuse paper",
            "abstract_or_summary": "…",
        },
        token="tok",
        http_get=_get,
    )
    assert paper is None

    def _get_hit(url: str, params=None, headers=None, timeout=None):  # noqa: ANN001
        return _Resp(
            [{"bibcode": "2020arXiv2006.09837X", "title": ["Betelgeuse paper"], "abstract": "abs"}]
        )

    paper2 = bi.resolve_apify_item_ads_bibcode(
        {
            "source": "arxiv",
            "item_id": "2006.09837",
            "title": "Betelgeuse paper",
            "abstract_or_summary": "abs",
        },
        token="tok",
        http_get=_get_hit,
    )
    assert paper2 is not None
    assert paper2["bibcode"] == "2020arXiv2006.09837X"
    assert paper2["source"] == "Apify+ADS"
