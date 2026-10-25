"""P2.3: Apify literature integration — mocked client; flag-off safety."""

from __future__ import annotations

import importlib
import json
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
    <title>Betelgeuse example preprint title</title>
    <published>2020-06-17T00:00:00Z</published>
    <summary>Abstract text.</summary>
  </entry>
</feed>
"""

ATEL_HTML = """
<html><body>
<a href="?read=13601">Betelgeuse Great Dimming notice</a>
<a href="?read=0">Home</a>
</body></html>
"""


def _fake_http_get(url: str, params: dict | None = None, **_kwargs: Any) -> _FakeResponse:
    if "arxiv.org" in url:
        return _FakeResponse(ARXIV_ATOM)
    if "astronomerstelegram.org" in url:
        return _FakeResponse(ATEL_HTML)
    raise AssertionError(f"unexpected URL {url} params={params}")


def test_flag_off_does_not_import_apify_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APIFY_ENABLED", "False")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    import backend.integrations.apify_literature as mod

    importlib.reload(mod)
    assert mod.is_enabled() is False
    written = mod.fetch_and_store([{"star_id": "* alf Ori"}], out_dir=Path("/tmp/unused"))
    assert written == {}


def test_local_fetchers_write_real_shaped_items(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APIFY_ENABLED", "True")
    monkeypatch.setenv("APIFY_TOKEN", "")
    from backend import config as config_mod

    config_mod.settings = config_mod.load_settings()
    import backend.integrations.apify_literature as mod

    importlib.reload(mod)
    assert mod.is_enabled() is True

    written = mod.fetch_and_store(
        [{"star_id": "* alf Ori", "aliases": ["Betelgeuse"]}],
        out_dir=tmp_path,
        prefer_cloud=False,
        http_get=_fake_http_get,
    )
    assert "* alf Ori" in written
    payload = json.loads(written["* alf Ori"].read_text(encoding="utf-8"))
    assert payload["star_id"] == "* alf Ori"
    assert payload["n_items"] >= 2
    sources = {item["source"] for item in payload["items"]}
    assert sources == {"arxiv", "atel"}
    for item in payload["items"]:
        assert item["simulated"] is False
        assert item["url"].startswith("http")
        assert item["item_id"]
        assert item["title"]


def test_cloud_client_mocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
                "title": "Mocked arXiv row",
                "date": "2020-06-17",
                "url": "https://arxiv.org/abs/2006.09837",
                "simulated": False,
            }

    class _Actor:
        def call(self, run_input=None):
            assert run_input is not None
            assert run_input["stars"][0]["star_id"] == "* alf Ori"
            return {"defaultDatasetId": "dataset-1"}

    class _Client:
        def __init__(self, token: str) -> None:
            assert token == "test-token"

        def actor(self, actor_id: str) -> _Actor:
            assert actor_id == "user/breakout-star-literature"
            return _Actor()

        def dataset(self, dataset_id: str) -> _Dataset:
            assert dataset_id == "dataset-1"
            return _Dataset()

    import sys
    import types

    fake = types.ModuleType("apify_client")
    fake.ApifyClient = _Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "apify_client", fake)

    written = mod.fetch_and_store(
        [{"star_id": "* alf Ori", "aliases": ["Betelgeuse"]}],
        out_dir=tmp_path,
        prefer_cloud=True,
    )
    payload = json.loads(written["* alf Ori"].read_text(encoding="utf-8"))
    assert payload["items"][0]["item_id"] == "2006.09837"
    assert payload["items"][0]["simulated"] is False


def test_actor_main_local_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    actor_src = ACTOR_ROOT / "src"
    sys.path.insert(0, str(actor_src))
    import main as actor_main  # type: ignore[import-not-found]

    inp = tmp_path / "input.json"
    out = tmp_path / "out.jsonl"
    inp.write_text(
        json.dumps(
            {
                "stars": [{"star_id": "* alf Ori", "aliases": ["Betelgeuse"]}],
                "sources": ["arxiv", "atel"],
                "max_per_source": 5,
            }
        ),
        encoding="utf-8",
    )
    # Patch httpx used inside fetchers via run_local(http_get=...).
    items = actor_main.run_local(
        json.loads(inp.read_text(encoding="utf-8")),
        http_get=_fake_http_get,
    )
    assert any(i["source"] == "arxiv" for i in items)
    assert any(i["source"] == "atel" for i in items)
    out.write_text(
        "\n".join(json.dumps(i) for i in items) + "\n",
        encoding="utf-8",
    )
    assert out.is_file()
