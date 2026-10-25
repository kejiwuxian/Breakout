"""Public base URL resolution for local vs production / tunnel mode."""

from __future__ import annotations

import importlib

import pytest

import backend.config as config_mod

_CLEAR_KEYS = (
    "BREAKOUT_PUBLIC_BASE_URL",
    "PUBLIC_BASE_URL",
    "BREAKOUT_PUBLIC_URL",
    "ENV",
    "BREAKOUT_ENV",
    "BREAKOUT_PUBLIC",
    "BREAKOUT_SERVE_FRONTEND",
)


def _reload(**env: str):
    for key in _CLEAR_KEYS:
        config_mod.os.environ.pop(key, None)
    for key, value in env.items():
        config_mod.os.environ[key] = value
    importlib.reload(config_mod)
    return config_mod


@pytest.fixture(autouse=True)
def _restore_config_env():
    saved = {k: config_mod.os.environ.get(k) for k in _CLEAR_KEYS}
    yield
    for key in _CLEAR_KEYS:
        config_mod.os.environ.pop(key, None)
    for key, value in saved.items():
        if value is not None:
            config_mod.os.environ[key] = value
    importlib.reload(config_mod)
    # Keep backend.app.settings in sync for later tests in the same process.
    import backend.app as app_mod

    app_mod.settings = config_mod.settings


def test_default_is_local() -> None:
    cfg = _reload()
    assert cfg.resolve_public_base_url() == "http://127.0.0.1:8000"
    assert cfg.load_settings().public_base_url == "http://127.0.0.1:8000"
    assert cfg.load_settings().serve_frontend is False


def test_env_production_selects_public_host() -> None:
    cfg = _reload(ENV="production")
    assert cfg.resolve_public_base_url() == "https://supernova.lylinks.com"
    settings = cfg.load_settings()
    assert settings.public_base_url == "https://supernova.lylinks.com"
    assert settings.serve_frontend is True


def test_explicit_override_wins() -> None:
    cfg = _reload(
        ENV="production",
        BREAKOUT_PUBLIC_BASE_URL="https://example.test",
    )
    assert cfg.resolve_public_base_url() == "https://example.test"


def test_public_ws_base_url() -> None:
    cfg = _reload()
    assert (
        cfg.public_ws_base_url("https://supernova.lylinks.com")
        == "wss://supernova.lylinks.com"
    )
    assert cfg.public_ws_base_url("http://127.0.0.1:8000") == "ws://127.0.0.1:8000"


def test_cors_includes_public_and_vite() -> None:
    cfg = _reload(ENV="production")
    origins = cfg.cors_allow_origins()
    assert "https://supernova.lylinks.com" in origins
    assert "http://127.0.0.1:5173" in origins


def test_health_exposes_public_base_url() -> None:
    cfg = _reload(ENV="production")
    import backend.app as app_mod

    app_mod.settings = cfg.load_settings()
    from fastapi.testclient import TestClient

    with TestClient(app_mod.app) as client:
        body = client.get("/health").json()
    assert body["public_base_url"] == "https://supernova.lylinks.com"
    assert body["public_ws_base_url"] == "wss://supernova.lylinks.com"
